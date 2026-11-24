"""Step inputs checked against the specification's parameters and turned into the request.

Each node comes from runtime/registry.json (built from the pinned documentation facts
by tests/reference/build_contracts.py): its kind, whether it is required, its allowed
values and limits. Numbers stay Decimal to the wire; nothing goes through float. A
list travels as one comma-separated value and an object as JSON text, as the
documentation's examples send them (``allowlisted_country_codes=US,CA``,
``poll_attachment={...}``).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Any

from . import numbers
from .errors import invalid

_PAIR_KEY_RE = re.compile(r"^[A-Za-z0-9._\-\[\]]{1,100}$")
MAX_PAIRS = 100
#: Bounds of this extension's own inputs (safety bounds, not Threads' rules):
#: an address, a field or metric name, one value of a free name/value object.
MAX_URL_LENGTH = 2000
MAX_NAME_LENGTH = 64
MAX_PAIR_VALUE_LENGTH = 1000
#: Characters of a refused value shown back in the message, and of refused names listed
#: (our decision).
SHOWN_VALUE_LENGTH = 40
SHOWN_DATE_LENGTH = 20
LISTED_NAMES = 5
#: How many IDs a list input takes when the documentation gives no number (our bound),
#: and how many country codes (ISO 3166-1 has 249 codes).
DEFAULT_MAX_IDS = 100
DEFAULT_MAX_COUNTRY_CODES = 250


def text(
    value: Any, what: str, *, max_length: int, min_length: int = 0, multiline: bool = False
) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise invalid(f"{what} must be text")
    result = (
        value
        if isinstance(value, str)
        else (numbers.plain(value) if isinstance(value, Decimal) else str(value))
    )
    result = result.strip()
    if not result:
        raise invalid(f"{what} is empty")
    allowed = {"\n", "\r", "\t"} if multiline else set()
    if any((ord(ch) < 32 or ord(ch) == 127) and ch not in allowed for ch in result):
        raise invalid(f"{what} may not contain control characters")
    if len(result) > max_length or len(result) < min_length:
        raise invalid(f"{what} must be {min_length or 1} to {max_length} characters")
    return result


_DATE_TIME_RE = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})"
    r"(?:[Tt ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d{1,9})?)?)?"
    r"(Z|z|[+-](\d{2}):?(\d{2}))?"
)


def date_time(value: str, what: str) -> str:
    """``value`` when it is a real date (and time), as RFC 3339 writes one; an impossible
    one (2026-02-31, 25:00, an offset past 23:59) is refused, never sent."""
    match = _DATE_TIME_RE.fullmatch(value)
    if match is None:
        raise invalid(f"{what} must be a date and time such as 2026-11-01T00:00:00Z")
    year, month, day, hour, minute, second, _, off_h, off_m = match.groups()
    try:
        date(int(year), int(month), int(day))
        if hour is not None:
            datetime(
                int(year), int(month), int(day), int(hour), int(minute), int(second or 0)
            ).replace(
                tzinfo=timezone(timedelta(hours=int(off_h or 0), minutes=int(off_m or 0)))
            ).astimezone(UTC)
    except (ValueError, OverflowError):
        raise invalid(f"{what} is not a real date and time: {value[:SHOWN_VALUE_LENGTH]}") from None
    return value


def http_date(value: str, what: str) -> str:
    """An HTTP date (``Wed, 21 Oct 2026 07:28:00 GMT``) that names a real moment."""
    try:
        moment = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        moment = None
    if moment is None:
        raise invalid(f"{what} must be an HTTP date such as Wed, 21 Oct 2026 07:28:00 GMT")
    return value


def decimal(value: Any, what: str) -> Decimal:
    """An exact decimal from a JSON number (already Decimal) or text; never a float."""
    if isinstance(value, bool) or isinstance(value, float):
        raise invalid(f"{what} must be an exact decimal, written as text or a JSON number")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, str) and re.fullmatch(r"\s*-?\d{1,15}(\.\d{1,10})?\s*", value):
        try:
            number = Decimal(value.strip())
        except InvalidOperation:  # pragma: no cover - the pattern rules it out
            raise invalid(f"{what} is not a number") from None
    else:
        raise invalid(f"{what} must be a number such as 49.99")
    if not number.is_finite():
        raise invalid(f"{what} must be a finite number")
    return number


def wire(value: Any) -> str:
    """A checked value as query text (Decimal plainly, booleans as JSON writes them)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return numbers.plain(value)
    return str(value)


def integer(node: Mapping[str, Any], value: Any, what: str) -> int:
    if isinstance(value, bool):
        raise invalid(f"{what} must be a whole number")
    if isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
        value = int(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d{1,19}", value.strip()):
        value = int(value.strip())
    if not isinstance(value, int):
        raise invalid(f"{what} must be a whole number")
    low, high = node.get("minimum"), node.get("maximum")
    if (low is not None and value < low) or (high is not None and value > high):
        raise invalid(f"{what} must be a whole number from {low} to {high}")
    return value


_ID_RE = re.compile(r"^[0-9]{1,30}$")
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_URL_RE = re.compile(r"^https?://[^\s/?#]+[^\s]*$", re.I)
_DAY_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
MAX_OBJECT_BYTES = 20_000


def identifier(node: Mapping[str, Any], value: Any, what: str) -> str:
    """A Threads ID: digits only (``me`` too where the node allows it)."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise invalid(f"{what} must be a Threads ID (digits)")
    result = str(value).strip()
    if node.get("allow_me") and result == "me":
        return result
    if not _ID_RE.fullmatch(result):
        raise invalid(
            f"{what} must be a Threads ID (digits)" + (" or me" if node.get("allow_me") else "")
        )
    return result


def url(value: Any, what: str) -> str:
    result = text(value, what, max_length=MAX_URL_LENGTH)
    if not _URL_RE.fullmatch(result):
        raise invalid(f"{what} must be a full http or https address")
    return result


def moment(node: Mapping[str, Any], value: Any, what: str) -> str:
    """A Unix timestamp (such as 1767225600) or a date (such as 2026-01-01): the two forms
    the documentation gives. An impossible date (2026-02-31) is refused, never sent."""
    if isinstance(value, bool):
        raise invalid(f"{what} must be a Unix timestamp or a date such as 2026-01-01")
    if isinstance(value, Decimal) and value == value.to_integral_value():
        value = int(value)
    if isinstance(value, int) or (isinstance(value, str) and value.strip().isdigit()):
        seconds = int(value)
        if seconds > 32_503_680_000:
            raise invalid(f"{what} is not a Unix timestamp in seconds")
        stamp = seconds
        shown = str(seconds)
    elif isinstance(value, str) and _DAY_RE.fullmatch(value.strip()):
        year, month, day = (int(p) for p in _DAY_RE.fullmatch(value.strip()).groups())  # type: ignore[union-attr]
        try:
            moment_day = date(year, month, day)
        except ValueError:
            raise invalid(
                f"{what} is not a real date: {value.strip()[:SHOWN_DATE_LENGTH]}"
            ) from None
        stamp = int(datetime(year, month, day, tzinfo=UTC).timestamp())
        shown = moment_day.isoformat()
    else:
        raise invalid(f"{what} must be a Unix timestamp or a date such as 2026-01-01")
    low = node.get("minimum")
    if low is not None and stamp < int(low):
        raise invalid(f"{what} must be on or after {low} (Unix time), as Threads documents")
    return shown


def timestamp_of(value: str) -> int:
    """The Unix time of a checked ``moment`` (a date counts from its UTC midnight)."""
    if value.isdigit():
        return int(value)
    return int(datetime.fromisoformat(value).replace(tzinfo=UTC).timestamp())


def names(node: Mapping[str, Any], value: Any, what: str) -> str:
    """A list of names sent as one comma-separated value (fields, metrics)."""
    items = value if isinstance(value, list) else [value]
    if isinstance(value, str) and "," in value:
        items = [part for part in value.split(",")]
    out: list[str] = []
    for i, item in enumerate(items, 1):
        name = text(item, f"{what} item {i}", max_length=MAX_NAME_LENGTH)
        if not _NAME_RE.fullmatch(name):
            raise invalid(f"{what} item {i} is not a field or metric name")
        if name not in out:
            out.append(name)
    if not out:
        raise invalid(f"{what} must name at least one value")
    allowed = node.get("allowed")
    if allowed and any(item not in allowed for item in out):
        wrong = [item for item in out if item not in allowed]
        raise invalid(
            f"{what} may only name: {', '.join(allowed)} (not {', '.join(wrong[:LISTED_NAMES])})"
        )
    return ",".join(out)


def id_list(node: Mapping[str, Any], value: Any, what: str) -> str:
    items = value if isinstance(value, list) else str(value).split(",")
    low, high = int(node.get("min_items") or 1), int(node.get("max_items") or DEFAULT_MAX_IDS)
    if not low <= len(items) <= high:
        raise invalid(f"{what} must list {low} to {high} IDs")
    return ",".join(identifier({}, item, f"{what} item {i}") for i, item in enumerate(items, 1))


def codes(node: Mapping[str, Any], value: Any, what: str) -> str:
    items = value if isinstance(value, list) else str(value).split(",")
    if not items or len(items) > int(node.get("max_items") or DEFAULT_MAX_COUNTRY_CODES):
        raise invalid(f"{what} must list at least one country code")
    out = []
    for i, item in enumerate(items, 1):
        code = text(item, f"{what} item {i}", max_length=2, min_length=2)
        if not re.fullmatch(r"[A-Z]{2}", code):
            raise invalid(f"{what} item {i} must be an ISO 3166-1 alpha-2 code such as US")
        out.append(code)
    return ",".join(out)


def json_object(value: Any, what: str) -> str:
    from .transport import dumps_json  # noqa: PLC0415 - avoids an import cycle

    if not isinstance(value, Mapping) or not value:
        raise invalid(f"{what} must be a JSON object")
    encoded = dumps_json(value)
    if len(encoded.encode("utf-8")) > MAX_OBJECT_BYTES:
        raise invalid(f"{what} is larger than {MAX_OBJECT_BYTES} bytes")
    return encoded


def check(node: Mapping[str, Any], value: Any, what: str) -> Any:
    """One parameter value checked against its node: what to send (a list sends one
    query parameter per item, ``pairs`` one per key)."""
    kind = node["kind"]
    if kind == "text":
        result = text(
            value,
            what,
            max_length=int(node["max_length"]),
            min_length=int(node.get("min_length") or 0),
            multiline=bool(node.get("multiline")),
        )
        allowed = node.get("allowed")
        if allowed and result not in allowed:
            raise invalid(f"{what} must be one of: {', '.join(allowed)}")
        if node.get("format") == "date-time":
            return date_time(result, what)
        if node.get("format") == "http-date":
            return http_date(result, what)
        return result
    if kind == "id":
        return identifier(node, value, what)
    if kind == "url":
        return url(value, what)
    if kind == "moment":
        return moment(node, value, what)
    if kind == "names":
        return names(node, value, what)
    if kind == "id_list":
        return id_list(node, value, what)
    if kind == "codes":
        return codes(node, value, what)
    if kind == "object":
        return json_object(value, what)
    if kind == "integer":
        return integer(node, value, what)
    if kind == "decimal":
        number = decimal(value, what)
        low, high = node.get("minimum"), node.get("maximum")
        if low is not None and number < Decimal(str(low)):
            raise invalid(f"{what} may not be less than {low}")
        if high is not None and number > Decimal(str(high)):
            raise invalid(f"{what} may not be more than {high}")
        return number
    if kind == "boolean":
        if not isinstance(value, bool):
            raise invalid(f"{what} must be true or false")
        return value
    if kind == "text_list":
        items = value if isinstance(value, list) else [value]
        limit = int(node["max_items"])
        if not items or len(items) > limit:
            raise invalid(f"{what} must be a list of 1 to {limit} values")
        out = [
            text(item, f"{what} item {i}", max_length=int(node["item_max_length"]))
            for i, item in enumerate(items, 1)
        ]
        allowed = node.get("allowed")
        if allowed and any(item not in allowed for item in out):
            raise invalid(f"{what} values must be among: {', '.join(allowed)}")
        return out
    if kind == "pairs":
        if not isinstance(value, Mapping) or not value or len(value) > MAX_PAIRS:
            raise invalid(f"{what} must be an object of 1 to {MAX_PAIRS} name/value pairs")
        pairs: list[tuple[str, str]] = []
        for name, item in value.items():
            if not isinstance(name, str) or not _PAIR_KEY_RE.fullmatch(name):
                raise invalid(f"{what} has a name that is not usable as a query parameter")
            for one in item if isinstance(item, list) else [item]:
                pairs.append(
                    (name, wire(text(one, f"{what}.{name}", max_length=MAX_PAIR_VALUE_LENGTH)))
                )
        return pairs
    raise invalid(f"{what} has a kind this extension does not know")  # pragma: no cover


__all__ = [
    "check",
    "date_time",
    "decimal",
    "http_date",
    "integer",
    "moment",
    "names",
    "text",
    "timestamp_of",
    "wire",
]
