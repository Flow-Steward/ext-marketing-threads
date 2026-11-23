"""Runners of the generated steps: one documented Threads endpoint each.

What each step accepts and how its answer is read comes from runtime/registry.json,
built from the pinned documentation facts by tests/reference/build_contracts.py:

- path IDs are digits (``threads_user_id`` may also be ``me``, as the documentation's
  examples use it, and is ``me`` when not given);
- parameters are typed by what the documentation says of them: allowed values,
  booleans, whole numbers with their documented range, dates as a Unix timestamp or
  a ``YYYY-MM-DD`` date, lists sent comma-separated and objects as JSON text;
- ``since`` must come before ``until`` where both are given, as documented;
- a read returns the JSON answer as ``data``; a list endpoint (one with ``after`` /
  ``before`` cursors) returns ``items`` and the cursor to continue from, and with
  ``all_pages`` reads every page (``runtime/pages.py``); the ``paging.next`` and
  ``paging.previous`` addresses are never returned, since they repeat the token;
- a write returns what Threads answered, decided by ``runtime/outcome.py``, and
  ``processing``: ``completed`` when Threads made the change, ``accepted`` for a media
  container Threads still processes; then ``applied`` is false and ``check`` names
  the step that reads its status.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

from . import budget, errors, nesting, outcome
from .context import Context
from .errors import invalid
from .params import check, timestamp_of, wire
from .transport import Answer, Call, TooDeep

REGISTRY_FILE = Path(__file__).resolve().parent / "registry.json"
#: Inputs every list step has besides the documented ones.
PAGE_INPUTS = frozenset({"all_pages", "max_items"})


@cache
def _data() -> dict[str, Any]:
    return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))


def registry() -> dict[str, dict[str, Any]]:
    return dict(_data()["operations"])


def spec(operation_id: str) -> dict[str, Any]:
    return _data()["operations"][operation_id]


def inputs_of(entry: Mapping[str, Any]) -> set[str]:
    names = {p["input"] for p in entry["params"]}
    if entry["paged"]:
        names |= PAGE_INPUTS
    return names


def prepare(operation_id: str, operation_input: Mapping[str, Any]) -> Call:
    """The checked request of a generated step (also its test-run check). The list
    inputs ``all_pages`` and ``max_items`` are the caller's, not the request's."""
    entry = spec(operation_id)
    given = {k: v for k, v in operation_input.items() if k != "connection_ref"}
    unknown = sorted(set(given) - {p["input"] for p in entry["params"]})
    if unknown:
        raise invalid(f"The step input has unknown fields: {', '.join(unknown[:10])}")
    path = entry["path"]
    query: list[tuple[str, str]] = [(k, v) for k, v in entry["fixed_query"]]
    form: list[tuple[str, str]] = []
    moments: dict[str, str] = {}
    for prm in entry["params"]:
        node = prm["node"]
        value = given.get(prm["input"])
        if value is None or value == "" or value == [] or value == {}:
            if node.get("default_value") is not None:
                value = node["default_value"]
            elif node["required"]:
                raise invalid(f"{prm['input']} is required")
            else:
                continue
        checked = check(node, value, prm["input"])
        if node["kind"] == "moment":
            moments[prm["name"]] = checked
        if prm["in"] == "path":
            path = path.replace("{" + prm["name"] + "}", quote(str(checked), safe=""))
        elif prm["in"] == "form":
            form.append((prm["name"], wire(checked)))
        else:
            query = [(k, v) for k, v in query if k != prm["name"]]
            query.append((prm["name"], wire(checked)))
    if "since" in moments and "until" in moments:
        if timestamp_of(moments["since"]) >= timestamp_of(moments["until"]):
            raise invalid("since must be before until")
    names = {k for k, _ in query}
    if "before" in names and "after" in names:
        raise invalid("Give before or after, not both: Threads does not accept both")
    return Call(
        method=entry["method"],
        path=path,
        shown=entry["shown"],
        query=tuple(query),
        form=tuple(form) if entry["method"] == "POST" else None,
        token=entry["token"],
    )


def read_json(context: Context, answer: Answer, shown: str) -> Any:
    """A read's JSON value; an invalid answer is an error (nothing changed)."""
    if answer.empty:
        raise errors.no_effect(
            errors.INVALID_RESPONSE,
            f"Threads answered {shown} without a body",
            failure_class="provider",
            retryable=False,
        )
    try:
        return context.transport.json(answer)
    except ValueError as exc:
        what = (
            f"JSON nested deeper than {nesting.MAX_ANSWER_DEPTH} levels; it is not read"
            if isinstance(exc, TooDeep)
            else "something that is not JSON"
        )
        raise errors.no_effect(
            errors.INVALID_RESPONSE,
            f"Threads answered {shown} with {what}",
            failure_class="provider",
            retryable=False,
        ) from None


def without_links(data: Any) -> Any:
    """``paging`` without the ``next`` / ``previous`` addresses (they repeat the token)."""
    if not isinstance(data, Mapping):
        return data
    out = dict(data)
    paging = out.get("paging")
    if isinstance(paging, Mapping):
        out["paging"] = {k: v for k, v in paging.items() if k not in {"next", "previous"}}
    return out


def single_page(context: Context, entry: Mapping[str, Any], data: Any) -> dict[str, Any]:
    """One page of a list endpoint: its items and the cursor to continue from."""
    from .pages import page_of  # noqa: PLC0415 - pages builds on this module

    page = page_of(data, entry["shown"])
    after = page.after if page.items else None
    return {
        "items": page.items,
        "count": len(page.items),
        "complete": not (page.items and after),
        "next_after": after,
        "before_cursor": page.before,
    }


def processing_of(entry: Mapping[str, Any], data: Any) -> dict[str, Any]:
    """What Threads' answer to a write confirms: the change made (completed), or a media
    container created, which Threads processes before it can be published (accepted)."""
    facts = entry["processing"]
    if facts["accepted"]:
        return {
            "processing": "accepted",
            "applied": False,
            "check": {
                "operation_id": facts["check"],
                "container_id": outcome.identifier_of(data),
            },
        }
    return {"processing": "completed", "applied": True, "check": None}


def write_result(context: Context, entry: Mapping[str, Any], answer: Answer) -> dict[str, Any]:
    data = outcome.write_outcome(context, entry["write_class"], answer, entry["shown"])
    result: dict[str, Any] = {"status": answer.status, "data": data}
    result["id"] = outcome.identifier_of(data) if entry["write_class"] == outcome.NEEDS_ID else None
    result.update(processing_of(entry, data))
    return result


def run(context: Context, operation_id: str) -> dict[str, Any]:
    entry = spec(operation_id)
    given = context.operation_input
    if (
        entry["paged"]
        and given.get("all_pages") is not None
        and given.get("all_pages") is not False
    ):
        from .pages import read_all  # noqa: PLC0415 - pages builds on this module

        result = read_all(context, operation_id, given)
        result["rate_limit_usage"] = context.transport.usage_report()
        budget.ensure_fits(result)
        return result
    if entry["paged"] and given.get("max_items") is not None:
        raise invalid("max_items applies only with all_pages")
    call = prepare(operation_id, {k: v for k, v in given.items() if k not in PAGE_INPUTS})
    if entry["kind"] == "read":
        answer = context.transport.read(call)
        data = read_json(context, answer, entry["shown"])
        if entry["paged"]:
            result = single_page(context, entry, data)
        else:
            result = {"data": without_links(data)}
        result["warnings"] = []
        result["rate_limit_usage"] = context.transport.usage_report()
        budget.ensure_fits(result)
        return result
    answer = context.transport.write(call)
    result = write_result(context, entry, answer)
    result["warnings"] = []
    result["rate_limit_usage"] = context.transport.usage_report()
    return result


__all__ = [
    "inputs_of",
    "prepare",
    "processing_of",
    "read_json",
    "registry",
    "run",
    "spec",
    "without_links",
    "write_result",
]
