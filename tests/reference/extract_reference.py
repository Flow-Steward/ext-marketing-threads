#!/usr/bin/env python3
"""Pin the facts this extension uses from Meta's Threads API documentation.

Threads publishes no machine-readable specification. Its documentation pages at
https://developers.facebook.com/documentation/threads/ are served as Markdown when
``.md`` is added to the address; this script reads saved copies of those pages and
of two Graph API pages (error responses and rate-limit headers, which the Threads
pages do not describe themselves), and writes what the steps are built from.

The pages are not committed. Download each address of ``PAGES`` to
``tests/reference/sources/<name>`` (Threads pages: the ``.md`` address; Graph pages:
the HTML page), then run from the bundle root:

    python3 tests/reference/extract_reference.py

Each page is reduced to its content first (the Markdown inside the page's ``<pre>``,
or the text of a Graph page) and its SHA-256 compared with the pinned one, so a
changed page is noticed rather than silently picked up. Output:
tests/reference/threads_api.json — every documented endpoint with its parameters,
the documented limits, permissions, container statuses, the error form and the
rate-limit headers. Nothing is guessed here; build_contracts.py decides what the
steps do.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources"
OUTPUT = HERE / "threads_api.json"
DOWNLOADED = "2026-11-23"
THREADS_DOCS = "https://developers.facebook.com/documentation/threads/"
GRAPH_DOCS = "https://developers.facebook.com/docs/graph-api/"

#: name -> address. The SHA-256 of each page's content (as ``content`` reduces it) is
#: pinned in pins.json.
PAGES: dict[str, str] = {
    "reference_publishing.md": THREADS_DOCS + "reference/publishing.md",
    "reference_media-retrieval.md": THREADS_DOCS + "reference/media-retrieval.md",
    "reference_reply-management.md": THREADS_DOCS + "reference/reply-management.md",
    "reference_user.md": THREADS_DOCS + "reference/user.md",
    "reference_locations.md": THREADS_DOCS + "reference/locations.md",
    "reference_location-search.md": THREADS_DOCS + "reference/location-search.md",
    "reference_insights.md": THREADS_DOCS + "reference/insights.md",
    "reference_oembed.md": THREADS_DOCS + "reference/oembed.md",
    "reference_debug.md": THREADS_DOCS + "reference/debug.md",
    "overview.md": THREADS_DOCS + "overview.md",
    "posts.md": THREADS_DOCS + "posts.md",
    "troubleshooting.md": THREADS_DOCS + "troubleshooting.md",
    "reply-management.md": THREADS_DOCS + "reply-management.md",
    "keyword-search.md": THREADS_DOCS + "keyword-search.md",
    "trending-topics.md": THREADS_DOCS + "trending-topics.md",
    "posts_reposts.md": THREADS_DOCS + "posts/reposts.md",
    "posts_delete-posts.md": THREADS_DOCS + "posts/delete-posts.md",
    "posts_accessibility.md": THREADS_DOCS + "posts/accessibility.md",
    "insights.md": THREADS_DOCS + "insights.md",
    "threads-mentions.md": THREADS_DOCS + "threads-mentions.md",
    "threads-profiles.md": THREADS_DOCS + "threads-profiles.md",
    "create-posts_location-tagging.md": THREADS_DOCS + "create-posts/location-tagging.md",
    "retrieve-and-discover-posts_retrieve-posts.md": THREADS_DOCS
    + "retrieve-and-discover-posts/retrieve-posts.md",
    "retrieve-and-manage-replies_retrieve-replies.md": THREADS_DOCS
    + "retrieve-and-manage-replies/retrieve-replies.md",
    "retrieve-and-manage-replies_create-replies.md": THREADS_DOCS
    + "retrieve-and-manage-replies/create-replies.md",
    "get-started_get-access-tokens-and-permissions.md": THREADS_DOCS
    + "get-started/get-access-tokens-and-permissions.md",
    "get-started_long-lived-tokens.md": THREADS_DOCS + "get-started/long-lived-tokens.md",
    "get-started_app-access-tokens.md": THREADS_DOCS + "get-started/app-access-tokens.md",
    "webhooks.md": THREADS_DOCS + "webhooks.md",
    "create-posts_polls.md": THREADS_DOCS + "create-posts/polls.md",
    "get-started.md": THREADS_DOCS + "get-started.md",
    "get-started_create-an-app.md": THREADS_DOCS + "get-started/create-an-app.md",
    "posts_geo-gating.md": THREADS_DOCS + "posts/geo-gating.md",
    "graph_error-handling.html": GRAPH_DOCS + "guides/error-handling",
    "graph_rate-limiting.html": GRAPH_DOCS + "overview/rate-limiting",
}
#: Written by ``--pin`` once, after the pages were downloaded and read; then fixed.
PINS_FILE = HERE / "pins.json"

REFERENCE_PAGES = (
    "reference_publishing.md",
    "reference_media-retrieval.md",
    "reference_reply-management.md",
    "reference_user.md",
    "reference_locations.md",
    "reference_location-search.md",
    "reference_insights.md",
    "reference_oembed.md",
    "reference_debug.md",
)
#: Parameters a guide page documents for an endpoint and its reference page does not:
#: (method, path) -> (page, the section heading the table is under).
SUPPLEMENTS: dict[tuple[str, str], tuple[str, str]] = {
    ("GET", "/{threads-media-id}/pending_replies"): (
        "reply-management.md",
        "### Retrieve pending replies",
    ),
}
#: Endpoints documented only on guide pages: (method, path, page, the words that show it).
GUIDE_ENDPOINTS: tuple[tuple[str, str, str, str], ...] = (
    ("GET", "/trending_topics", "trending-topics.md", "GET graph.threads.com/trending_topics"),
    ("GET", "/{trend-id}/posts", "trending-topics.md", "GET graph.threads.com/{trend-id}/posts"),
    (
        "POST",
        "/oauth/access_token",
        "get-started_get-access-tokens-and-permissions.md",
        "POST https://graph.threads.com/oauth/access_token",
    ),
    ("GET", "/access_token", "get-started_long-lived-tokens.md", "GET /access_token"),
    (
        "GET",
        "/refresh_access_token",
        "get-started_long-lived-tokens.md",
        "GET /refresh_access_token",
    ),
)


class _Text(HTMLParser):
    """The visible text of an HTML page, one block per line."""

    BLOCKS = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "pre", "br", "table"}

    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if tag in self.BLOCKS:
            self.out.append("\n")
        if tag in {"td", "th"}:
            self.out.append(" | ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.out.append(data)


def content(name: str, raw: bytes) -> str:
    """What a page says, without what changes on every download (nonces, scripts)."""
    text = raw.decode("utf-8")
    if name.endswith(".md"):
        match = re.search(r'<pre data-testid="developer-docs-markdown-page">(.*)</pre>', text, re.S)
        if match is None:
            raise SystemExit(f"{name}: not a Markdown documentation page")
        return html.unescape(match.group(1))
    parser = _Text()
    parser.feed(text)
    joined = re.sub(r"[ \t]+", " ", "".join(parser.out))
    return re.sub(r"\n\s*\n+", "\n", joined)


def pins() -> dict[str, str]:
    return json.loads(PINS_FILE.read_text(encoding="utf-8")) if PINS_FILE.exists() else {}


def load(name: str, *, pin: bool = False) -> tuple[str, dict[str, Any]]:
    raw = (SOURCES / name).read_bytes()
    text = content(name, raw)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    pinned = pins().get(name)
    if not pin and digest != pinned:
        raise SystemExit(f"{name}: the page changed (SHA-256 {digest}, pinned {pinned})")
    return text, {"name": name, "url": PAGES[name], "sha256": digest, "chars": len(text)}


# -- reference pages -------------------------------------------------------------------


_HEADING = re.compile(r"^## `(GET|POST|DELETE) ([^`]+)`", re.M)
_ROW = re.compile(r"^\| `([A-Za-z0-9_.-]+)`(?:<br>)*\s*([^|]*?)\s*\| (.*) \|\s*$", re.M)
_USES = re.compile(r"This endpoint also uses these \[common parameters\][^:]*: (.+)\.")


def _plain(text: str) -> str:
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    value = value.replace("<br>", " ").replace("**", "").replace("*", "")
    return " ".join(value.split())


def _values(cell: str) -> tuple[list[str], str | None]:
    """The values a parameter takes (``**Values:**`` list) and its default."""
    found = re.search(r"(?:\*\*Values?:\*\*|Accepted values:)(.*?)(?:\*\*Note|$)", cell, re.S)
    if not found:
        return [], None
    # Inline values end with their line ("<br>" or a new line); a bulleted list does not.
    part = found.group(1)
    if "<br>* `" not in part:
        part = re.split(r"<br>|\n", part.strip(), maxsplit=1)[0]
    values: list[str] = []
    default = None
    listed = "<br>* `" in part
    item = r"(?:^|<br>|\n)\s*\* `([^`]+)`" if listed else r"`([^`]+)`"
    for match in re.finditer(item + r"(\s*\*\(default[^)]*\)\*)?", part):
        values.append(match.group(1))
        if match.group(2):
            default = match.group(1)
    return values, default


def _param(name: str, kind: str, cell: str, place: str) -> dict[str, Any]:
    values, default = _values(cell)
    if kind.strip().lower() == "boolean" and not values:
        values = []
    earliest = re.search(r"on or after `(\d+)`", cell)
    between = re.search(r"between (\d+) and (\d+)", cell)
    maximum = re.search(r"The default is `(\d+)` and the maximum is `(\d+)`", cell)
    return {
        "name": name,
        "in": place,
        "range": [int(between.group(1)), int(between.group(2))] if between else None,
        "earliest": int(earliest.group(1)) if earliest else None,
        "default_and_maximum": [int(maximum.group(1)), int(maximum.group(2))] if maximum else None,
        "type": " ".join(kind.replace("<br>", " ").split()),
        "required": cell.lstrip().startswith("**Required.**"),
        "values": values,
        "default": default,
        "description": _plain(re.sub(r"^\*\*(Required|Optional)\.\*\*", "", cell.strip()))[:900],
    }


def _table(block: str) -> list[tuple[str, str, str]]:
    return [(m.group(1), m.group(2), m.group(3)) for m in _ROW.finditer(block)]


def _common(text: str) -> dict[str, tuple[str, str]]:
    found = re.search(r"## Common parameters\n(.*?)\n## ", text, re.S)
    if not found:
        return {}
    return {name: (kind, cell) for name, kind, cell in _table(found.group(1))}


def _split(heading: str) -> tuple[str, dict[str, str]]:
    """``/{id}?fields=status`` -> (``/{id}``, {fields: status}); ``?url=...`` keeps no value."""
    path, _, query = heading.partition("?")
    fixed = {}
    for pair in query.split("&") if query else []:
        key, _, value = pair.partition("=")
        if value and value != "...":
            fixed[key] = value
    return path.strip(), fixed


def reference_operations(texts: dict[str, str]) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for page in REFERENCE_PAGES:
        text = texts[page]
        common = _common(text)
        heads = list(_HEADING.finditer(text))
        for index, head in enumerate(heads):
            end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
            block = text[head.end() : end]
            method = head.group(1)
            path, fixed = _split(head.group(2))
            summary = _plain(block.strip().split("\n", 1)[0])
            params: list[dict[str, Any]] = []
            uses = _USES.search(block)
            used = re.findall(r"`([^`]+)`", uses.group(1)) if uses else []
            path_names = set(re.findall(r"\{([^}]+)\}", path))
            body_place = "form" if method == "POST" else "query"
            for name in used:
                if name != "access_token" and name in common:
                    kind, cell = common[name]
                    params.append(_param(name, kind, cell, "query"))
            for name, kind, cell in _table(block.split("### Fields", 1)[0]):
                if name == "access_token":
                    continue
                place = "path" if name in path_names else body_place
                if method == "GET" or name in path_names:
                    place = "path" if name in path_names else "query"
                params.append(_param(name, kind, cell, place))
            token = (
                any(n == "access_token" for n, _, _ in _table(block.split("### Fields", 1)[0]))
                or "access_token" in used
            )
            fields = []
            if "### Fields" in block:
                fields = [name for name, _, _ in _table(block.split("### Fields", 1)[1])]
            operations.append(
                {
                    "method": method,
                    "path": path,
                    "heading": head.group(2).split("`")[0],
                    "fixed_query": fixed,
                    "page": page,
                    "summary": summary,
                    "params": params,
                    "token_documented": token,
                    "answer_fields": fields,
                }
            )
    for (method, path), (page, section) in SUPPLEMENTS.items():
        op = next(o for o in operations if o["method"] == method and o["path"] == path)
        text = texts[page]
        start = text.index(section)
        rest = text[start + len(section) :]
        # The first table after the heading: its parameters, not its returned fields.
        table = re.search(r"(?:^\|.*\n)+", rest, re.M)
        rest = table.group(0) if table else ""
        have = {p["name"] for p in op["params"]}
        for name, kind, cell in _table(rest):
            if name not in have:
                added = _param(name, kind, cell, "query")
                added["source"] = f"{page} ({section.lstrip('# ')})"
                op["params"].append(added)
    return operations


def guide_operations(texts: dict[str, str]) -> list[dict[str, Any]]:
    out = []
    for method, path, page, words in GUIDE_ENDPOINTS:
        if words not in texts[page]:
            raise SystemExit(f"{page}: does not show {words}")
        out.append({"method": method, "path": path, "page": page, "shown_as": words})
    return out


# -- facts from the guides ---------------------------------------------------------------


def _find(pattern: str, text: str, flags: int = 0) -> str:
    """The first group of ``pattern`` in ``text``; a page without it is refused."""
    found = re.search(pattern, text, flags)
    if not found:
        raise SystemExit(f"not found: {pattern}")
    return found.group(1)


def _number(text: str, pattern: str) -> int:
    found = re.search(pattern, text)
    if not found:
        raise SystemExit(f"not found: {pattern}")
    return int(found.group(1).replace(",", ""))


def limits(texts: dict[str, str]) -> dict[str, Any]:
    overview = texts["overview.md"]
    posts = texts["posts.md"]
    trouble = texts["troubleshooting.md"]
    publishing = texts["reference_publishing.md"]
    statuses = re.findall(r"^\* `([A-Z_]+)` — ", trouble.split("In case of an error")[0], re.M)
    messages = re.findall(r"^\* `([A-Z_]+)`$", trouble.split("In case of an error")[1], re.M)
    host = re.search(
        r"accessed by either `(graph\.threads\.com)` or `(graph\.threads\.net)`", overview
    )
    versions = sorted(
        set(re.findall(r"https://graph\.threads\.com/(v\d+\.\d+)/", "".join(texts.values())))
    )
    if not host or len(versions) != 1:
        raise SystemExit("the API host or version is not what the pages show")
    return {
        "hosts": [host.group(1), host.group(2)],
        "api_version": versions[0],
        "text_max_characters": _number(overview, r"Text posts are limited to (\d+) characters"),
        "carousel_max_children": _number(overview, r"maximum of (\d+) children"),
        "carousel_min_children": _number(overview, r"minimum of (\d+) children"),
        "image_max_mb": _number(overview, r"\*\*File Size:\*\* (\d+) MB maximum"),
        "video_max_gb": _number(overview, r"\*\*File Size:\*\* (\d+) GB maximum"),
        "video_max_seconds": _number(overview, r"\*\*Duration:\*\* (\d+) seconds"),
        "alt_text_max_characters": _number(publishing, r"maximum length of `alt_text` is ([\d,]+)"),
        "topic_tag_max_characters": _number(posts, r"no more than (\d+) characters long"),
        "links_max": _number(posts, r"restricted to (\d+) or fewer"),
        "posts_per_24h": _number(overview, r"limited to (\d+) API-published posts"),
        "replies_per_24h": _number(overview, r"limited to ([\d,]+) replies"),
        "deletes_per_24h": _number(overview, r"limited to (\d+) deletions"),
        "location_searches_per_24h": _number(overview, r"limited to (\d+) location searches"),
        "keyword_queries_per_24h": _number(
            texts["keyword-search.md"], r"maximum of ([\d,]+) queries"
        ),
        "wait_before_publish_seconds": _number(
            posts, r"Wait about (\d+) seconds before publishing"
        ),
        "status_checks_per_minute": 1 if "once per minute" in trouble else 0,
        "status_check_max_minutes": _number(trouble, r"for no more than (\d+) minutes"),
        "container_expires_hours": _number(trouble, r"not published within (\d+) hours"),
        "container_statuses": statuses,
        "container_error_messages": messages,
        "image_formats": "JPEG and PNG" if "JPEG and PNG image types" in overview else "",
        "media_by_public_url": "it must be on a public server" in posts,
        # How a list and an object travel in a request, as the examples send them.
        "list_example": _find(r"allowlisted_country_codes=([A-Z,]+)", texts["posts_geo-gating.md"]),
        "object_example": _find(
            r"poll_attachment='(\{.*?\})'", texts["create-posts_polls.md"], re.S
        ),
    }


def user_insights(texts: dict[str, str]) -> dict[str, Any]:
    """What the insights guide adds to the reference for user insights."""
    guide = texts["insights.md"]
    part = guide.split("## User insights", 1)[1]
    rows = re.findall(r"^\| `([a-z_]+)` \| ([A-Za-z ]+) \| (.*) \|$", part, re.M)
    breakdown = re.search(
        r"must be equal to one of the following values: ((?:`[a-z]+`,? ?(?:or )?)+)", part
    )
    return {
        "earliest": _number(part, r"earliest Unix timestamp that can be used is `(\d+)`"),
        "metrics": {name: kind.strip() for name, kind, _ in rows},
        "without_since_until": [
            name for name, _, words in rows if "does not support the `since` and `until`" in words
        ],
        "breakdown_metric": "follower_demographics",
        "breakdown_values": re.findall(r"`([a-z]+)`", breakdown.group(1)) if breakdown else [],
    }


def permissions(texts: dict[str, str]) -> dict[str, Any]:
    found: dict[str, str] = {}
    for text in texts.values():
        for name, words in re.findall(r"^\* `(threads_[a-z_]+)` — (.+)$", text, re.M):
            found.setdefault(name, _plain(words))
    scopes = re.search(
        r"\*\*Values:\*\*\s*((?:`threads_[a-z_]+`,? ?)+)",
        texts["get-started_get-access-tokens-and-permissions.md"],
    )
    app = texts["get-started_create-an-app.md"]
    use_case = re.findall(r"^\| \[`(threads_[a-z_]+)`\]", app, re.M)
    return {
        "described": dict(sorted(found.items())),
        "use_case_permissions": use_case,
        "authorization_scopes": re.findall(
            r"`(threads_[a-z_]+)`", scopes.group(1) if scopes else ""
        ),
    }


def auth(texts: dict[str, str]) -> dict[str, Any]:
    access = texts["get-started_get-access-tokens-and-permissions.md"]
    long_lived = texts["get-started_long-lived-tokens.md"]
    exchange = access.split("Example success response", 1)[1].split("```", 2)[1]
    return {
        "authorization_url": _find(r"(https://threads\.com/oauth/authorize)", access),
        "token_url": _find(r"POST (https://graph\.threads\.com/oauth/access_token)", access),
        "code_exchange_answer_fields": re.findall(r'"([a-z_]+)":', exchange),
        "short_lived": "short-lived and are valid for one hour" in long_lived,
        "long_lived_days": _number(long_lived, r"Long-lived tokens are valid for (\d+) days"),
        "long_lived_grant": _find(r"Set this to `(th_exchange_token)`", long_lived),
        "refresh_grant": _find(r"Set this to `(th_refresh_token)`", long_lived),
        "refresh_takes_a_refresh_token": "| `refresh_token`" in long_lived,
        "scope_separator": "comma-separated or space-separated" in access,
        "pkce_documented": "code_challenge" in access,
    }


def graph(texts: dict[str, str]) -> dict[str, Any]:
    errors = texts["graph_error-handling.html"]
    rate = texts["graph_rate-limiting.html"]
    form = errors.split("Error Responses", 1)[1].split("Error Codes", 1)[0]
    keys = re.findall(r'"([a-z_]+)":', form)
    throttle = rate.split("Throttle Error Codes", 1)[1].split("Sample Response", 1)[0]
    return {
        "error_form_keys": keys,
        "throttle_codes": sorted({int(c) for c in re.findall(r"^\s*(\d+)\s*$", throttle, re.M)}),
        "token_codes": [102, 190] if "Access token has expired" in errors else [],
        "permission_codes": [10, "200-299"] if "API Permission Denied" in errors else [],
        "usage_headers": sorted(set(re.findall(r"(X-App-Usage|X-Business-Use-Case-Usage)", rate))),
    }


def extract(texts: dict[str, str], pages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "source": {
            "site": THREADS_DOCS,
            "downloaded": DOWNLOADED,
            "pages": pages,
            "machine_readable_specification": False,
        },
        "operations": reference_operations(texts),
        "guide_operations": guide_operations(texts),
        "limits": limits(texts),
        "user_insights": user_insights(texts),
        "permissions": permissions(texts),
        "auth": auth(texts),
        "graph": graph(texts),
    }


def build(*, pin: bool = False) -> dict[str, Any]:
    texts: dict[str, str] = {}
    pages: list[dict[str, Any]] = []
    for name in PAGES:
        text, facts = load(name, pin=pin)
        texts[name] = text
        pages.append(facts)
    return extract(texts, pages)


def main(argv: list[str]) -> int:
    pin = "--pin" in argv
    data = build(pin=pin)
    if pin:
        PINS_FILE.write_text(
            json.dumps({p["name"]: p["sha256"] for p in data["source"]["pages"]}, indent=1) + "\n",
            encoding="utf-8",
        )
    OUTPUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        "operations:", len(data["operations"]), "guide operations:", len(data["guide_operations"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
