"""Table T: the outcome of every write is decided by runtime/outcome.py, cell by cell.

Each cell is a status × Content-Type × body × step class; ``expected`` says what the
table promises independently of the code. The classes are represented by
``publish_media_container`` (needs_id: Threads answers ``{"id"}``) and ``delete_post``
(confirm: Threads answers ``{"success": true}``).
"""

from __future__ import annotations

import http.client
import itertools
import json
from typing import Any

import pytest
from support import FakeThreads, Response, run

from runtime import generic, outcome

STEPS = {
    "needs_id": ("publish_media_container", {"creation_id": "111"}),
    "confirm": ("delete_post", {"threads_media_id": "222"}),
}
STATUSES = [200, 201]
TYPES = ["application/json", "text/html", None]
BODIES = [
    "empty",
    "good",
    "wrong_form",
    "said_no",
    "not_json",
    "broken_json",
    "deep",
    "too_large",
    "cut_off",
]


class CutOff(Response):
    """A body that breaks off after its first bytes."""

    def __init__(self, status: int, body: bytes, headers: dict[str, str] | None = None) -> None:
        super().__init__(status, body, headers)
        self.first: bytes = body[:5]

    def read(self, size: int = -1) -> bytes:
        if self.first:
            chunk, self.first = self.first, b""
            return chunk
        raise http.client.IncompleteRead(b"")


def body_of(kind: str, cls: str) -> bytes:
    good: dict[str, Any] = (
        {"id": "333"} if cls == "needs_id" else {"success": True, "deleted_id": "222"}
    )
    return {
        "empty": b"",
        "good": json.dumps(good).encode(),
        "wrong_form": json.dumps({"result": "ok"}).encode(),
        "said_no": json.dumps({"success": False}).encode(),
        "not_json": b"<html>done</html>",
        "broken_json": b'{"id": "333"',
        "deep": b"[" * 49 + b"]" * 49,
        "too_large": b"{" + b" " * (31 * 1024 * 1024),
        "cut_off": b'{"id": "333", "x": "' + b"y" * 100,
    }[kind]


def expected(status: int, ctype: str | None, kind: str, cls: str) -> str:
    """What table T says, first row that applies."""
    if status != 200:
        return "unknown"  # T1: not the documented success
    if ctype is not None and "json" not in ctype:
        return "unknown"  # T2
    if kind in {"too_large", "cut_off", "empty"}:
        return "unknown"  # T4: the class needs the body
    if kind in {"not_json", "broken_json"}:
        return "unknown"  # T3
    if kind == "deep":
        return "unknown"  # T4
    if kind == "said_no":
        return "refused" if cls == "confirm" else "unknown"  # T5
    if kind == "wrong_form":
        return "unknown"  # T5
    return "success"  # T6


CELLS = list(itertools.product(STATUSES, TYPES, BODIES, STEPS))


@pytest.mark.parametrize(("status", "ctype", "kind", "cls"), CELLS)
def test_the_outcome_of_a_write_follows_table_t(
    status: int, ctype: str | None, kind: str, cls: str
) -> None:
    operation_id, given = STEPS[cls]
    headers = {} if ctype is None else {"Content-Type": ctype}
    answer = (CutOff if kind == "cut_off" else Response)(status, body_of(kind, cls), headers)
    response = run(operation_id, given, FakeThreads(answer))
    want = expected(status, ctype, kind, cls)
    if want == "success":
        assert response["ok"] is True, response
        assert response["external_effect_status"] == "succeeded"
        result = response["result"]
        if cls == "needs_id":
            assert result["id"] == "333"
        else:
            assert result["data"]["success"] is True
    elif want == "refused":
        assert response["ok"] is False
        assert response["definitely_no_external_effect"] is True
        assert response["external_effect_status"] == "failed"
        assert "nothing was changed" in response["error"]
    else:
        assert response["ok"] is False, response
        assert response["error_code"] in {
            "invalid_response",
            "response_too_large",
            "timeout_unknown",
        }
        assert response["external_effect_status"] == "timeout_unknown"
        assert response["definitely_no_external_effect"] is False


def test_there_are_108_cells() -> None:
    assert len(CELLS) == 108


def test_every_write_path_goes_through_the_one_function(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    real = outcome.write_outcome

    def spy(context: Any, write_class: str, answer: Any, shown: str) -> Any:
        seen.append(shown)
        return real(context, write_class, answer, shown)

    monkeypatch.setattr(outcome, "write_outcome", spy)
    run("delete_post", {"threads_media_id": "1"}, FakeThreads(Response(200, b'{"success":true}')))
    fake = FakeThreads(
        Response(200, b'{"id":"10"}'),
        Response(200, b'{"id":"10","status":"FINISHED"}'),
        Response(200, b'{"id":"20"}'),
        Response(200, b'{"id":"20","permalink":"https://www.threads.com/t/x"}'),
    )
    run("publish_post", {"media_type": "TEXT", "text": "hi"}, fake)
    assert seen == [
        "DELETE /{threads-media-id}",
        "POST /{threads-user-id}/threads",
        "POST /{threads-user-id}/threads_publish",
    ]


def test_every_generated_write_has_a_class() -> None:
    for operation_id, entry in generic.registry().items():
        if entry["kind"] == "write":
            assert entry["write_class"] in outcome.CLASSES, operation_id
        else:
            assert entry["write_class"] is None, operation_id
