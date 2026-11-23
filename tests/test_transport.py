"""How requests leave and how refusals come back."""

from __future__ import annotations

import json
import socket
from typing import Any
from urllib.parse import quote

import pytest
from support import TOKEN, FakeThreads, graph_error, ok, page, raw, refuse, run, text_of

from flowsteward_extension_sdk import PinnedPeerError


def test_the_token_travels_only_in_the_authorization_header() -> None:
    fake = FakeThreads(ok({"id": "1", "status": "FINISHED"}))
    run("get_media_container_status", {"threads_container_id": "1"}, fake)
    call = fake.calls[0]
    assert call.headers["authorization"] == "Bearer " + TOKEN
    assert TOKEN not in call.url and TOKEN.encode() not in call.raw_body
    assert call.host == "graph.threads.com" and call.path == "/v1.0/1"
    assert call.q("fields") == "status"


def test_a_post_sends_its_parameters_as_a_form() -> None:
    fake = FakeThreads(ok({"success": True}))
    run("hide_or_unhide_reply", {"threads_reply_id": "77", "hide": True}, fake)
    call = fake.calls[0]
    assert call.verb == "POST" and call.path == "/v1.0/77/manage_reply"
    assert call.headers["content-type"] == "application/x-www-form-urlencoded"
    assert call.form == {"hide": "true"}
    assert call.query == []


def test_the_embed_endpoint_is_called_without_a_token() -> None:
    fake = FakeThreads(ok({"html": "<blockquote>", "type": "rich", "version": "1.0"}))
    response = run("get_embed_html", {"url": "https://www.threads.com/@meta"}, fake)
    assert response["ok"] is True, response
    assert "authorization" not in fake.calls[0].headers


def test_the_token_is_removed_from_answers() -> None:
    forms = [TOKEN, quote(TOKEN, safe="")]
    answer = {"id": "1", "a": forms[0], "b": "x?access_token=" + forms[1], forms[0]: 1}
    response = run("get_post", {"threads_media_id": "1"}, FakeThreads(ok(answer)))
    assert response["ok"] is True
    assert TOKEN not in text_of(response) and forms[1] not in text_of(response)


def test_paging_addresses_are_not_returned() -> None:
    response = run("get_user_posts", {}, FakeThreads(ok(page([{"id": "1"}], "A1", more=True))))
    assert response["ok"] is True
    assert "next" not in text_of(response["result"]).replace("next_after", "")
    assert response["result"]["next_after"] == "A1" and response["result"]["complete"] is False


@pytest.mark.parametrize(
    ("status", "body", "code"),
    [
        (400, graph_error(190, "Error validating access token"), "authentication_failed"),
        (400, graph_error(10, "Permission denied"), "authentication_failed"),
        (403, graph_error(200, "Requires permission"), "authentication_failed"),
        (400, graph_error(4, "Application request limit reached"), "rate_limited"),
        (400, graph_error(17, "User request limit reached"), "rate_limited"),
        (400, graph_error(613, "Calls within one hour exceeded"), "rate_limited"),
        (429, graph_error(32, "Page request limit"), "rate_limited"),
        (404, graph_error(803, "Unknown object"), "not_found"),
        (400, graph_error(100, "Invalid parameter"), "upstream_validation_failed"),
        (500, graph_error(2, "Service temporarily unavailable"), "upstream_failure"),
    ],
)
def test_a_documented_refusal_of_a_write_changed_nothing(status: int, body: Any, code: str) -> None:
    response = run(
        "hide_or_unhide_reply",
        {"threads_reply_id": "1", "hide": True},
        FakeThreads(refuse(status, body)),
    )
    assert response["error_code"] == code
    if status < 500:
        assert response["definitely_no_external_effect"] is True
        assert response["external_effect_status"] == "failed"
        assert "nothing was changed" in response["error"]
    else:
        assert response["external_effect_status"] == "timeout_unknown"
    assert "fbtrace_id AbCdEf123" in response["error"]


@pytest.mark.parametrize(
    "body",
    [None, b"<html>bad gateway</html>", {"error": "text"}, {"error": {"code": "x"}}, {"oops": 1}],
)
def test_a_refusal_without_the_documented_error_form_leaves_a_write_unknown(body: Any) -> None:
    response = run(
        "approve_or_ignore_pending_reply",
        {"threads_reply_id": "1", "approve": True},
        FakeThreads(refuse(400, body)),
    )
    assert response["external_effect_status"] == "timeout_unknown"
    assert response["definitely_no_external_effect"] is False


def test_a_408_leaves_a_write_unknown_even_with_the_error_form() -> None:
    response = run(
        "repost_post", {"threads_media_id": "1"}, FakeThreads(refuse(408, graph_error(2)))
    )
    assert response["external_effect_status"] == "timeout_unknown"


def test_a_read_refusal_is_retryable_only_when_it_may_pass_later() -> None:
    limited = run(
        "get_post",
        {"threads_media_id": "1"},
        FakeThreads(refuse(400, graph_error(4), Retry_After="7")),
    )
    assert limited["error_code"] == "rate_limited" and limited["retryable"] is True
    assert limited["retry_after_seconds"] == 7
    invalid = run("get_post", {"threads_media_id": "1"}, FakeThreads(refuse(400, graph_error(100))))
    assert invalid["retryable"] is False


def test_another_2xx_is_not_success() -> None:
    read = run("get_post", {"threads_media_id": "1"}, FakeThreads(ok({"id": "1"}, status=202)))
    assert read["error_code"] == "invalid_response"
    assert read["definitely_no_external_effect"] is True
    write = run("repost_post", {"threads_media_id": "1"}, FakeThreads(ok({"id": "2"}, status=201)))
    assert write["external_effect_status"] == "timeout_unknown"


def test_a_redirect_is_not_followed() -> None:
    response = run("get_post", {"threads_media_id": "1"}, FakeThreads(refuse(302, None)))
    assert response["error_code"] == "redirect_rejected"


def test_usage_headers_are_returned_when_threads_sends_them() -> None:
    usage = {"call_count": 28, "total_time": 25, "total_cputime": 25}
    answer = raw(200, b'{"id":"1"}', X_App_Usage=json.dumps(usage))
    response = run("get_post", {"threads_media_id": "1"}, FakeThreads(answer))
    assert response["result"]["rate_limit_usage"] == {"X-App-Usage": usage}
    plain = run("get_post", {"threads_media_id": "1"}, FakeThreads(ok({"id": "1"})))
    assert plain["result"]["rate_limit_usage"] is None


def test_a_token_in_a_refusal_never_reaches_the_error() -> None:
    body = graph_error(100, f"Bad token {TOKEN}")
    response = run("get_post", {"threads_media_id": "1"}, FakeThreads(refuse(400, body)))
    assert TOKEN not in text_of(response)


def test_network_failures() -> None:
    read = run("get_post", {"threads_media_id": "1"}, FakeThreads(socket.timeout("slow")))
    assert read["error_code"] == "timeout" and read["definitely_no_external_effect"] is True
    write = run("repost_post", {"threads_media_id": "1"}, FakeThreads(ConnectionResetError()))
    assert write["error_code"] == "timeout_unknown"
    unresolved = run(
        "repost_post",
        {"threads_media_id": "1"},
        FakeThreads(PinnedPeerError("host cannot be resolved")),
    )
    assert unresolved["error_code"] == "connection_failed"
    assert unresolved["definitely_no_external_effect"] is True


def test_the_connection_must_be_a_threads_connection_with_a_token() -> None:
    other = {"connection_id": "conn-1", "connection_type": "x", "secrets": {"access_token": TOKEN}}
    assert (
        run("get_post", {"threads_media_id": "1"}, connection=other)["error_code"]
        == "invalid_connection"
    )
    short = run("get_post", {"threads_media_id": "1"}, token="abc")
    assert short["error_code"] == "invalid_connection"
    extra = {
        "connection_id": "conn-1",
        "connection_type": "threads_account",
        "secrets": {"access_token": TOKEN, "app_secret": "s" * 20},
    }
    assert (
        run("get_post", {"threads_media_id": "1"}, connection=extra)["error_code"]
        == "invalid_connection"
    )
