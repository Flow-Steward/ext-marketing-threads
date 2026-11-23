"""The everyday steps, built on the documented endpoints of runtime/registry.json.

Each one goes through the same checks and transport as the generated step of the
endpoint it calls (generic.prepare), so refusals and token handling are the same.

Publishing follows the documented two-step protocol: create a media container
(``POST /{threads-user-id}/threads``; for a carousel first one container per item),
check its status (``GET /{threads-container-id}?fields=status``) until it is
``FINISHED``, then publish it (``POST /{threads-user-id}/threads_publish``). The
documentation recommends checking a container's status once per minute, for no more
than five minutes; the step does that while its time allows. When the container is
still ``IN_PROGRESS`` the step returns ``processing`` ``accepted`` with the container ID
in ``check``: read its status with Get media container status and publish it with
Publish media container. Images and videos are given as public addresses, because
Threads fetches the media itself from a public server (it accepts no file upload).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from . import errors, generic, outcome, pages
from .context import Context
from .errors import ExtensionError, invalid
from .params import moment, names, text, timestamp_of, url
from .transport import MIN_CALL_WINDOW_SECONDS, DeadlineReached

#: Documented limits (tests/reference/threads_api.json, ``limits``).
TEXT_MAX = 500
ALT_TEXT_MAX = 1000
TOPIC_TAG_MAX = 50
CAROUSEL_MIN = 2
CAROUSEL_MAX = 20
LINKS_MAX = 5
STATUS_INTERVAL_SECONDS = 60.0
STATUS_CHECKS = 5
REPLY_CONTROLS = [
    "everyone",
    "accounts_you_follow",
    "mentioned_only",
    "parent_post_author_only",
    "followers_only",
]
MEDIA_TYPES = ["TEXT", "IMAGE", "VIDEO", "CAROUSEL"]
PROFILE_FIELDS = [
    "id",
    "username",
    "name",
    "threads_profile_picture_url",
    "threads_biography",
    "is_verified",
]
POST_FIELDS = [
    "id",
    "media_product_type",
    "media_type",
    "media_url",
    "permalink",
    "owner",
    "username",
    "text",
    "timestamp",
    "shortcode",
    "thumbnail_url",
    "children",
    "is_quote_post",
    "alt_text",
    "link_attachment_url",
    "has_replies",
    "reply_audience",
    "quoted_post",
    "reposted_post",
    "gif_url",
    "is_spoiler_media",
    "text_entities",
    "text_attachment",
]
REPLY_FIELDS = [
    "id",
    "media_product_type",
    "media_type",
    "media_url",
    "permalink",
    "username",
    "text",
    "timestamp",
    "shortcode",
    "thumbnail_url",
    "children",
    "is_quote_post",
    "has_replies",
    "root_post",
    "replied_to",
    "is_reply",
    "is_reply_owned_by_me",
    "hide_status",
    "reply_audience",
    "quoted_post",
    "reposted_post",
    "gif_url",
    "topic_tag",
]
POST_METRICS = ["views", "likes", "replies", "reposts", "quotes", "shares"]
ACCOUNT_METRICS = [
    "views",
    "likes",
    "replies",
    "reposts",
    "quotes",
    "clicks",
    "followers_count",
    "follower_demographics",
]
ACCOUNT_DEFAULT_METRICS = [
    "views",
    "likes",
    "replies",
    "reposts",
    "quotes",
    "clicks",
    "followers_count",
]
WITHOUT_SINCE_UNTIL = {"followers_count", "follower_demographics"}
BREAKDOWNS = ["country", "city", "age", "gender"]
INSIGHTS_EARLIEST = 1712991600
LIMIT_FIELDS = [
    "quota_usage",
    "config",
    "reply_quota_usage",
    "reply_config",
    "delete_quota_usage",
    "delete_config",
    "location_search_quota_usage",
    "location_search_config",
]
_URL_IN_TEXT = re.compile(r"https?://[^\s]+|www\.[^\s]+", re.I)


# -- helpers -----------------------------------------------------------------------------


def _closed(given: Mapping[str, Any], allowed: set[str]) -> dict[str, Any]:
    rest = {k: v for k, v in given.items() if k != "connection_ref"}
    unknown = sorted(set(rest) - allowed)
    if unknown:
        raise invalid(f"The step input has unknown fields: {', '.join(unknown[:10])}")
    return rest


def _read(context: Context, operation_id: str, given: Mapping[str, Any]) -> Any:
    call = generic.prepare(operation_id, given)
    answer = context.transport.read(call)
    return generic.read_json(context, answer, call.shown)


def _write(context: Context, operation_id: str, given: Mapping[str, Any]) -> str:
    """One documented write that returns an ID (outcome table T, class needs_id)."""
    entry = generic.spec(operation_id)
    call = generic.prepare(operation_id, given)
    answer = context.transport.write(call)
    data = outcome.write_outcome(context, entry["write_class"], answer, call.shown)
    ident = outcome.identifier_of(data)
    if ident is None:  # pragma: no cover - write_outcome refuses an answer without one
        raise errors.no_effect(errors.INTERNAL_ERROR, "The write's answer carries no ID")
    return ident


def _bad(shown: str, what: str) -> ExtensionError:
    return errors.no_effect(
        errors.INVALID_RESPONSE,
        f"Threads' answer to {shown} {what}",
        failure_class="provider",
        retryable=False,
    )


def _field_list(given: Mapping[str, Any], default: list[str], allowed: list[str]) -> str:
    value = given.get("fields")
    if value in (None, "", []):
        return ",".join(default)
    return names({"allowed": allowed}, value, "fields")


def _documented_fields(operation_id: str) -> list[str]:
    """The fields the documentation lists for an endpoint (registry ``fields`` node)."""
    for prm in generic.spec(operation_id)["params"]:
        if prm["name"] == "fields":
            return list(prm["node"].get("allowed") or [])
    return []  # pragma: no cover - every list endpoint documents its fields


def _usage(context: Context, result: dict[str, Any]) -> dict[str, Any]:
    result["rate_limit_usage"] = context.transport.usage_report()
    return result


def _bool(given: Mapping[str, Any], name: str) -> bool | None:
    value = given.get(name)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise invalid(f"{name} must be true or false")
    return value


# -- connection and profile --------------------------------------------------------------


def test_connection(context: Context) -> dict[str, Any]:
    _closed(context.operation_input, set())
    data = _read(context, "get_user_profile", {"fields": "id,username,name"})
    if not isinstance(data, Mapping) or not isinstance(data.get("id"), str) or not data["id"]:
        raise _bad("GET /{threads-user-id}", "carries no user id")
    username = data.get("username")
    return _usage(
        context,
        {
            "connected": True,
            "user_id": errors.safe_text(data["id"], 64),
            "username": errors.safe_text(username, 100) if isinstance(username, str) else None,
            "warnings": [],
        },
    )


def get_my_profile(context: Context) -> dict[str, Any]:
    given = _closed(context.operation_input, {"fields"})
    allowed = [*PROFILE_FIELDS, "recently_searched_keywords"]
    data = _read(
        context,
        "get_user_profile",
        {"fields": _field_list(given, PROFILE_FIELDS, allowed)},
    )
    if not isinstance(data, Mapping):
        raise _bad("GET /{threads-user-id}", "is not a profile")
    return _usage(context, {"profile": dict(data), "warnings": []})


def _list_options(given: Mapping[str, Any], most_name: str) -> tuple[str | None, int]:
    return pages.options({"after": given.get("after"), "max_items": given.get(most_name)})


def list_my_posts(context: Context) -> dict[str, Any]:
    given = _closed(context.operation_input, {"since", "until", "fields", "after", "max_posts"})
    start, most = _list_options(given, "max_posts")
    query: dict[str, Any] = {
        "fields": _field_list(given, POST_FIELDS, _documented_fields("get_user_posts"))
    }
    for name in ("since", "until"):
        if given.get(name) not in (None, ""):
            query[name] = given[name]
    generic.prepare("get_user_posts", query)
    result = pages.collect(
        context, operation_id="get_user_posts", query=query, start=start, most=most, out_key="posts"
    )
    return _usage(context, result)


def list_post_replies(context: Context) -> dict[str, Any]:
    given = _closed(
        context.operation_input,
        {"post_id", "include_nested", "reverse", "fields", "after", "max_replies"},
    )
    nested = _bool(given, "include_nested")
    operation_id = "get_post_conversation" if nested else "get_post_replies"
    start, most = _list_options(given, "max_replies")
    query: dict[str, Any] = {
        "threads_media_id": given.get("post_id"),
        "fields": _field_list(given, REPLY_FIELDS, _documented_fields(operation_id)),
    }
    reverse = _bool(given, "reverse")
    if reverse is not None:
        query["reverse"] = reverse
    if query["threads_media_id"] in (None, ""):
        raise invalid("post_id is required")
    generic.prepare(operation_id, query)
    result = pages.collect(
        context, operation_id=operation_id, query=query, start=start, most=most, out_key="replies"
    )
    return _usage(context, result)


# -- publishing --------------------------------------------------------------------------


def _text_of(given: Mapping[str, Any], *, required: bool) -> str | None:
    value = given.get("text")
    if value in (None, ""):
        if required:
            raise invalid("text is required for a text post")
        return None
    if not isinstance(value, str):
        raise invalid("text must be text")
    if not value.strip():
        raise invalid("text is empty")
    if len(value) > TEXT_MAX:
        raise invalid(f"text is longer than the {TEXT_MAX} characters Threads allows")
    return value


def _alt_text(value: Any, what: str) -> str:
    return text(value, what, max_length=ALT_TEXT_MAX)


def _carousel_items(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not CAROUSEL_MIN <= len(value) <= CAROUSEL_MAX:
        raise invalid(f"items must be a list of {CAROUSEL_MIN} to {CAROUSEL_MAX} images or videos")
    out = []
    for i, item in enumerate(value, 1):
        what = f"items item {i}"
        if not isinstance(item, Mapping) or set(item) - {"image_url", "video_url", "alt_text"}:
            raise invalid(f"{what} must be an object with image_url or video_url and alt_text")
        has_image = item.get("image_url") not in (None, "")
        has_video = item.get("video_url") not in (None, "")
        if has_image == has_video:
            raise invalid(f"{what} needs exactly one of image_url and video_url")
        entry = {
            "media_type": "IMAGE" if has_image else "VIDEO",
            "url_field": "image_url" if has_image else "video_url",
            "url": url(item["image_url" if has_image else "video_url"], f"{what} address"),
        }
        if item.get("alt_text") not in (None, ""):
            entry["alt_text"] = _alt_text(item["alt_text"], f"{what} alt_text")
        out.append(entry)
    return out


PUBLISH_INPUTS = {
    "media_type",
    "text",
    "image_url",
    "video_url",
    "alt_text",
    "items",
    "link_attachment",
    "reply_control",
    "topic_tag",
    "quote_post_id",
    "location_id",
    "is_made_with_ai",
}
REPLY_INPUTS = {"reply_to_id", "text", "image_url", "video_url", "alt_text", "reply_control"}


def plan_post(given: Mapping[str, Any], *, reply_to: str | None = None) -> dict[str, Any]:
    """The checked containers of a post or reply: ``items`` (carousel children) and
    ``main`` (the container inputs of get_user_posts' sibling create_media_container)."""
    if reply_to is None:
        media_type = text(given.get("media_type") or "", "media_type", max_length=10)
        if media_type not in MEDIA_TYPES:
            raise invalid("media_type must be one of: " + ", ".join(MEDIA_TYPES))
    else:
        has_image = given.get("image_url") not in (None, "")
        has_video = given.get("video_url") not in (None, "")
        if has_image and has_video:
            raise invalid("Give image_url or video_url, not both")
        media_type = "IMAGE" if has_image else "VIDEO" if has_video else "TEXT"
    main: dict[str, Any] = {"media_type": media_type}
    items: list[dict[str, str]] = []
    body = _text_of(given, required=media_type == "TEXT")
    if body is not None:
        main["text"] = body
    for name, kind in (("image_url", "IMAGE"), ("video_url", "VIDEO")):
        value = given.get(name)
        if value not in (None, ""):
            if media_type != kind:
                raise invalid(f"{name} is for media_type {kind}")
            main[name] = url(value, name)
        elif media_type == kind:
            raise invalid(f"{name} is required for media_type {kind}")
    if given.get("alt_text") not in (None, ""):
        if media_type not in {"IMAGE", "VIDEO"}:
            raise invalid("alt_text is for an image or a video; give it per item of a carousel")
        main["alt_text"] = _alt_text(given["alt_text"], "alt_text")
    if media_type == "CAROUSEL":
        items = _carousel_items(given.get("items"))
    elif given.get("items") not in (None, [], ""):
        raise invalid("items is for media_type CAROUSEL")
    link = given.get("link_attachment")
    if link not in (None, ""):
        if media_type != "TEXT":
            raise invalid("link_attachment is for text posts only, as Threads documents")
        main["link_attachment"] = url(link, "link_attachment")
    links = set(_URL_IN_TEXT.findall(body or ""))
    if main.get("link_attachment"):
        links.add(main["link_attachment"])
    if len(links) > LINKS_MAX:
        raise invalid(f"A post may hold at most {LINKS_MAX} links; Threads refuses more")
    control = given.get("reply_control")
    if control not in (None, ""):
        if control not in REPLY_CONTROLS:
            raise invalid("reply_control must be one of: " + ", ".join(REPLY_CONTROLS))
        main["reply_control"] = control
    tag = given.get("topic_tag")
    if tag not in (None, ""):
        tag_text = text(tag, "topic_tag", max_length=TOPIC_TAG_MAX)
        if "." in tag_text or "&" in tag_text:
            raise invalid("topic_tag may not contain periods (.) or ampersands (&)")
        main["topic_tag"] = tag_text
    for name in ("quote_post_id", "location_id"):
        if given.get(name) not in (None, ""):
            main[name] = given[name]
    flag = _bool(given, "is_made_with_ai")
    if flag is not None:
        main["is_made_with_ai"] = flag
    if reply_to is not None:
        main["reply_to_id"] = reply_to
    # The container request is checked in full now (IDs, allowed values).
    generic.prepare("create_media_container", {**main, "children": ["1", "2"]} if items else main)
    return {"media_type": media_type, "main": main, "items": items}


def validate_publish(operation_input: Mapping[str, Any]) -> None:
    plan_post(_closed(operation_input, PUBLISH_INPUTS))


def validate_reply(operation_input: Mapping[str, Any]) -> None:
    given = _closed(operation_input, REPLY_INPUTS)
    plan_post(given, reply_to=_reply_to(given))


def _reply_to(given: Mapping[str, Any]) -> str:
    value = given.get("reply_to_id")
    if value in (None, ""):
        raise invalid("reply_to_id is required")
    generic.prepare("get_post", {"threads_media_id": value})
    return str(value).strip()


def _status(context: Context, container_id: str) -> tuple[str, str | None]:
    data = _read(
        context,
        "get_media_container_status",
        {"threads_container_id": container_id, "fields": "id,status,error_message"},
    )
    status = data.get("status") if isinstance(data, Mapping) else None
    if not isinstance(status, str) or not status:
        raise _bad("GET /{threads-container-id}", "carries no status")
    message = data.get("error_message")
    return status, errors.safe_text(message, 100) if isinstance(message, str) else None


def _wait(context: Context, container_id: str) -> tuple[str, str | None, int]:
    """The container's status, checked once a minute while it is IN_PROGRESS, at most
    five times and while the step's time allows."""
    checks = 0
    while True:
        status, message = _status(context, container_id)
        checks += 1
        if status != "IN_PROGRESS" or checks >= STATUS_CHECKS:
            return status, message, checks
        # Room for the pause, this status check and the publish request after it.
        if (
            context.transport.remaining()
            < STATUS_INTERVAL_SECONDS + 2 * MIN_CALL_WINDOW_SECONDS + 15
        ):
            return status, message, checks
        context.transport.sleep(STATUS_INTERVAL_SECONDS)


def _publish(context: Context, plan: Mapping[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    item_ids: list[str] = []
    for item in plan["items"]:
        fields = {"media_type": item["media_type"], item["url_field"]: item["url"]}
        if "alt_text" in item:
            fields["alt_text"] = item["alt_text"]
        fields["is_carousel_item"] = True
        item_ids.append(_write(context, "create_media_container", fields))
    main = dict(plan["main"])
    if item_ids:
        main["children"] = item_ids
    container_id = _write(context, "create_media_container", main)
    try:
        status, message, checks = _wait(context, container_id)
    except DeadlineReached:
        status, message, checks = "NOT_CHECKED", None, 0
        warnings.append("Time ran out before the container's status could be read")
    except ExtensionError as exc:
        if exc.definitely_no_external_effect is not True:
            raise
        status, message, checks = "NOT_CHECKED", None, 0
        warnings.append(f"The container's status could not be read ({exc.code}: {exc.message})")
    result: dict[str, Any] = {
        "post_id": None,
        "permalink": None,
        "container_id": container_id,
        "item_container_ids": item_ids,
        "container_status": status,
        "status_checks": checks,
        "warnings": warnings,
    }
    if status in {"ERROR", "EXPIRED"}:
        raise ExtensionError(
            errors.UPSTREAM_VALIDATION_FAILED,
            f"Threads created media container {container_id} but reports it {status}"
            + (f" ({message})" if message else "")
            + "; nothing was published. Fix the media and run the step again",
            failure_class="provider",
            retryable=False,
            definitely_no_external_effect=False,
            external_effect_status="timeout_unknown",
        )
    if status == "PUBLISHED":
        warnings.append(
            f"Threads reports media container {container_id} as already published; it was not "
            "published again. Read the post with Get user posts"
        )
        result.update(processing="completed", applied=True, check=None)
        return result
    if status != "FINISHED":
        warnings.append(
            f"Threads is still processing media container {container_id} ({status}) after "
            f"{checks} status checks; it is not published yet. Read its status with Get media "
            "container status and publish it with Publish media container when it is FINISHED"
        )
        result.update(
            processing="accepted",
            applied=False,
            check={"operation_id": "get_media_container_status", "container_id": container_id},
        )
        return result
    try:
        post_id = _write(context, "publish_media_container", {"creation_id": container_id})
    except DeadlineReached:
        # Raised before the publish request was sent.
        warnings.append(
            f"Media container {container_id} is FINISHED, but time ran out before it could be "
            "published; publish it with Publish media container"
        )
        result.update(
            processing="accepted",
            applied=False,
            check={"operation_id": "get_media_container_status", "container_id": container_id},
        )
        return result
    result.update(post_id=post_id, processing="completed", applied=True, check=None)
    try:
        data = _read(context, "get_post", {"threads_media_id": post_id, "fields": "id,permalink"})
        link = data.get("permalink") if isinstance(data, Mapping) else None
        result["permalink"] = link if isinstance(link, str) else None
    except (ExtensionError, DeadlineReached) as exc:
        reason = exc.message if isinstance(exc, ExtensionError) else "time ran out"
        warnings.append(
            f"The post was published, but its permalink could not be read ({reason}); read it "
            "with Get post"
        )
    return result


def publish_post(context: Context) -> dict[str, Any]:
    given = _closed(context.operation_input, PUBLISH_INPUTS)
    return _usage(context, _publish(context, plan_post(given)))


def reply_to_post(context: Context) -> dict[str, Any]:
    given = _closed(context.operation_input, REPLY_INPUTS)
    result = _publish(context, plan_post(given, reply_to=_reply_to(given)))
    result["reply_id"] = result.pop("post_id")
    return _usage(context, result)


# -- insights and limits -----------------------------------------------------------------


def _metric_values(data: Any, shown: str) -> dict[str, Any]:
    """Each metric's value: ``total_value.value``, the one value of ``values``, or the list
    (a time series, ``link_total_values``) as Threads returns it."""
    if not isinstance(data, Mapping) or not isinstance(data.get("data"), list):
        raise _bad(shown, "has no data list")
    out: dict[str, Any] = {}
    for item in data["data"]:
        if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
            raise _bad(shown, "lists a metric without a name")
        name = item["name"]
        if isinstance(item.get("total_value"), Mapping):
            out[name] = item["total_value"].get("value")
        elif (
            isinstance(item.get("values"), list)
            and len(item["values"]) == 1
            and isinstance(item["values"][0], Mapping)
        ):
            out[name] = item["values"][0].get("value")
        elif isinstance(item.get("values"), list):
            out[name] = item["values"]
        elif isinstance(item.get("link_total_values"), list):
            out[name] = item["link_total_values"]
        else:
            out[name] = None
    return out


def get_post_insights(context: Context) -> dict[str, Any]:
    given = _closed(context.operation_input, {"post_id", "metrics"})
    metric = names({"allowed": POST_METRICS}, given.get("metrics") or POST_METRICS, "metrics")
    if given.get("post_id") in (None, ""):
        raise invalid("post_id is required")
    data = _read(
        context, "get_media_insights", {"threads_media_id": given["post_id"], "metric": metric}
    )
    return _usage(
        context,
        {
            "metrics": _metric_values(data, "GET /{threads-media-id}/insights"),
            "data": generic.without_links(data),
            "warnings": [],
        },
    )


def get_account_insights(context: Context) -> dict[str, Any]:
    given = _closed(context.operation_input, {"metrics", "since", "until", "breakdown"})
    chosen = given.get("metrics") or ACCOUNT_DEFAULT_METRICS
    metric = names({"allowed": ACCOUNT_METRICS}, chosen, "metrics")
    query: dict[str, Any] = {"metric": metric}
    period = [n for n in ("since", "until") if given.get(n) not in (None, "")]
    for name in period:
        query[name] = moment({"minimum": INSIGHTS_EARLIEST}, given[name], name)
    if len(period) == 2 and timestamp_of(query["since"]) >= timestamp_of(query["until"]):
        raise invalid("since must be before until")
    warnings: list[str] = []
    if period and WITHOUT_SINCE_UNTIL & set(metric.split(",")):
        without = sorted(WITHOUT_SINCE_UNTIL & set(metric.split(",")))
        raise invalid(
            f"{', '.join(without)} do not take since and until, as Threads documents; read them "
            "in a step without a period"
        )
    breakdown = given.get("breakdown")
    if breakdown not in (None, ""):
        if breakdown not in BREAKDOWNS or "follower_demographics" not in metric.split(","):
            raise invalid(
                "breakdown is one of " + ", ".join(BREAKDOWNS) + " and needs follower_demographics"
            )
        query["breakdown"] = breakdown
    elif "follower_demographics" in metric.split(","):
        raise invalid("follower_demographics needs breakdown: " + ", ".join(BREAKDOWNS))
    data = _read(context, "get_user_insights", query)
    return _usage(
        context,
        {
            "metrics": _metric_values(data, "GET /{threads-user-id}/threads_insights"),
            "data": generic.without_links(data),
            "warnings": warnings,
        },
    )


def get_publishing_limit(context: Context) -> dict[str, Any]:
    _closed(context.operation_input, set())
    data = _read(context, "get_publishing_limit_usage", {"fields": ",".join(LIMIT_FIELDS)})
    rows = data.get("data") if isinstance(data, Mapping) else None
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], Mapping):
        raise _bad("GET /{threads-user-id}/threads_publishing_limit", "has no usage")
    row = rows[0]

    def pair(used: str, config: str) -> dict[str, Any]:
        value = row.get(config)
        settings: Mapping[str, Any] = value if isinstance(value, Mapping) else {}
        return {
            "used": row.get(used),
            "total": settings.get("quota_total"),
            "window_seconds": settings.get("quota_duration"),
        }

    return _usage(
        context,
        {
            "posts": pair("quota_usage", "config"),
            "replies": pair("reply_quota_usage", "reply_config"),
            "deletes": pair("delete_quota_usage", "delete_config"),
            "location_searches": pair("location_search_quota_usage", "location_search_config"),
            "warnings": [],
        },
    )


COMPOSITES: dict[str, Callable[[Context], dict[str, Any]]] = {
    "test_connection": test_connection,
    "get_my_profile": get_my_profile,
    "list_my_posts": list_my_posts,
    "publish_post": publish_post,
    "reply_to_post": reply_to_post,
    "list_post_replies": list_post_replies,
    "get_post_insights": get_post_insights,
    "get_account_insights": get_account_insights,
    "get_publishing_limit": get_publishing_limit,
}
COMPOSITE_WRITES: frozenset[str] = frozenset({"publish_post", "reply_to_post"})
VALIDATORS: dict[str, Callable[[Mapping[str, Any]], None]] = {
    "publish_post": validate_publish,
    "reply_to_post": validate_reply,
}

__all__ = ["COMPOSITES", "COMPOSITE_WRITES", "VALIDATORS", "plan_post"]
