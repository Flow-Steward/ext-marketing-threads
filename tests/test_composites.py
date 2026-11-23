"""The everyday steps."""

from __future__ import annotations

from typing import Any

import pytest
from support import Clock, FakeThreads, graph_error, ok, page, refuse, run, text_of


def status(value: str, ident: str = "10", message: str | None = None) -> Any:
    body: dict[str, Any] = {"id": ident, "status": value}
    if message:
        body["error_message"] = message
    return ok(body)


def published(post: str = "20") -> list[Any]:
    return [ok({"id": post}), ok({"id": post, "permalink": "https://www.threads.com/@me/post/abc"})]


def test_test_connection_reads_the_account() -> None:
    fake = FakeThreads(ok({"id": "123", "username": "brand", "name": "Brand"}))
    response = run("test_connection", {}, fake)
    assert response["result"]["user_id"] == "123" and response["result"]["username"] == "brand"
    assert fake.calls[0].path == "/v1.0/me"


def test_a_text_post_is_created_checked_and_published() -> None:
    fake = FakeThreads(ok({"id": "10"}), status("FINISHED"), *published())
    response = run(
        "publish_post", {"media_type": "TEXT", "text": "Hello\nThreads", "topic_tag": "News"}, fake
    )
    result = response["result"]
    assert response["ok"] is True, response
    assert result["post_id"] == "20" and result["container_id"] == "10"
    assert result["permalink"] == "https://www.threads.com/@me/post/abc"
    assert result["processing"] == "completed" and result["applied"] is True
    assert response["external_effect_status"] == "succeeded"
    keys = [c.key for c in fake.calls]
    assert keys == ["POST /me/threads", "GET /10", "POST /me/threads_publish", "GET /20"]
    assert fake.calls[0].form == {
        "media_type": "TEXT",
        "text": "Hello\nThreads",
        "topic_tag": "News",
    }
    assert fake.calls[2].form == {"creation_id": "10"}


def test_a_carousel_creates_one_container_per_item_first() -> None:
    fake = FakeThreads(
        ok({"id": "1"}), ok({"id": "2"}), ok({"id": "10"}), status("FINISHED"), *published()
    )
    items = [
        {"image_url": "https://cdn.example.com/1.jpg", "alt_text": "one"},
        {"video_url": "https://cdn.example.com/2.mp4"},
    ]
    response = run("publish_post", {"media_type": "CAROUSEL", "text": "Two", "items": items}, fake)
    assert response["result"]["item_container_ids"] == ["1", "2"]
    assert fake.calls[0].form == {
        "media_type": "IMAGE",
        "image_url": "https://cdn.example.com/1.jpg",
        "alt_text": "one",
        "is_carousel_item": "true",
    }
    assert fake.calls[1].form["media_type"] == "VIDEO"
    assert fake.calls[2].form == {"media_type": "CAROUSEL", "text": "Two", "children": "1,2"}


def test_a_video_still_processing_is_checked_once_a_minute() -> None:
    clock = Clock()
    fake = FakeThreads(
        ok({"id": "10"}),
        status("IN_PROGRESS"),
        status("IN_PROGRESS"),
        status("FINISHED"),
        *published(),
    )
    response = run(
        "publish_post",
        {"media_type": "VIDEO", "video_url": "https://cdn.example.com/v.mp4"},
        fake,
        clock=clock,
    )
    assert response["result"]["post_id"] == "20"
    assert response["result"]["status_checks"] == 3
    assert clock.slept == [60.0, 60.0]


def test_a_container_still_processing_after_five_checks_is_accepted_not_published() -> None:
    clock = Clock()
    fake = FakeThreads(ok({"id": "10"}), *[status("IN_PROGRESS") for _ in range(5)])
    response = run(
        "publish_post",
        {"media_type": "VIDEO", "video_url": "https://cdn.example.com/v.mp4"},
        fake,
        clock=clock,
    )
    result = response["result"]
    assert response["ok"] is True
    assert result["processing"] == "accepted" and result["applied"] is False
    assert result["check"] == {"operation_id": "get_media_container_status", "container_id": "10"}
    assert result["post_id"] is None and len(clock.slept) == 4
    assert "not published yet" in result["warnings"][0]
    assert response["external_effect_status"] == "succeeded"


def test_a_container_threads_could_not_process_is_reported_with_its_reason() -> None:
    fake = FakeThreads(ok({"id": "10"}), status("ERROR", message="FAILED_DOWNLOADING_VIDEO"))
    response = run(
        "publish_post", {"media_type": "VIDEO", "video_url": "https://cdn.example.com/v.mp4"}, fake
    )
    assert response["ok"] is False
    assert (
        "FAILED_DOWNLOADING_VIDEO" in response["error"]
        and "nothing was published" in response["error"]
    )
    assert response["external_effect_status"] == "timeout_unknown"


def test_a_refused_container_changes_nothing() -> None:
    fake = FakeThreads(refuse(400, graph_error(100, "Invalid image")))
    response = run(
        "publish_post", {"media_type": "IMAGE", "image_url": "https://cdn.example.com/i.png"}, fake
    )
    assert response["definitely_no_external_effect"] is True
    assert response["external_effect_status"] == "failed"


def test_a_failed_publish_after_a_created_container_is_not_reported_as_nothing_changed() -> None:
    fake = FakeThreads(ok({"id": "10"}), status("FINISHED"), refuse(400, graph_error(100)))
    response = run("publish_post", {"media_type": "TEXT", "text": "x"}, fake)
    assert response["external_effect_status"] == "timeout_unknown"
    assert response["definitely_no_external_effect"] is False


def test_an_unreadable_permalink_only_warns() -> None:
    fake = FakeThreads(
        ok({"id": "10"}), status("FINISHED"), ok({"id": "20"}), refuse(500, graph_error(2))
    )
    response = run("publish_post", {"media_type": "TEXT", "text": "x"}, fake)
    assert response["ok"] is True and response["result"]["post_id"] == "20"
    assert "permalink could not be read" in response["result"]["warnings"][0]


@pytest.mark.parametrize(
    "given",
    [
        {"media_type": "TEXT"},
        {"media_type": "IMAGE"},
        {
            "media_type": "IMAGE",
            "image_url": "https://x.example/i.png",
            "video_url": "https://x.example/v.mp4",
        },
        {"media_type": "CAROUSEL", "items": [{"image_url": "https://x.example/1.png"}]},
        {
            "media_type": "IMAGE",
            "image_url": "https://x.example/1.png",
            "link_attachment": "https://x.example",
        },
        {"media_type": "TEXT", "text": " ".join(f"https://a{i}.example" for i in range(6))},
        {"media_type": "TEXT", "text": "x", "topic_tag": "a.b"},
        {"media_type": "TEXT", "text": "x" * 501},
    ],
)
def test_a_post_threads_would_refuse_is_not_sent(given: dict[str, Any]) -> None:
    fake = FakeThreads()
    response = run("publish_post", given, fake)
    assert response["error_code"] == "invalid_payload", response
    assert fake.calls == []


def test_a_test_run_sends_nothing() -> None:
    fake = FakeThreads()
    response = run("publish_post", {"media_type": "TEXT", "text": "x"}, fake, test_mode=True)
    assert fake.calls == []
    assert response["definitely_no_external_effect"] is True
    assert response["external_effect_status"] == "failed"
    assert response["result"]["warnings"]


def test_a_test_run_still_checks_the_inputs() -> None:
    response = run("reply_to_post", {"text": "x"}, test_mode=True)
    assert response["error_code"] == "invalid_payload"


def test_a_reply_is_published_to_the_post_it_answers() -> None:
    fake = FakeThreads(ok({"id": "10"}), status("FINISHED"), *published("30"))
    response = run("reply_to_post", {"reply_to_id": "555", "text": "Thanks!"}, fake)
    assert response["result"]["reply_id"] == "30"
    assert fake.calls[0].form == {"media_type": "TEXT", "text": "Thanks!", "reply_to_id": "555"}


def test_all_replies_are_read_page_by_page() -> None:
    fake = FakeThreads(ok(page([{"id": "1"}], "A1", more=True)), ok(page([{"id": "2"}])))
    response = run("list_post_replies", {"post_id": "9", "reverse": False}, fake)
    assert [r["id"] for r in response["result"]["replies"]] == ["1", "2"]
    assert fake.calls[0].path == "/v1.0/9/replies" and fake.calls[0].q("reverse") == "false"
    nested = FakeThreads(ok(page([])))
    run("list_post_replies", {"post_id": "9", "include_nested": True}, nested)
    assert nested.calls[0].path == "/v1.0/9/conversation"


def test_all_my_posts_with_every_field() -> None:
    fake = FakeThreads(ok(page([{"id": "1", "text": "a"}])))
    response = run("list_my_posts", {"since": "2026-01-01", "max_posts": 5}, fake)
    assert response["result"]["posts"] == [{"id": "1", "text": "a"}]
    assert "permalink" in fake.calls[0].q("fields")
    assert fake.calls[0].q("limit") == "5" and fake.calls[0].q("since") == "2026-01-01"


def test_post_insights_are_one_number_each() -> None:
    answer = {
        "data": [
            {"name": "likes", "period": "lifetime", "values": [{"value": 100}]},
            {"name": "views", "period": "lifetime", "total_value": {"value": 900}},
        ]
    }
    fake = FakeThreads(ok(answer))
    response = run("get_post_insights", {"post_id": "1"}, fake)
    assert response["result"]["metrics"] == {"likes": 100, "views": 900}
    assert fake.calls[0].q("metric") == "views,likes,replies,reposts,quotes,shares"


@pytest.mark.parametrize(
    ("given", "words"),
    [
        ({"metrics": ["followers_count"], "since": "2026-01-01"}, "do not take since"),
        ({"metrics": ["follower_demographics"]}, "needs breakdown"),
        ({"since": "2024-01-01"}, "on or after"),
        ({"since": "2026-02-01", "until": "2026-01-01"}, "before until"),
    ],
)
def test_account_insights_follow_the_documented_rules(given: dict[str, Any], words: str) -> None:
    response = run("get_account_insights", given)
    assert response["error_code"] == "invalid_payload" and words in response["error"]


def test_account_insights_with_a_period() -> None:
    answer = {
        "data": [
            {
                "name": "views",
                "values": [{"value": 1, "end_time": "a"}, {"value": 2, "end_time": "b"}],
            }
        ]
    }
    fake = FakeThreads(ok(answer))
    response = run(
        "get_account_insights",
        {"metrics": ["views"], "since": "2026-01-01", "until": "2026-01-03"},
        fake,
    )
    assert response["result"]["metrics"]["views"] == [
        {"value": 1, "end_time": "a"},
        {"value": 2, "end_time": "b"},
    ]
    assert fake.calls[0].path == "/v1.0/me/threads_insights"


def test_publishing_limits_are_returned_by_kind() -> None:
    answer = {
        "data": [
            {
                "quota_usage": 4,
                "config": {"quota_total": 250, "quota_duration": 86400},
                "reply_quota_usage": 1,
                "reply_config": {"quota_total": 1000, "quota_duration": 86400},
            }
        ]
    }
    response = run("get_publishing_limit", {}, FakeThreads(ok(answer)))
    result = response["result"]
    assert result["posts"] == {"used": 4, "total": 250, "window_seconds": 86400}
    assert result["replies"]["total"] == 1000
    assert result["deletes"] == {"used": None, "total": None, "window_seconds": None}


def test_no_result_carries_the_token() -> None:
    from support import TOKEN

    fake = FakeThreads(ok({"id": "1", "username": TOKEN}))
    assert TOKEN not in text_of(run("test_connection", {}, fake))
