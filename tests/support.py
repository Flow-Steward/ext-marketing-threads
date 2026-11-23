"""A fake Threads API and helpers."""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlsplit

from runtime.operations import handle_runtime
from runtime.transport import ThreadsTransport

BUNDLE = Path(__file__).resolve().parents[1]
TOKEN = "THAAfixture-threads-user-access-token-0123456789abcdef"  # pragma: allowlist secret
JSON = "application/json"


class Call:
    def __init__(self, request: Any) -> None:
        parts = urlsplit(request.full_url)
        self.url = request.full_url
        self.host = parts.hostname
        self.path = parts.path
        self.query = parse_qsl(parts.query, keep_blank_values=True)
        self.verb = request.get_method()
        self.headers = {k.lower(): v for k, v in request.header_items()}
        self.raw_body = request.data or b""
        self.form = dict(parse_qsl(self.raw_body.decode("utf-8"), keep_blank_values=True))

    @property
    def key(self) -> str:
        return f"{self.verb} {self.path.removeprefix('/v1.0')}"

    def q(self, name: str) -> str | None:
        return dict(self.query).get(name)


class Response:
    def __init__(self, status: int, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self._body: bytes = body
        self.headers = Message()
        for key, value in (headers if headers is not None else {"Content-Type": JSON}).items():
            self.headers[key] = value

    def read(self, size: int = -1) -> bytes:
        chunk, self._body = (
            (self._body, b"") if size < 0 else (self._body[:size], self._body[size:])
        )
        return chunk

    def __enter__(self) -> Response:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


def ok(value: Any = None, status: int = 200, headers: dict[str, str] | None = None) -> Response:
    raw = b"" if value is None else json.dumps(value).encode("utf-8")
    return Response(status, raw, headers)


def raw(status: int, body: bytes, content_type: str | None = JSON, **headers: str) -> Response:
    head = {k.replace("_", "-"): v for k, v in headers.items()}
    if content_type is not None:
        head["Content-Type"] = content_type
    return Response(status, body, head)


def graph_error(
    code: int = 100, message: str = "Invalid parameter", subcode: int | None = None
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "message": message,
        "type": "OAuthException",
        "code": code,
        "fbtrace_id": "AbCdEf123",
    }
    if subcode is not None:
        error["error_subcode"] = subcode
    return {"error": error}


def refuse(status: int, body: Any = None, **headers: str) -> HTTPError:
    data = b"" if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
    message = Message()
    message["Content-Type"] = JSON
    for key, value in headers.items():
        message[key.replace("_", "-")] = value
    return HTTPError(
        "https://graph.threads.com/v1.0/x", status, "refused", message, io.BytesIO(data)
    )


def page(items: list[Any], after: str | None = None, *, more: bool = False) -> dict[str, Any]:
    paging: dict[str, Any] = {"cursors": {"before": "B0"}}
    if after:
        paging["cursors"]["after"] = after
    if more:
        paging["next"] = f"https://graph.threads.com/v1.0/x?access_token={TOKEN}&after={after}"
    return {"data": items, "paging": paging}


class FakeThreads:
    """Answers requests in order (a list) or by key (``"GET /me"`` -> answer)."""

    def __init__(self, *answers: Any, routes: dict[str, Any] | None = None) -> None:
        self.answers = list(answers)
        self.routes = routes or {}
        self.calls: list[Call] = []

    def __call__(self, request: Any, *, timeout_seconds: float, purpose: str) -> Any:
        call = Call(request)
        self.calls.append(call)
        if call.key in self.routes:
            answer = self.routes[call.key]
            if isinstance(answer, list):
                answer = answer.pop(0)
        elif self.answers:
            answer = self.answers.pop(0)
        else:
            raise AssertionError(f"unexpected request {call.key}")
        if callable(answer) and not isinstance(answer, (Response, HTTPError)):
            answer = answer(call)
        if isinstance(answer, BaseException):
            raise answer
        return answer


class Clock:
    """A clock that moves only when the step sleeps (or a test moves it)."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def payload(
    operation_id: str,
    operation_input: dict[str, Any] | None = None,
    *,
    token: str = TOKEN,
    test_mode: bool = False,
    connection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_connection = connection or {
        "connection_id": "conn-1",
        "connection_type": "threads_account",
        "config": {},
        "secrets": {"access_token": token},
    }
    return {
        "mode": "action",
        "contract_version": "extension_host_v2",
        "runtime_context": {
            "test_mode": test_mode,
            "group_id": None,
            "for_each_id": None,
            "step_id": "step-1",
            "step_execution_id": "exec-1",
        },
        "action": {
            "action_id": operation_id,
            "input": {"connection_ref": "conn-1", **(operation_input or {})},
            "target": {"connection": target_connection},
        },
    }


def run(
    operation_id: str,
    operation_input: dict[str, Any] | None = None,
    fake: FakeThreads | None = None,
    *,
    clock: Clock | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    fake = fake if fake is not None else FakeThreads()
    clock = clock or Clock()

    def factory(connection: Any) -> ThreadsTransport:
        return ThreadsTransport(connection, opener=fake, clock=clock, sleep=clock.sleep)

    return handle_runtime(
        payload(operation_id, operation_input, **kwargs), transport_factory=factory
    )


def text_of(response: dict[str, Any]) -> str:
    return json.dumps(response, default=str)


Handler = Callable[[Call], Any]
