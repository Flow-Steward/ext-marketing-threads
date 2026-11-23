"""Inputs and outputs of the everyday steps (runtime/composites.py), for the contracts."""

from __future__ import annotations

from typing import Any

WARNINGS: dict[str, Any] = {
    "name": "warnings",
    "type": "array",
    "items": {"type": "string"},
    "description": "What the step could not do fully or what to check.",
}
USAGE: dict[str, Any] = {
    "name": "rate_limit_usage",
    "type": ["object", "null"],
    "additionalProperties": True,
    "description": (
        "The rate-limit usage Threads reported with the last answer, by header (X-App-Usage, "
        "X-Business-Use-Case-Usage: percentages of the limit used); empty when Threads sent none."
    ),
}
PROCESSING: list[dict[str, Any]] = [
    {
        "name": "processing",
        "type": ["string", "null"],
        "enum": ["completed", "accepted", None],
        "description": (
            "completed: Threads made the change. accepted: Threads created the media container "
            "and is still processing it; nothing is published yet, check its status with the "
            "step named in check. Empty in a test run and when nothing was sent."
        ),
    },
    {
        "name": "applied",
        "type": ["boolean", "null"],
        "description": "True with processing completed; false with accepted, in a test run and when nothing was sent.",
    },
    {
        "name": "check",
        "type": ["object", "null"],
        "additionalProperties": True,
        "description": "With processing accepted: operation_id, the step that reads the container's status, and container_id.",
    },
]
EFFECT = [
    {"name": "external_effect_status", "type": "string"},
    {"name": "definitely_no_external_effect", "type": "boolean"},
]


def _list(name: str, what: str) -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "type": "array",
            "items": {"type": "object", "additionalProperties": True},
            "description": what,
        },
        {"name": "count", "type": "integer", "description": "How many were returned."},
        {
            "name": "complete",
            "type": "boolean",
            "description": "True when the list was read to its end.",
        },
        {
            "name": "next_after",
            "type": ["string", "null"],
            "description": "When complete is false: run the step again with after set to this cursor for the rest.",
        },
    ]


AFTER = {
    "name": "after",
    "type": "string",
    "maxLength": 2048,
    "title": "Continue after",
    "description": "next_after of an earlier run, to continue where it stopped. Empty: from the start.",
}


def _most(name: str, default: int) -> dict[str, Any]:
    return {
        "name": name,
        "type": "integer",
        "minimum": 1,
        "maximum": 100000,
        "title": "At most",
        "description": f"The most to read in this step. Default {default}.",
    }


SINCE = {
    "name": "since",
    "type": "string",
    "maxLength": 20,
    "title": "Since",
    "description": "Only from this moment: a Unix timestamp such as 1767225600 or a date such as 2026-01-01.",
}
UNTIL = {
    "name": "until",
    "type": "string",
    "maxLength": 20,
    "title": "Until",
    "description": "Only until this moment, after since: a Unix timestamp or a date such as 2026-01-31.",
}
REPLY_CONTROL = {
    "name": "reply_control",
    "type": "string",
    "enum": [
        "everyone",
        "accounts_you_follow",
        "mentioned_only",
        "parent_post_author_only",
        "followers_only",
    ],
    "title": "Who can reply",
    "description": "Who can reply to the post. Default: everyone.",
}
TEXT = {
    "name": "text",
    "type": "string",
    "maxLength": 500,
    "title": "Text",
    "description": "The text of the post, up to 500 characters (Threads counts an emoji as its UTF-8 bytes). Required for a text post.",
}
IMAGE_URL = {
    "name": "image_url",
    "type": "string",
    "maxLength": 2000,
    "title": "Image address",
    "description": "A public address of a JPEG or PNG image (up to 8 MB). Threads downloads it from there.",
}
VIDEO_URL = {
    "name": "video_url",
    "type": "string",
    "maxLength": 2000,
    "title": "Video address",
    "description": "A public address of an MP4 or MOV video (up to 1 GB, 5 minutes). Threads downloads it from there.",
}
ALT_TEXT = {
    "name": "alt_text",
    "type": "string",
    "maxLength": 1000,
    "title": "Alternative text",
    "description": "A description of the image or video for people who cannot see it, up to 1000 characters.",
}
PUBLISH_OUT = [
    {
        "name": "permalink",
        "type": ["string", "null"],
        "description": "The post's address on Threads, read after publishing.",
    },
    {
        "name": "container_id",
        "type": ["string", "null"],
        "description": "The media container Threads created for the post.",
    },
    {
        "name": "item_container_ids",
        "type": "array",
        "items": {"type": "string"},
        "description": "The containers of a carousel's images and videos.",
    },
    {
        "name": "container_status",
        "type": ["string", "null"],
        "description": "The container's last status: FINISHED, IN_PROGRESS, PUBLISHED, or NOT_CHECKED when it could not be read.",
    },
    {
        "name": "status_checks",
        "type": "integer",
        "description": "How many times the container's status was read.",
    },
]

COMPOSITES: list[dict[str, Any]] = [
    {
        "operation_id": "test_connection",
        "title": "Test connection",
        "kind": "read",
        "calls": ["GET /{threads-user-id}"],
        "description": (
            "Checks the connection: reads the account it belongs to (GET /me with id, username "
            "and name) and returns its user ID and username. Needs threads_basic."
        ),
        "inputs": [],
        "outputs": [
            {
                "name": "connected",
                "type": "boolean",
                "description": "True when Threads accepted the token.",
            },
            {
                "name": "user_id",
                "type": ["string", "null"],
                "description": "The Threads user ID of the account.",
            },
            {
                "name": "username",
                "type": ["string", "null"],
                "description": "The account's Threads username.",
            },
            WARNINGS,
            USAGE,
        ],
    },
    {
        "operation_id": "get_my_profile",
        "title": "Get my profile",
        "kind": "read",
        "calls": ["GET /{threads-user-id}"],
        "description": (
            "Reads the connected account's Threads profile: ID, username, name, profile picture, "
            "biography and whether it is verified (or the fields you choose, including "
            "recently_searched_keywords). Needs threads_basic."
        ),
        "inputs": [
            {
                "name": "fields",
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "id",
                        "username",
                        "name",
                        "threads_profile_picture_url",
                        "threads_biography",
                        "is_verified",
                        "recently_searched_keywords",
                    ],
                },
                "title": "Fields",
                "description": "The profile fields to read. Default: all but recently_searched_keywords.",
            }
        ],
        "outputs": [
            {
                "name": "profile",
                "type": "object",
                "additionalProperties": True,
                "description": "The profile as Threads returns it.",
            },
            WARNINGS,
            USAGE,
        ],
    },
    {
        "operation_id": "list_my_posts",
        "title": "Get all my posts",
        "kind": "read",
        "calls": ["GET /{threads-user-id}/threads"],
        "description": (
            "Reads the connected account's posts page by page (GET /me/threads, 100 per page) "
            "until all are read, the step output is full, the asked maximum is reached or time "
            "runs out; then it returns what it read with complete false and next_after to "
            "continue from. Optionally only posts from since to until. Each post has every "
            "documented field unless you choose fewer. Needs threads_basic."
        ),
        "inputs": [
            SINCE,
            UNTIL,
            {
                "name": "fields",
                "type": "array",
                "items": {"type": "string"},
                "title": "Fields",
                "description": "The post fields to read. Default: every documented field of a post.",
            },
            AFTER,
            _most("max_posts", 10000),
        ],
        "outputs": [
            *_list("posts", "The posts, newest first, as Threads returns them."),
            WARNINGS,
            USAGE,
        ],
    },
    {
        "operation_id": "publish_post",
        "title": "Publish a post",
        "kind": "write",
        "calls": [
            "POST /{threads-user-id}/threads",
            "GET /{threads-container-id}",
            "POST /{threads-user-id}/threads_publish",
            "GET /{threads-media-id}",
        ],
        "description": (
            "Publishes a text, image, video or carousel post on the connected account, as Threads "
            "documents it: creates the media container (for a carousel one container per image or "
            "video first), reads its status once a minute until it is FINISHED (at most five "
            "times, as Threads recommends) and publishes it. Images and videos are public "
            "addresses that Threads downloads. Returns the post ID and permalink. When Threads "
            "is still processing the media, the step returns processing accepted and the "
            "container ID: publish it later with Publish media container. Needs threads_basic "
            "and threads_content_publish. Threads allows 250 published posts per 24 hours."
        ),
        "inputs": [
            {
                "name": "media_type",
                "type": "string",
                "enum": ["TEXT", "IMAGE", "VIDEO", "CAROUSEL"],
                "title": "Kind of post",
                "description": "TEXT, IMAGE, VIDEO or CAROUSEL (2 to 20 images and videos).",
                "required": True,
            },
            TEXT,
            IMAGE_URL,
            VIDEO_URL,
            ALT_TEXT,
            {
                "name": "items",
                "type": "array",
                "items": {"type": "object", "additionalProperties": False},
                "minItems": 2,
                "maxItems": 20,
                "title": "Carousel items",
                "description": 'For a carousel: 2 to 20 objects, each with image_url or video_url and optional alt_text, such as [{"image_url": "https://example.com/1.jpg"}].',
            },
            {
                "name": "link_attachment",
                "type": "string",
                "maxLength": 2000,
                "title": "Link preview",
                "description": "A public address shown as a link preview; text posts only. A post may hold at most 5 links.",
            },
            REPLY_CONTROL,
            {
                "name": "topic_tag",
                "type": "string",
                "maxLength": 50,
                "title": "Topic",
                "description": "One topic for the post, 1 to 50 characters, without periods or ampersands.",
            },
            {
                "name": "quote_post_id",
                "type": "string",
                "maxLength": 30,
                "title": "Quote post ID",
                "description": "The ID of a post to quote.",
            },
            {
                "name": "location_id",
                "type": "string",
                "maxLength": 30,
                "title": "Location ID",
                "description": "A location to tag, from Search locations (needs threads_location_tagging).",
            },
            {
                "name": "is_made_with_ai",
                "type": "boolean",
                "title": "Made with AI",
                "description": "True to show the AI info label on the post.",
            },
        ],
        "outputs": [
            {
                "name": "post_id",
                "type": ["string", "null"],
                "description": "The ID of the published post.",
            },
            *PUBLISH_OUT,
            *PROCESSING,
            WARNINGS,
            USAGE,
            *EFFECT,
        ],
    },
    {
        "operation_id": "reply_to_post",
        "title": "Reply to a post",
        "kind": "write",
        "calls": [
            "POST /{threads-user-id}/threads",
            "GET /{threads-container-id}",
            "POST /{threads-user-id}/threads_publish",
            "GET /{threads-media-id}",
        ],
        "description": (
            "Publishes a reply to a post or to another reply: text, or an image or video with "
            "optional text, through the same container, status and publish requests as Publish "
            "a post (reply_to_id). Returns the reply ID and permalink, or processing accepted "
            "and the container ID when Threads is still processing the media. Needs "
            "threads_basic, threads_content_publish and threads_manage_replies. Threads allows "
            "1000 replies per 24 hours."
        ),
        "inputs": [
            {
                "name": "reply_to_id",
                "type": "string",
                "maxLength": 30,
                "title": "Reply to",
                "description": "The ID of the post or reply to answer.",
                "required": True,
            },
            TEXT,
            IMAGE_URL,
            VIDEO_URL,
            ALT_TEXT,
            REPLY_CONTROL,
        ],
        "outputs": [
            {
                "name": "reply_id",
                "type": ["string", "null"],
                "description": "The ID of the published reply.",
            },
            *PUBLISH_OUT,
            *PROCESSING,
            WARNINGS,
            USAGE,
            *EFFECT,
        ],
    },
    {
        "operation_id": "list_post_replies",
        "title": "Get all replies to a post",
        "kind": "read",
        "calls": ["GET /{threads-media-id}/replies", "GET /{threads-media-id}/conversation"],
        "description": (
            "Reads the replies to a post page by page until all are read: the top-level replies "
            "(GET /{id}/replies), or with include_nested every reply at every level "
            "(GET /{id}/conversation). Stops with complete false and next_after when the output "
            "is full, the maximum is reached or time runs out. Needs threads_basic and "
            "threads_read_replies."
        ),
        "inputs": [
            {
                "name": "post_id",
                "type": "string",
                "maxLength": 30,
                "title": "Post ID",
                "description": "The post whose replies to read.",
                "required": True,
            },
            {
                "name": "include_nested",
                "type": "boolean",
                "title": "Nested replies too",
                "description": "True for replies at every level (the conversation), false or empty for top-level replies.",
            },
            {
                "name": "reverse",
                "type": "boolean",
                "title": "Newest first",
                "description": "True (Threads' default) for reverse chronological order, false for oldest first.",
            },
            {
                "name": "fields",
                "type": "array",
                "items": {"type": "string"},
                "title": "Fields",
                "description": "The reply fields to read. Default: every documented field of a reply.",
            },
            AFTER,
            _most("max_replies", 10000),
        ],
        "outputs": [*_list("replies", "The replies, as Threads returns them."), WARNINGS, USAGE],
    },
    {
        "operation_id": "get_post_insights",
        "title": "Get post insights",
        "kind": "read",
        "calls": ["GET /{threads-media-id}/insights"],
        "description": (
            "Reads a post's metrics: views, likes, replies, reposts, quotes and shares (or the ones "
            "you choose), each as one number in metrics. Needs threads_basic and "
            "threads_manage_insights."
        ),
        "inputs": [
            {
                "name": "post_id",
                "type": "string",
                "maxLength": 30,
                "title": "Post ID",
                "description": "The post to read the metrics of.",
                "required": True,
            },
            {
                "name": "metrics",
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["views", "likes", "replies", "reposts", "quotes", "shares"],
                },
                "title": "Metrics",
                "description": "Default: all six.",
            },
        ],
        "outputs": [
            {
                "name": "metrics",
                "type": "object",
                "additionalProperties": True,
                "description": "Each metric's value by name.",
            },
            {
                "name": "data",
                "type": ["object", "null"],
                "additionalProperties": True,
                "description": "Threads' answer as it came (names, periods, titles).",
            },
            WARNINGS,
            USAGE,
        ],
    },
    {
        "operation_id": "get_account_insights",
        "title": "Get account insights",
        "kind": "read",
        "calls": ["GET /{threads-user-id}/threads_insights"],
        "description": (
            "Reads the connected account's metrics: views (a value per day), likes, replies, "
            "reposts, quotes, link clicks and followers, or follower demographics by country, "
            "city, age or gender. Optionally from since to until (from 13 April 2024; followers "
            "and demographics take no period). Without a period Threads reads yesterday and "
            "today. Needs threads_basic and threads_manage_insights."
        ),
        "inputs": [
            {
                "name": "metrics",
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "views",
                        "likes",
                        "replies",
                        "reposts",
                        "quotes",
                        "clicks",
                        "followers_count",
                        "follower_demographics",
                    ],
                },
                "title": "Metrics",
                "description": "Default: all but follower_demographics.",
            },
            SINCE,
            UNTIL,
            {
                "name": "breakdown",
                "type": "string",
                "enum": ["country", "city", "age", "gender"],
                "title": "Demographics by",
                "description": "Required with follower_demographics (accounts with at least 100 followers).",
            },
        ],
        "outputs": [
            {
                "name": "metrics",
                "type": "object",
                "additionalProperties": True,
                "description": "Each metric by name: one number, or the list Threads returns (views per day, clicks per link).",
            },
            {
                "name": "data",
                "type": ["object", "null"],
                "additionalProperties": True,
                "description": "Threads' answer as it came.",
            },
            WARNINGS,
            USAGE,
        ],
    },
    {
        "operation_id": "get_publishing_limit",
        "title": "Get publishing limits",
        "kind": "read",
        "calls": ["GET /{threads-user-id}/threads_publishing_limit"],
        "description": (
            "Reads how much of its 24-hour limits the connected account has used: posts (250), "
            "replies (1000), deletions (100) and location searches (500), each with the limit and "
            "its window, as Threads reports them. Needs threads_basic and threads_content_publish "
            "(replies also threads_manage_replies, deletions threads_delete, location searches "
            "threads_location_tagging)."
        ),
        "inputs": [],
        "outputs": [
            {
                "name": name,
                "type": "object",
                "additionalProperties": True,
                "description": f"{label}: used, total and window_seconds.",
            }
            for name, label in (
                ("posts", "Published posts"),
                ("replies", "Published replies"),
                ("deletes", "Deleted posts"),
                ("location_searches", "Location searches"),
            )
        ]
        + [WARNINGS, USAGE],
    },
]
