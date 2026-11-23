"""main.py and health.py as the host runs them: a subprocess, JSON in and out."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest
from support import BUNDLE, TOKEN, payload

import main


def invoke(request: Any) -> tuple[int, dict[str, Any]]:
    code, text = invoke_raw(request)
    return code, json.loads(text)


def invoke_raw(request: Any) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-B", "main.py"],
        cwd=BUNDLE,
        input=json.dumps(request) if not isinstance(request, bytes) else request.decode(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return proc.returncode, proc.stdout


def test_a_test_mode_write_answers_without_network() -> None:
    request = payload("publish_post", {"media_type": "TEXT", "text": "Hi"}, test_mode=True)
    code, response = invoke(request)
    assert code == 0, response
    assert response["definitely_no_external_effect"] is True
    assert response["result"]["warnings"]
    assert TOKEN not in json.dumps(response)


def test_an_unknown_operation_is_refused() -> None:
    code, response = invoke(payload("drop_everything"))
    assert code == 2
    assert response["error_code"] == "unsupported_operation"
    assert response["result"]["warnings"] == [] and response["warnings"] == []


def test_a_request_that_is_not_json_is_refused() -> None:
    code, response = invoke(b"{not json")
    assert code == 2
    assert response["error_code"] == "invalid_payload"


@pytest.mark.parametrize("number", ["1e1000000", "9" * 5000, "1" * 41])
def test_a_number_outside_the_bounds_is_refused_before_anything_is_sent(number: str) -> None:
    raw = json.dumps(payload("get_location", {"location_id": "1"})).replace('"1"}', number + "}", 1)
    code, text = invoke_raw(raw.encode())
    assert len(text) < 2_000
    response = json.loads(text)
    assert code == 2 and response["error_code"] == "invalid_payload"
    assert response["definitely_no_external_effect"] is True


def test_the_last_resort_answer_keeps_the_facts_of_a_write() -> None:
    huge = {
        "ok": True,
        "result": {"id": "1", "blob": "x" * 6_000_000},
        "external_effect_status": "succeeded",
        "definitely_no_external_effect": False,
    }
    final, _ = main._bounded_serialized_response(huge)
    assert final["ok"] is True and final["external_effect_status"] == "succeeded"
    assert final["result"]["id"] == "1" and "blob" not in final["result"]


def test_health_answers_without_network() -> None:
    proc = subprocess.run(
        [sys.executable, "-B", "health.py"], cwd=BUNDLE, capture_output=True, text=True, check=True
    )
    report = json.loads(proc.stdout)
    assert report["ok"] is True
    assert report["extension_id"] == "flowsteward.threads"
    assert report["declared_operations"] == 34
    assert report["effect_operations"] == 8
