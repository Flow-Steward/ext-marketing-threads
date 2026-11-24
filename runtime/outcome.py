"""The outcome of a write after it was sent: one table, decided in one place.

Every write of this extension (each generated write step and every write of the
everyday steps) goes through ``write_outcome`` once Threads answered it with HTTP 200.
The inputs are the Content-Type, the state of the body (empty / read and parsed /
read and not parsed / not fully read / nested deeper than 48 levels) and the class of
the step. The Threads documentation shows a JSON answer for every write, so JSON is
always what is promised. The first row that applies decides:

- T1. A status other than HTTP 200 never reaches this table: the transport refuses it
  (a documented refusal, or the outcome is unknown).
- T2. The Content-Type is present and not JSON: the outcome is unknown
  (``invalid_response``, ``timeout_unknown``). Decided on the headers, whether or not
  the body was read.
- T3. The body was read, is not empty, and does not start with ``{`` or ``[`` or does not
  parse: the outcome is unknown.
- T4. The body was not fully read (limit, deadline, cut off), is empty, or nests deeper
  than 48 levels: the step needs what is inside it, so the outcome is unknown. Both
  classes below read the body:
  (a) ``confirm`` — Threads confirms the change inside the body with ``"success": true``
  (hide or unhide a reply, approve or ignore a pending reply, delete a post);
  (c) ``needs_id`` — the step returns the ID Threads gives in ``"id"`` (create a media
  container, publish it, repost).
  No Threads write answers a list of items (class b) and none is confirmed by the
  status alone (class d).
- T5. A parsed body of the wrong shape: ``confirm`` without ``"success": true`` and
  ``needs_id`` without an ``"id"`` are unknown, except ``"success": false``, which the
  documentation describes as the action not being successful: then nothing changed.
- T6. Otherwise: success.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from . import errors
from .context import Context
from .errors import ExtensionError
from .transport import CHECK, Answer, TooDeep, unknown

CONFIRM = "confirm"
NEEDS_ID = "needs_id"
CLASSES = (CONFIRM, NEEDS_ID)


#: Bytes looked at for the first character of a JSON answer (our decision).
JSON_START_WINDOW = 4096
#: A Threads ID is a number of up to this many digits (our bound; Meta's IDs have 17-19).
MAX_ID_DIGITS = 30


def json_media(content_type: str) -> bool:
    return "json" in content_type.lower()


def _starts_as_json(raw: bytes) -> bool:
    return raw[:JSON_START_WINDOW].lstrip(b"\xef\xbb\xbf \t\r\n")[:1] in {b"{", b"["}


def _unknown(shown: str, answer: Answer, what: str) -> ExtensionError:
    return unknown(
        f"Threads answered {shown} with HTTP {answer.status}, but {what}, so the outcome is "
        "not known" + CHECK,
        errors.INVALID_RESPONSE,
        answer.status,
    )


def identifier_of(data: Any) -> str | None:
    """The ``id`` of a write's answer: digits, given as text or as a number."""
    if not isinstance(data, Mapping):
        return None
    value = data.get("id")
    if isinstance(value, bool):
        return None
    text = str(value).strip() if isinstance(value, (str, int)) else ""
    return text if text.isdigit() and len(text) <= MAX_ID_DIGITS else None


def write_outcome(context: Context, write_class: str, answer: Answer, shown: str) -> Any:
    """The parsed ``data`` of a write Threads answered with HTTP 200 (T2-T6 above);
    raises when the outcome is unknown or Threads said the action did not succeed."""
    if write_class not in CLASSES:  # pragma: no cover - the registry is closed
        raise ValueError(write_class)
    # T2: on the headers, before and whatever the body.
    if answer.content_type and not json_media(answer.content_type):
        raise _unknown(shown, answer, f"its Content-Type is {answer.content_type}, not JSON")
    # T4: not fully read, or empty.
    if answer.unread:
        raise _unknown(shown, answer, f"its answer {answer.unread}")
    if answer.empty:
        raise _unknown(shown, answer, "its answer is empty")
    # T3: read, not empty, not JSON.
    if not _starts_as_json(answer.raw):
        raise _unknown(shown, answer, "its body does not start as JSON")
    try:
        data = context.transport.json(answer)
    except TooDeep:
        raise _unknown(shown, answer, "its answer is nested deeper than 48 levels") from None
    except ValueError:
        raise _unknown(shown, answer, "its body is not valid JSON") from None
    # T5: the shape the step needs.
    if write_class == CONFIRM:
        success = data.get("success") if isinstance(data, Mapping) else None
        if success is False:
            # Threads said the action did not succeed: this write changed nothing.
            context.transport.confirmed_writes -= 1
            raise errors.no_effect(
                errors.UPSTREAM_FAILURE,
                f"Threads answered {shown} that the action was not successful; nothing was changed",
                failure_class="provider",
                retryable=False,
                http_status=answer.status,
            )
        if success is not True:
            raise _unknown(
                shown, answer, 'its answer does not confirm the change with "success": true'
            )
    elif identifier_of(data) is None:
        raise _unknown(shown, answer, "its answer carries no ID")
    # T6.
    return data


__all__ = ["CLASSES", "CONFIRM", "NEEDS_ID", "identifier_of", "json_media", "write_outcome"]
