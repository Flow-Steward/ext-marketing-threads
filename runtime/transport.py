"""The only way this extension reaches Threads.

Each documented endpoint is a request to ``https://graph.threads.com/v1.0`` (the
host and version the Threads documentation uses; it names ``graph.threads.net`` as
the other host). GET and DELETE carry their parameters in the query; POST carries
them as an ``application/x-www-form-urlencoded`` body, as the documentation's
``curl -d`` / ``-F`` examples send them. The access token travels only in the
``Authorization: Bearer`` header (Threads issues it with ``token_type`` bearer), never
in a URL or a body. Requests go out through the public Flow Steward extension SDK,
which pins DNS, verifies the connected peer, refuses redirects and enforces the
timeout; they are sent one at a time, never in parallel, and never retried.

The Threads pages show an example answer for every endpoint but name no HTTP
status. The Graph API answers a request it carried out with HTTP 200, so 200 is the
only success; another 2xx is not taken as success (a read fails with
``invalid_response``, a write's outcome is unknown).

Refusals: the Graph API documents its error answer as ``{"error": {"message", "type",
"code", "error_subcode", "error_user_title", "error_user_msg", "fbtrace_id"}}``, with
codes for an expired token (190, 102), a missing permission (10, 200-299) and
throttling (4, 17, 32, 613). A write is known to have changed nothing only when
Threads refused it with a 4xx status (not 408) and that error form; any other failure
after the request was sent leaves the write ``timeout_unknown``.

Usage: the Graph API reports rate-limit usage in the ``X-App-Usage`` and
``X-Business-Use-Case-Usage`` headers once enough calls were made; when Threads sends
them, the last values are returned with the result.
"""

from __future__ import annotations

import http.client
import json
import re
import secrets
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request

from flowsteward_extension_sdk import PinnedPeerError, open_pinned_url, parse_retry_after

from . import errors, nesting, numbers
from .connection import Connection
from .errors import ExtensionError

DEFAULT_TIMEOUT_SECONDS = 120.0
MAX_REQUEST_BODY_BYTES = 1024 * 1024
#: The most read from an answer.
MAX_ANSWER_BYTES = 30 * 1024 * 1024
MAX_ERROR_BODY_BYTES = 64 * 1024
CHUNK_BYTES = 64 * 1024
#: Shortest window still worth starting a request in.
MIN_CALL_WINDOW_SECONDS = 15.0
_USER_AGENT = "FlowSteward-Threads/0.1"
_PATH_RE = re.compile(r"^(/[A-Za-z0-9%._~-]+)+$")
CHECK = "; check in Threads what changed before running the step again"
#: Response headers a step may return.
KEPT_HEADERS = ("Retry-After",)
#: Rate-limit usage headers the Graph API documents.
USAGE_HEADERS = ("X-App-Usage", "X-Business-Use-Case-Usage")
SUCCESS = ("200",)
TOKEN_CODES = frozenset({102, 190})
THROTTLE_CODES = frozenset({4, 17, 32, 613})


def permission_code(code: int | None) -> bool:
    return code is not None and (code == 10 or 200 <= code <= 299)


class DeadlineReached(Exception):
    """The invocation's time budget leaves no room for another request."""


@dataclass
class Answer:
    status: int
    raw: bytes
    content_type: str
    headers: dict[str, str] = field(default_factory=dict)
    #: Why the body of a confirmed write was not read (too large, too late); then
    #: ``raw`` is empty and only the status and the headers are known.
    unread: str | None = None

    @property
    def empty(self) -> bool:
        return not self.raw.strip()


@dataclass(frozen=True)
class Call:
    """One request."""

    method: str
    path: str
    shown: str
    query: Sequence[tuple[str, str]] = ()
    form: Sequence[tuple[str, str]] | None = None
    #: False for the one endpoint the documentation calls without a token (oEmbed).
    token: bool = True
    limit: int = MAX_ANSWER_BYTES


class ThreadsTransport:
    """Sends Threads requests for one connection."""

    def __init__(
        self,
        connection: Connection,
        *,
        opener: Callable[..., Any] = open_pinned_url,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._connection = connection
        self._opener = opener
        self.clock = clock
        self.sleep = sleep
        self._timeout_seconds = timeout_seconds
        self._call_timeout = timeout_seconds
        #: The token's forms, computed once for the connection (scrub runs per value).
        self._forms = connection.secret_forms()
        self._forms_bytes = tuple(form.encode("utf-8") for form in self._forms)
        #: True once a request that can change data may have left this process.
        self.mutated = False
        #: Writes Threads confirmed in this invocation (HTTP 200).
        self.confirmed_writes = 0
        #: Monotonic time after which no request may start (set by the operation).
        self.deadline: float | None = None
        #: Requests started in this invocation.
        self.calls = 0
        #: The last rate-limit usage Threads reported (header -> parsed value).
        self.usage: dict[str, Any] = {}

    @property
    def connection(self) -> Connection:
        return self._connection

    @property
    def committed(self) -> bool:
        """True once Threads confirmed a change in this invocation."""
        return self.confirmed_writes > 0

    def remaining(self) -> float:
        return float("inf") if self.deadline is None else self.deadline - self.clock()

    # -- public calls --------------------------------------------------------

    def read(self, call: Call) -> Answer:
        return self._call(call, mutating=False)

    def write(self, call: Call) -> Answer:
        """A change; its answer once Threads confirmed it with HTTP 200."""
        answer = self._call(call, mutating=True)
        self.confirmed_writes += 1
        return answer

    # -- answers -------------------------------------------------------------

    def scrub(self, value: Any) -> Any:
        """The token removed from every text and key of a parsed answer."""
        if isinstance(value, str):
            for form in self._forms:
                if form in value:
                    value = value.replace(form, "[redacted]")
            return value
        if isinstance(value, Mapping):
            return {self.scrub(k): self.scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.scrub(v) for v in value]
        return value

    def json(self, answer: Answer) -> Any:
        """The answer's JSON value (numbers with a point as Decimal), token removed.
        ValueError when it is not JSON."""
        return self.scrub(parse_json(answer.raw))

    def text(self, answer: Answer, limit: int = 100_000) -> str:
        return self.scrub(answer.raw.decode("utf-8", "replace"))[:limit]

    def usage_report(self) -> dict[str, Any] | None:
        return dict(self.usage) if self.usage else None

    def _note_usage(self, headers: Any) -> None:
        if headers is None or not hasattr(headers, "get"):
            return
        for name in USAGE_HEADERS:
            value = headers.get(name)
            if not isinstance(value, str) or not value.strip():
                continue
            text = errors.safe_text(self.scrub(value), 2000)
            try:
                parsed = parse_json(text.encode("utf-8"))
            except ValueError:
                parsed = text
            self.usage[name] = parsed if isinstance(parsed, (dict, list)) else text

    # -- one request ---------------------------------------------------------

    def _call(self, call: Call, *, mutating: bool) -> Answer:
        if not _PATH_RE.fullmatch(call.path):
            raise errors.invalid("Not a Threads endpoint")
        headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
        if call.token:
            headers["Authorization"] = "Bearer " + self._connection.access_token
        body = None
        if call.form is not None:
            body = urlencode(list(call.form)).encode("utf-8")
            if len(body) > MAX_REQUEST_BODY_BYTES:
                raise errors.invalid("The request is larger than the 1 MB this extension sends")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        url = self._connection.base_url + call.path
        if call.query:
            url += "?" + urlencode(list(call.query))
        request = Request(url, method=call.method, data=body, headers=headers)
        remaining = self.remaining()
        if remaining < MIN_CALL_WINDOW_SECONDS:
            raise DeadlineReached
        self._call_timeout = min(self._timeout_seconds, remaining)
        self.calls += 1
        if mutating:
            self.mutated = True
        expires = None if self.deadline is None else self.deadline + MIN_CALL_WINDOW_SECONDS
        progress: dict[str, Any] = {}
        if expires is None:
            return self._exchange(request, call, mutating, progress)
        outcome: dict[str, Any] = {}

        def work() -> None:
            try:
                outcome["value"] = self._exchange(request, call, mutating, progress)
            except BaseException as exc:  # handed to the caller below
                outcome["error"] = exc

        worker = threading.Thread(target=work, name="threads-call", daemon=True)
        worker.start()
        worker.join(max(0.0, expires - self.clock()))
        if worker.is_alive():
            confirmed = progress.get("confirmed")
            if isinstance(confirmed, Answer):
                # The status confirmed the write before its body finished arriving.
                return confirmed
            _late(mutating)
        if "error" in outcome:
            raise outcome["error"]
        return outcome["value"]

    def _exchange(
        self, request: Request, call: Call, mutating: bool, progress: dict[str, Any]
    ) -> Answer:
        expires = None if self.deadline is None else self.deadline + MIN_CALL_WINDOW_SECONDS
        try:
            with self._opener(
                request, timeout_seconds=self._call_timeout, purpose="Threads"
            ) as response:
                status = int(getattr(response, "status", 0) or getattr(response, "code", 0) or 0)
                headers = getattr(response, "headers", None) or {}
                self._note_usage(headers)
                confirmed: Answer | None = None
                if mutating and str(status) in SUCCESS:
                    # The status is known before the body: HTTP 200 confirms the write
                    # whatever happens to the body afterwards.
                    confirmed = Answer(
                        status,
                        b"",
                        _media(headers),
                        _kept_headers(headers, self.scrub),
                        unread="did not arrive in time",
                    )
                    progress["confirmed"] = confirmed
                try:
                    raw = read_bounded(
                        response,
                        call.limit,
                        mutating=mutating,
                        expires=expires,
                        clock=self.clock,
                        per_read=self._call_timeout,
                    )
                except ExtensionError as exc:
                    if confirmed is None:
                        raise
                    confirmed.unread = (
                        f"is larger than the {call.limit // (1024 * 1024)} MB this extension reads"
                        if exc.code == errors.RESPONSE_TOO_LARGE
                        else "did not arrive in time"
                    )
                    return confirmed
                except (OSError, http.client.HTTPException):
                    if confirmed is None:
                        raise
                    confirmed.unread = "was cut off by the connection"
                    return confirmed
        except HTTPError as exc:
            try:
                body = exc.read(MAX_ERROR_BODY_BYTES)
            except Exception:  # pragma: no cover - upstream body is optional
                body = b""
            self._note_usage(exc.headers)
            kept = _kept_headers(exc.headers, self.scrub)
            raise self.refusal(
                int(exc.code), body or b"", call, mutating=mutating, headers=kept
            ) from None
        except PinnedPeerError as exc:
            # Raised while resolving and pinning, before anything was sent.
            host = request.host
            if "cannot be resolved" in str(exc):
                raise ExtensionError(
                    errors.CONNECTION_FAILED,
                    f"{host} could not be resolved",
                    failure_class="transient",
                    retryable=True,
                    definitely_no_external_effect=True,
                    external_effect_status="failed",
                ) from None
            raise errors.no_effect(
                errors.BLOCKED_ADDRESS,
                f"{host} is not reachable under the host network policy",
            ) from None
        except TimeoutError:
            raise ExtensionError(
                errors.TIMEOUT_UNKNOWN if mutating else errors.TIMEOUT,
                "Threads did not answer in time" + (CHECK if mutating else ""),
                **_transport_failure_facts(mutating=mutating),
            ) from None
        except http.client.IncompleteRead:
            # Content-Length not reached, or a chunked answer that stopped before its end.
            if not mutating:
                raise errors.no_effect(
                    errors.INVALID_RESPONSE,
                    "Threads's answer was cut off before its end; it is not used",
                    failure_class="transient",
                    retryable=True,
                ) from None
            raise ExtensionError(
                errors.TIMEOUT_UNKNOWN,
                "Threads's answer was cut off before its end" + CHECK,
                **_transport_failure_facts(mutating=True),
            ) from None
        except (OSError, http.client.HTTPException):
            raise ExtensionError(
                errors.TIMEOUT_UNKNOWN if mutating else errors.CONNECTION_FAILED,
                "The connection to Threads failed" + (CHECK if mutating else ""),
                **_transport_failure_facts(mutating=mutating),
            ) from None
        kept = _kept_headers(headers, self.scrub)
        if status < 200 or status >= 300:
            raise self.refusal(
                status, raw[:MAX_ERROR_BODY_BYTES], call, mutating=mutating, headers=kept
            )
        if str(status) not in SUCCESS:
            raise undocumented(status, call, mutating=mutating)
        return Answer(status, raw, _media(headers), kept)

    # -- refusals ------------------------------------------------------------

    @staticmethod
    def graph_error(raw: bytes) -> Mapping[str, Any] | None:
        """The ``error`` object of the Graph API's documented error answer, when ``raw``
        is one: ``{"error": {..., "code": <integer>, ...}}``."""
        try:
            data = parse_json(raw)
        except ValueError:
            return None
        if not isinstance(data, Mapping):
            return None
        error = data.get("error")
        if not isinstance(error, Mapping):
            return None
        code = error.get("code")
        if isinstance(code, bool) or not isinstance(code, int):
            return None
        return error

    def detail(self, raw: bytes) -> str:
        """Threads' own words about a refusal; never the token."""
        error = self.graph_error(raw)
        if error is None:
            try:
                data = parse_json(raw)
            except ValueError:
                text = re.sub(r"<[^>]+>", " ", raw.decode("utf-8", "replace"))
                return errors.safe_text(self.scrub(text), 200)
            return errors.safe_text(self.scrub(json.dumps(data, default=str)), 200)
        error = self.scrub(dict(error))
        words = error.get("error_user_msg") or error.get("message") or ""
        text = errors.safe_text(words, 600)
        code = f"code {error.get('code')}"
        sub = error.get("error_subcode")
        if isinstance(sub, int) and not isinstance(sub, bool):
            code += f", subcode {sub}"
        trace = error.get("fbtrace_id")
        if isinstance(trace, str) and trace.strip():
            code += f", fbtrace_id {errors.safe_text(trace, 64)}"
        return f"{text} ({code})" if text else f"({code})"

    def refusal(
        self,
        status: int,
        raw: bytes,
        call: Call,
        *,
        mutating: bool,
        headers: Mapping[str, str] | None = None,
    ) -> ExtensionError:
        shown = call.shown
        error = self.graph_error(raw)
        detail = self.detail(raw)
        suffix = f": {detail}" if detail else ""
        retry_after = parse_retry_after((headers or {}).get("Retry-After"))
        code_number = int(error["code"]) if error is not None else None
        certain = not mutating or (error is not None and 400 <= status < 500 and status != 408)
        if status == 429 or code_number in THROTTLE_CODES:
            code = errors.RATE_LIMITED
            wait = f"; Threads asks to wait {int(retry_after)} s" if retry_after else ""
            message = (
                f"Threads refused {shown}: a rate limit is reached (HTTP {status}){wait}{suffix}"
            )
        elif status == 401 or code_number in TOKEN_CODES:
            code = errors.AUTHENTICATION_FAILED
            message = (
                f"Threads refused {shown} (HTTP {status}){suffix}. Threads no longer accepts the "
                "connection's access token; it expired or was withdrawn. Enter a new one in the "
                "connection form"
            )
        elif status == 403 or permission_code(code_number):
            code = errors.AUTHENTICATION_FAILED
            message = (
                f"Threads refused {shown} (HTTP {status}){suffix}. The permission this step "
                "needs is missing from the connection's access token; authorize the permission "
                "the step names and enter the new access token"
            )
        elif 300 <= status < 400:
            code = errors.REDIRECT_REJECTED
            message = f"Threads redirected {shown} (HTTP {status}); redirects are not followed"
        elif status == 404:
            code = errors.NOT_FOUND
            message = f"Threads found nothing for {shown} (HTTP 404){suffix}"
        elif status == 409:
            code = errors.CONFLICT
            message = f"Threads refused {shown} as a conflict (HTTP 409){suffix}"
        elif status >= 500 or status == 408:
            code = errors.TIMEOUT if status in {408, 504} else errors.UPSTREAM_FAILURE
            message = f"Threads could not complete {shown} (HTTP {status}){suffix}"
        else:
            code = errors.UPSTREAM_VALIDATION_FAILED
            message = f"Threads refused {shown} (HTTP {status}){suffix}"
        if not certain:
            return unknown(message + CHECK, code, status)
        if mutating:
            message += "; nothing was changed"
        retryable = not mutating and (
            status >= 500 or status in {408, 429} or code == errors.RATE_LIMITED
        )
        return ExtensionError(
            code,
            message,
            failure_class="provider",
            retryable=retryable,
            definitely_no_external_effect=True,
            external_effect_status="failed",
            http_status=status,
            retry_after_seconds=retry_after
            if code == errors.RATE_LIMITED and not mutating
            else None,
        )


def undocumented(status: int, call: Call, *, mutating: bool) -> ExtensionError:
    """A 2xx answer other than HTTP 200: not taken as success."""
    message = f"Threads answered {call.shown} with HTTP {status}, not the HTTP 200 of a success"
    if mutating:
        return unknown(message + CHECK, errors.INVALID_RESPONSE, status)
    return errors.no_effect(
        errors.INVALID_RESPONSE,
        message,
        failure_class="provider",
        retryable=False,
        http_status=status,
    )


def unknown(message: str, code: str, status: int | None) -> ExtensionError:
    return ExtensionError(
        code,
        message,
        failure_class="provider",
        retryable=False,
        definitely_no_external_effect=False,
        external_effect_status="timeout_unknown",
        http_status=status,
    )


def _media(headers: Any) -> str:
    kind = str(headers.get("Content-Type") or "") if hasattr(headers, "get") else ""
    return kind.split(";")[0].strip().lower()


def _kept_headers(headers: Any, scrub: Callable[[Any], Any]) -> dict[str, str]:
    """The headers a step may use, the token removed before they are bounded (so a
    cut never leaves part of it)."""
    kept: dict[str, str] = {}
    if headers is None or not hasattr(headers, "get"):
        return kept
    for name in KEPT_HEADERS:
        value = headers.get(name)
        if isinstance(value, str) and value.strip():
            kept[name] = errors.safe_text(scrub(value), 2000)
    return kept


def dumps_json(value: Any) -> str:
    """JSON with ``Decimal`` written as an exact number (never through float).

    A Decimal outside ``numbers``' bounds is written as text in its own exponential
    notation, never expanded."""
    marker = secrets.token_hex(8)

    def default(item: Any) -> str:
        if isinstance(item, Decimal) and numbers.bounded(item):
            return f"@{marker}@{format(item, 'f')}@{marker}@"
        if isinstance(item, Decimal):
            return str(item)
        raise TypeError(f"{type(item).__name__} is not JSON")

    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=default)
    return re.sub(rf'"@{marker}@([-+0-9.]+)@{marker}@"', r"\1", text)


def _answer_number(integer: bool) -> Callable[[str], Any]:
    def read(text: str) -> Any:
        number = numbers.read(text, integer=integer)
        # Outside the bounds: kept as Threads wrote it, as text, never expanded.
        return text if number is None else number

    return read


_ANSWER_FLOAT = _answer_number(False)
_ANSWER_INT = _answer_number(True)


class TooDeep(ValueError):
    """Threads' answer nests deeper than ``nesting.MAX_ANSWER_DEPTH``; it is not read."""


def parse_json(raw: bytes) -> Any:
    """Any JSON value, numbers with a point read as Decimal; ValueError otherwise.

    A number outside ``numbers``' bounds (and NaN or Infinity) is kept as the text
    Threads wrote, so reading it never expands it or fails on it. An answer nested
    deeper than ``nesting.MAX_ANSWER_DEPTH`` (counted on the bytes, before parsing) is
    ``TooDeep`` and never reaches the JSON reader, so no RecursionError comes out."""
    if nesting.too_deep(raw, nesting.MAX_ANSWER_DEPTH):
        raise TooDeep(f"nested deeper than {nesting.MAX_ANSWER_DEPTH} levels")
    try:
        text = raw.decode("utf-8-sig", "strict") if raw else ""
    except UnicodeDecodeError as exc:
        raise ValueError("not UTF-8") from exc
    if not text.strip():
        raise ValueError("empty")
    try:
        return json.loads(
            text, parse_float=_ANSWER_FLOAT, parse_int=_ANSWER_INT, parse_constant=str
        )
    except json.JSONDecodeError as exc:
        raise ValueError("bad JSON") from exc
    except RecursionError as exc:  # pragma: no cover - the depth check comes first
        raise TooDeep("nested too deeply") from exc


def read_bounded(
    response: Any,
    limit: int,
    *,
    mutating: bool = False,
    expires: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    per_read: float | None = None,
) -> bytes:
    """Read at most ``limit`` bytes before ``expires``; a longer answer is an error."""
    buffer = bytearray()
    sock = _socket_of(response)
    while True:
        if expires is not None:
            left = expires - clock()
            if left <= 0:
                _late(mutating)
            if sock is not None:
                try:
                    sock.settimeout(max(0.5, min(left, per_read or left)))
                except OSError:  # pragma: no cover - a closed socket fails the read below
                    pass
        chunk = response.read(min(CHUNK_BYTES, limit + 1 - len(buffer)))
        if not chunk:
            # http.client ends a read short of Content-Length without an error when the
            # connection closes; the bytes still owed mean the answer was cut off.
            owed = getattr(response, "length", None)
            if isinstance(owed, int) and not isinstance(owed, bool) and owed > 0:
                raise http.client.IncompleteRead(bytes(buffer), owed)
            break
        buffer.extend(chunk)
        if expires is not None and clock() > expires:
            _late(mutating)
        if len(buffer) > limit:
            if mutating:
                raise unknown(
                    "Threads' answer was too large to read" + CHECK,
                    errors.RESPONSE_TOO_LARGE,
                    None,
                )
            raise errors.no_effect(
                errors.RESPONSE_TOO_LARGE,
                f"Threads' answer is larger than the {limit // (1024 * 1024)} MB this extension "
                "reads; narrow the request",
            )
    return bytes(buffer)


def _late(mutating: bool) -> None:
    if not mutating:
        raise DeadlineReached
    raise ExtensionError(
        errors.TIMEOUT_UNKNOWN,
        "Threads' answer did not arrive in time" + CHECK,
        failure_class="transient",
        retryable=False,
        definitely_no_external_effect=False,
        external_effect_status="timeout_unknown",
    )


def _socket_of(response: Any) -> Any:
    for path in (("fp", "raw", "_sock"), ("fp", "fp", "raw", "_sock"), ("_sock",)):
        node = response
        for name in path:
            node = getattr(node, name, None)
        if node is not None and hasattr(node, "settimeout"):
            return node
    return None


def _transport_failure_facts(*, mutating: bool) -> dict[str, Any]:
    return {
        "failure_class": "transient",
        "retryable": not mutating,
        "definitely_no_external_effect": not mutating,
        "external_effect_status": "timeout_unknown" if mutating else "failed",
    }


__all__ = [
    "CHECK",
    "MIN_CALL_WINDOW_SECONDS",
    "Answer",
    "Call",
    "DeadlineReached",
    "ThreadsTransport",
    "TooDeep",
    "dumps_json",
    "parse_json",
    "read_bounded",
    "undocumented",
    "unknown",
]
