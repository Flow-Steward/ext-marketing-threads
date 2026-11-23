"""Generated steps: inputs checked against the documentation, lists read page by page."""

from __future__ import annotations

from typing import Any

import pytest
from support import FakeThreads, graph_error, ok, page, refuse, run

from runtime import budget, generic


def _read_ok(
    operation_id: str, given: dict[str, Any], answer: Any = None
) -> tuple[dict[str, Any], Any]:
    fake = FakeThreads(ok(answer if answer is not None else {"id": "1"}))
    return run(operation_id, given, fake), fake


@pytest.mark.parametrize(
    ("given", "words"),
    [
        ({"threads_media_id": "abc"}, "digits"),
        ({"threads_media_id": "1", "fields": ["id", "nope"]}, "may only name"),
        ({"threads_media_id": "1", "extra": 1}, "unknown fields"),
    ],
)
def test_an_input_the_documentation_does_not_allow_is_refused_before_sending(
    given: dict[str, Any], words: str
) -> None:
    fake = FakeThreads()
    response = run("get_post", given, fake)
    assert response["error_code"] == "invalid_payload" and words in response["error"]
    assert fake.calls == []


def test_the_user_id_is_me_unless_given() -> None:
    _, fake = _read_ok("get_user_profile", {})
    assert fake.calls[0].path == "/v1.0/me"
    _, fake = _read_ok("get_user_profile", {"threads_user_id": "123"})
    assert fake.calls[0].path == "/v1.0/123"


def test_fields_and_metrics_travel_comma_separated() -> None:
    _, fake = _read_ok("get_post", {"threads_media_id": "1", "fields": ["id", "text", "permalink"]})
    assert fake.calls[0].q("fields") == "id,text,permalink"
    _, fake = _read_ok(
        "get_media_insights", {"threads_media_id": "1", "metric": ["views", "likes"]}, {"data": []}
    )
    assert fake.calls[0].q("metric") == "views,likes"


@pytest.mark.parametrize(
    ("since", "until", "ok_"),
    [
        ("2026-01-01", "2026-01-31", True),
        ("1767225600", "1769904000", True),
        ("2026-02-31", None, False),
        ("2026-01-31", "2026-01-01", False),
        ("1600000000", None, False),
        ("yesterday", None, False),
    ],
)
def test_dates_are_real_and_in_order(since: str, until: str | None, ok_: bool) -> None:
    given = {"since": since, **({"until": until} if until else {})}
    fake = FakeThreads(ok(page([])))
    response = run("get_user_posts", given, fake)
    assert (response["ok"] is True) is ok_, response
    if ok_:
        assert fake.calls[0].q("since") == since


def test_lists_and_objects_are_encoded_as_documented() -> None:
    fake = FakeThreads(ok({"id": "9"}))
    response = run(
        "create_media_container",
        {
            "media_type": "CAROUSEL",
            "children": ["1", "2"],
            "allowlisted_country_codes": ["US", "CA"],
            "poll_attachment": {"option_a": "first", "option_b": "second"},
            "is_made_with_ai": True,
        },
        fake,
    )
    assert response["ok"] is True, response
    form = fake.calls[0].form
    assert form["children"] == "1,2"
    assert form["allowlisted_country_codes"] == "US,CA"
    assert form["poll_attachment"] == '{"option_a":"first","option_b":"second"}'
    assert form["is_made_with_ai"] == "true"
    assert response["result"]["processing"] == "accepted"
    assert response["result"]["check"] == {
        "operation_id": "get_media_container_status",
        "container_id": "9",
    }


@pytest.mark.parametrize(
    "given",
    [
        {"media_type": "SONG"},
        {"media_type": "CAROUSEL", "children": ["1"]},
        {"media_type": "TEXT", "text": "x" * 501},
        {"media_type": "IMAGE", "image_url": "ftp://x/y.jpg"},
        {"media_type": "TEXT", "allowlisted_country_codes": ["usa"]},
        {"media_type": "TEXT", "reply_control": "nobody"},
    ],
)
def test_a_container_the_documentation_rules_out_is_not_sent(given: dict[str, Any]) -> None:
    fake = FakeThreads()
    response = run("create_media_container", given, fake)
    assert response["error_code"] == "invalid_payload", response
    assert response["definitely_no_external_effect"] is True
    assert fake.calls == []


def test_one_page_gives_the_cursor_to_continue() -> None:
    response, fake = _read_ok(
        "get_user_replies", {"limit": 50}, page([{"id": "1"}], "A1", more=True)
    )
    assert response["result"]["items"] == [{"id": "1"}]
    assert response["result"]["next_after"] == "A1"
    assert response["result"]["complete"] is False
    assert fake.calls[0].q("limit") == "50"


def test_all_pages_reads_until_the_list_ends() -> None:
    fake = FakeThreads(
        ok(page([{"id": "1"}, {"id": "2"}], "A1", more=True)),
        ok(page([{"id": "2"}, {"id": "3"}], "A2", more=True)),
        ok(page([], None)),
    )
    response = run("get_user_mentions", {"all_pages": True}, fake)
    result = response["result"]
    assert [i["id"] for i in result["items"]] == ["1", "2", "3"]
    assert result["complete"] is True and result["next_after"] is None
    assert any("appeared twice" in w for w in result["warnings"])
    assert [c.q("after") for c in fake.calls] == [None, "A1", "A2"]
    assert all(c.q("limit") == "100" for c in fake.calls)


def test_all_pages_stops_at_the_maximum_on_whole_pages_with_where_to_continue() -> None:
    fake = FakeThreads(ok(page([{"id": "1"}, {"id": "2"}], "A1", more=True)))
    response = run("get_user_posts", {"all_pages": True, "max_items": 2}, fake)
    result = response["result"]
    assert result["count"] == 2 and result["complete"] is False and result["next_after"] == "A1"
    assert fake.calls[0].q("limit") == "2"
    again = FakeThreads(ok(page([{"id": "3"}], None)))
    run("get_user_posts", {"all_pages": True, "after": "A1"}, again)
    assert again.calls[0].q("after") == "A1"


def test_an_empty_page_that_says_more_follow_is_an_incomplete_read() -> None:
    fake = FakeThreads(ok(page([{"id": "1"}], "A1", more=True)), ok(page([], "A2", more=True)))
    response = run("get_user_posts", {"all_pages": True}, fake)
    assert response["error_code"] == "invalid_response"
    assert "not complete" in response["error"]


def test_a_cursor_given_again_is_an_error_not_a_loop() -> None:
    fake = FakeThreads(ok(page([{"id": "1"}], "A1")), ok(page([{"id": "2"}], "A1")))
    response = run("get_user_posts", {"all_pages": True}, fake)
    assert response["error_code"] == "invalid_response" and "cursor" in response["error"]


def test_a_page_too_large_for_the_output_is_asked_again_with_half_the_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(budget, "MAX_SERIALIZED_BYTES", 40_000)
    records = [{"id": str(i), "text": "x" * 1000} for i in range(1000)]

    def answer(call: Any) -> Any:
        start = int((call.q("after") or "P0")[1:])
        size = int(call.q("limit"))
        return ok(page(records[start : start + size], f"P{start + size}", more=True))

    fake = FakeThreads(routes={"GET /me/threads": [answer] * 50})
    response = run("get_user_posts", {"all_pages": True}, fake)
    result = response["result"]
    limits = [int(c.q("limit")) for c in fake.calls]
    assert limits[:4] == [100, 50, 25, 100]
    assert result["complete"] is False
    # Whole pages only, and the cursor points at the first record not returned.
    assert result["next_after"] == f"P{result['count']}"
    assert [r["id"] for r in result["items"]] == [str(i) for i in range(result["count"])]
    assert budget.fits(result)


def test_a_failed_later_page_returns_what_was_read() -> None:
    fake = FakeThreads(ok(page([{"id": "1"}], "A1", more=True)), refuse(500, graph_error(2)))
    response = run("get_user_posts", {"all_pages": True}, fake)
    result = response["result"]
    assert result["count"] == 1 and result["next_after"] == "A1"
    assert "could not give the next page" in result["warnings"][-1]


def test_all_pages_and_before_do_not_mix() -> None:
    response = run("get_user_posts", {"all_pages": True, "before": "B"})
    assert response["error_code"] == "invalid_payload"


def test_every_list_endpoint_is_a_paged_step() -> None:
    paged = {oid for oid, e in generic.registry().items() if e["paged"]}
    assert paged == {
        "get_user_posts",
        "get_user_replies",
        "get_user_mentions",
        "get_user_ghost_posts",
        "get_public_profile_posts",
        "get_post_replies",
        "get_post_conversation",
        "get_pending_replies",
    }
