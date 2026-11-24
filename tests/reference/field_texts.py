"""One label for each input name, and one description for inputs that mean the same in
every step.

A step's form shows the label and the description. An input with the same name has the
same label in every step (``LABELS``, otherwise the name in words); an input that means
the same in every step also has the same description (``SAME``). An input whose meaning
depends on the method (``part``, ``id``, ``mine``) keeps the description the source gives
for that method; where the source gives none, ``FALLBACK`` says it.
"""

from __future__ import annotations

_WORDS = {"id": "ID", "ids": "IDs", "url": "URL", "html": "HTML", "ig": "Instagram"}

LABELS: dict[str, str] = {
    "after": "After cursor",
    "before": "Before cursor",
    "since": "Since",
    "until": "Until",
    "limit": "Page size",
    "fields": "Fields",
    "q": "Search query",
    "query": "Search query",
    "media_type": "Media type",
    "text": "Text",
    "image_url": "Image URL",
    "video_url": "Video URL",
    "alt_text": "Alternative text",
    "link_attachment": "Link attachment",
    "reply_control": "Who can reply",
    "topic_tag": "Topic",
    "quote_post_id": "Quote post ID",
    "location_id": "Location ID",
    "is_made_with_ai": "Made with AI",
    "reply_to_id": "Reply to ID",
    "reverse": "Newest first",
    "post_id": "Post ID",
    "metric": "Metric",
    "metrics": "Metrics",
    "breakdown": "Breakdown",
    "threads_user_id": "Threads user ID",
    "threads_media_id": "Post ID",
    "threads_container_id": "Media container ID",
    "threads_reply_id": "Reply ID",
    "maxwidth": "Max width",
    "all_pages": "All pages",
    "max_items": "Most records",
    "max_posts": "Most posts",
    "max_replies": "Most replies",
    "items": "Carousel items",
    "children": "Carousel item IDs",
    "creation_id": "Media container ID",
    "url": "Post URL",
    "username": "Username",
    "author_username": "Author username",
}

SAME: dict[str, str] = {
    "after": (
        "A cursor to continue from: next_after of an earlier run, or an after cursor Threads "
        "returned. Empty: from the start. Not together with before."
    ),
    "before": "A cursor Threads returned, to read the page before it. Not together with after.",
    "since": (
        "Only from this moment: a Unix timestamp such as 1767225600, or a date and time such "
        "as 2026-01-01T00:00:00Z."
    ),
    "until": (
        "Only until this moment, after since: a Unix timestamp, or a date and time such as "
        "2026-01-31T23:59:59Z."
    ),
    "limit": "The most records Threads returns in one page (Threads' default 25, at most 100).",
}

FALLBACK: dict[str, str] = {}


def label_of(name: str) -> str:
    """The label of an input: LABELS, or its name in words."""
    if name in LABELS:
        return LABELS[name]
    words = [_WORDS.get(w, w) for w in name.split("_")]
    text = " ".join(words)
    return text[:1].upper() + text[1:]


def text_of(name: str, description: str | None) -> tuple[str, str]:
    """(label, description) of one input."""
    label = label_of(name)
    if name in SAME:
        return label, SAME[name]
    given = (description or "").strip()
    raw = name.replace("_", "")
    if not given or given.lower().replace(" ", "") in {raw, name.lower()}:
        given = FALLBACK.get(name, "")
    if not given:
        raise ValueError(f"No description for input {name}")
    return label, given
