"""Reading every page of a Threads list, with an exact place to continue from.

Threads lists answer ``{"data": [...], "paging": {"cursors": {"before", "after"},
"next"?}}`` and take ``after`` to read the page that follows. Pages are read until the
list ends, the asked maximum is reached, the step output is full or the time left is
too short; then the step returns what it read with ``complete`` false and
``next_after``: run it again with ``after`` set to it for the rest. A read never fails
because of that.

- The list ends with an empty page or a page without an ``after`` cursor. An empty page
  while ``paging.next`` says there is more is an error: the read is not complete.
- A page that does not fit the step output is asked again from the same cursor with
  half as many records (where the endpoint documents ``limit``), down to one; after a
  page fits, the next one is asked at the full size again. So the result is always
  whole pages and ``next_after`` is the cursor of the first record not returned.
- A record returned twice (the list changed while it was read) is returned once.
- A cursor that comes back again is an error, never a loop.
- The whole result is measured, not only the records: its envelope with the widest
  values it can hold, the warnings so far and room for the closing warning.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from . import budget, errors, generic
from .context import Context
from .errors import ExtensionError, invalid
from .params import integer, text
from .transport import MIN_CALL_WINDOW_SECONDS, DeadlineReached

MAX_STOP_WARNING = 600
_STOP_RESERVE = "x" * MAX_STOP_WARNING
MAX_ITEMS = 100_000
DEFAULT_MAX_ITEMS = 10_000
MAX_CURSOR = 2048
#: Time a page needs after its request is answered (reading and measuring it; our
#: decision): no page is started with less than this on top of the request's own window.
PAGE_READ_SECONDS = 15
#: The widest count the envelope reserves room for (more than any list here holds).
WIDEST_COUNT = 10**9


@dataclass
class Page:
    items: list[Any]
    after: str | None
    before: str | None
    more: bool


def _bad(shown: str, what: str) -> ExtensionError:
    return errors.no_effect(
        errors.INVALID_RESPONSE,
        f"Threads' answer to {shown} {what}",
        failure_class="provider",
        retryable=False,
    )


def _cursor(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_CURSOR:
        return None
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in value):
        return None
    return value


def page_of(data: Any, shown: str) -> Page:
    """One list page as Threads documents it; an answer of another shape is an error."""
    if not isinstance(data, Mapping) or not isinstance(data.get("data"), list):
        raise _bad(shown, "has no data list")
    paging = data.get("paging")
    paging = paging if isinstance(paging, Mapping) else {}
    cursors = paging.get("cursors")
    cursors = cursors if isinstance(cursors, Mapping) else {}
    return Page(
        items=list(data["data"]),
        after=_cursor(cursors.get("after")),
        before=_cursor(cursors.get("before")),
        more=isinstance(paging.get("next"), str) and bool(paging.get("next")),
    )


class Pages:
    """Collects the records of a paginated read into the step output, measuring the
    whole result each time (envelope, warnings so far, pending ones and room for the
    closing warning) so the final budget check never refuses what was taken."""

    def __init__(self, key: str, envelope: dict[str, Any]) -> None:
        self.key = key
        self.envelope = envelope
        self.items: list[Any] = []
        self.records = budget.Totals()
        self.warnings: list[str] = []

    def take(self, page: list[Any], pending: list[str]) -> bool:
        """Add a page and its pending warnings; False (nothing added) when they do not fit."""
        added = self.records
        for item in page:
            cost = budget.measure(item)
            # One level for the list, one for the result object.
            added = added + budget.Totals(cost.nodes, cost.depth + 2, cost.size + 1)
        frame = budget.measure(
            {**self.envelope, self.key: [], "warnings": [*self.warnings, *pending, _STOP_RESERVE]}
        )
        if not (added + frame).within():
            return False
        self.records = added
        self.items += page
        self.warnings += pending
        return True


def _room(context: Context) -> bool:
    return context.transport.remaining() >= MIN_CALL_WINDOW_SECONDS + PAGE_READ_SECONDS


def _out_of_time(context: Context) -> ExtensionError:
    return errors.no_effect(
        errors.TIMEOUT,
        f"The step ran out of time after {context.transport.calls} requests to Threads while "
        "asking for a page small enough to return; nothing was changed. Run it again with "
        "narrower filters",
    )


def _too_large_answer(exc: ExtensionError) -> bool:
    return exc.code == errors.RESPONSE_TOO_LARGE and exc.definitely_no_external_effect is True


def options(given: Mapping[str, Any]) -> tuple[str | None, int]:
    """The starting cursor (``after``) and the most records to read (``max_items``)."""
    if given.get("before") not in (None, ""):
        raise invalid("before reads backwards one page at a time; it cannot be used with all_pages")
    flag = given.get("all_pages")
    if flag is not None and not isinstance(flag, bool):
        raise invalid("all_pages must be true or false")
    after = given.get("after")
    start = text(after, "after", max_length=MAX_CURSOR) if after not in (None, "") else None
    most = given.get("max_items")
    most_n = (
        DEFAULT_MAX_ITEMS
        if most in (None, "")
        else integer({"minimum": 1, "maximum": MAX_ITEMS}, most, "max_items")
    )
    return start, most_n


def collect(
    context: Context,
    *,
    operation_id: str,
    query: Mapping[str, Any],
    start: str | None,
    most: int,
    out_key: str = "items",
) -> dict[str, Any]:
    """Pages of a generated list step read from ``start`` until the list ends."""
    entry = generic.spec(operation_id)
    shown = entry["shown"]
    page_size = entry["page_size"][1] if entry["page_size"] else None
    envelope = {
        "count": WIDEST_COUNT,
        "complete": False,
        "next_after": "x" * MAX_CURSOR,
        "rate_limit_usage": {
            "X-App-Usage": "x" * errors.HEADER_TEXT,
            "X-Business-Use-Case-Usage": "x" * errors.HEADER_TEXT,
        },
    }
    pages = Pages(out_key, envelope)
    cursor = start
    used: set[str] = set()
    seen: set[str] = set()
    first = True
    stopped = ""
    complete = False
    size = page_size
    while True:
        if len(pages.items) >= most:
            stopped = f"the {most} asked for were read"
            break
        if context.transport.calls and not _room(context):
            if first:
                raise _out_of_time(context)
            stopped = "time ran out"
            break
        limit = min(size, most - len(pages.items)) if size else None
        given = dict(query)
        if cursor:
            given["after"] = cursor
        if limit is not None:
            given["limit"] = limit
        call = generic.prepare(operation_id, given)
        try:
            answer = context.transport.read(call)
            data = generic.read_json(context, answer, shown)
        except DeadlineReached:
            if first and context.transport.calls:
                raise _out_of_time(context) from None
            if first:
                raise
            stopped = "time ran out"
            break
        except ExtensionError as exc:
            if _too_large_answer(exc) and limit is not None and limit > 1:
                size = max(1, limit // 2)
                continue
            if first or not (exc.retryable is True or _too_large_answer(exc)):
                raise
            stopped = f"Threads could not give the next page ({exc.code}: {exc.message})"
            break
        page = page_of(data, shown)
        if not page.items:
            if page.more:
                raise _bad(
                    shown, "is an empty page while it says more follow; the read is not complete"
                )
            complete = True
            break
        fresh = []
        for item in page.items:
            ident = item.get("id") if isinstance(item, Mapping) else None
            if not isinstance(ident, str) or not ident:
                raise _bad(shown, "lists a record without an id")
            if ident in seen:
                continue
            fresh.append(item)
        pending = []
        if len(fresh) != len(page.items):
            pending.append(
                f"{len(page.items) - len(fresh)} records appeared twice because the list changed "
                "while it was read; each is returned once"
            )
        if not pages.take(fresh, pending):
            if limit is not None and limit > 1:
                size = max(1, limit // 2)
                continue
            if first:
                raise budget.too_large()
            stopped = "the output is full"
            break
        seen.update(item["id"] for item in fresh)
        first = False
        size = page_size
        if page.after is None:
            complete = True
            break
        if page.after == cursor or page.after in used:
            raise _bad(shown, "gives a cursor it gave before; the read is not complete")
        if cursor:
            used.add(cursor)
        cursor = page.after
    if not complete:
        pages.warnings.append(
            errors.safe_text(
                f"Stopped early because {stopped}; run the step again with after set to "
                "next_after for the rest",
                MAX_STOP_WARNING,
            )
        )
    return {
        out_key: pages.items,
        "count": len(pages.items),
        "complete": complete,
        "next_after": None if complete else cursor,
        "warnings": pages.warnings,
    }


def read_all(context: Context, operation_id: str, given: Mapping[str, Any]) -> dict[str, Any]:
    """A generated list step with ``all_pages``."""
    start, most = options(given)
    query = {
        k: v
        for k, v in given.items()
        if k not in {"all_pages", "max_items", "after", "before", "limit", "connection_ref"}
    }
    if given.get("limit") not in (None, ""):
        raise invalid("limit is chosen by the step with all_pages; leave it empty")
    # Checked in full before the first request.
    generic.prepare(operation_id, query)
    result = collect(context, operation_id=operation_id, query=query, start=start, most=most)
    result["before_cursor"] = None
    return result


__all__ = ["Page", "Pages", "collect", "options", "page_of", "read_all"]
