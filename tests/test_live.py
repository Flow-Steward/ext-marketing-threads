"""Read-only steps against the real Threads API, with a token from THREADS_TOKEN_FILE.

Skipped without the variable. Only reads: nothing is published, hidden or deleted.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from runtime.operations import handle_runtime
from support import payload

TOKEN_FILE = os.environ.get("THREADS_TOKEN_FILE")
pytestmark = pytest.mark.skipif(not TOKEN_FILE, reason="THREADS_TOKEN_FILE is not set")


def live(operation_id: str, given: dict | None = None) -> dict:
    token = Path(str(TOKEN_FILE)).read_text(encoding="utf-8").strip()
    response = handle_runtime(payload(operation_id, given or {}, token=token))
    assert token not in str(response)
    return response


def test_the_connection_is_accepted() -> None:
    response = live("test_connection")
    assert response["ok"] is True, response["error"]
    assert response["result"]["user_id"]


def test_my_posts_and_limits_can_be_read() -> None:
    posts = live("list_my_posts", {"max_posts": 5})
    assert posts["ok"] is True, posts["error"]
    limits = live("get_publishing_limit")
    assert limits["ok"] is True, limits["error"]
