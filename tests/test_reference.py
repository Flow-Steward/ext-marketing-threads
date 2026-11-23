"""The pinned facts are what the pinned documentation pages say."""

from __future__ import annotations

import json
import sys

import pytest
from support import BUNDLE

sys.path.insert(0, str(BUNDLE / "tests" / "reference"))

import extract_reference  # noqa: E402

PRESENT = all((extract_reference.SOURCES / name).exists() for name in extract_reference.PAGES)


def facts() -> dict:
    return json.loads(extract_reference.OUTPUT.read_text(encoding="utf-8"))


@pytest.mark.skipif(not PRESENT, reason="the documentation pages are not committed")
def test_the_facts_are_extracted_from_the_pinned_pages() -> None:
    assert extract_reference.build() == facts()


def test_a_changed_page_is_refused(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    page = '<html><pre data-testid="developer-docs-markdown-page"># Changed</pre></html>'
    (tmp_path / "reference_debug.md").write_text(page, encoding="utf-8")
    monkeypatch.setattr(extract_reference, "SOURCES", tmp_path)
    with pytest.raises(SystemExit, match="the page changed"):
        extract_reference.load("reference_debug.md")


def test_every_page_is_pinned_with_its_address() -> None:
    pins = extract_reference.pins()
    pages = facts()["source"]["pages"]
    assert set(pins) == set(extract_reference.PAGES) == {p["name"] for p in pages}
    for p in pages:
        assert p["sha256"] == pins[p["name"]] and len(p["sha256"]) == 64
        assert p["url"] == extract_reference.PAGES[p["name"]]
    assert facts()["source"]["downloaded"] == "2026-11-23"
    assert facts()["source"]["machine_readable_specification"] is False


def test_the_documented_facts_the_steps_rely_on() -> None:
    data = facts()
    limits = data["limits"]
    assert limits["api_version"] == "v1.0" and limits["hosts"][0] == "graph.threads.com"
    assert limits["text_max_characters"] == 500
    assert (limits["carousel_min_children"], limits["carousel_max_children"]) == (2, 20)
    assert limits["status_check_max_minutes"] == 5 and limits["media_by_public_url"] is True
    assert limits["container_statuses"] == [
        "EXPIRED",
        "ERROR",
        "FINISHED",
        "IN_PROGRESS",
        "PUBLISHED",
    ]
    assert data["graph"]["throttle_codes"] == [4, 17, 32, 613]
    assert data["graph"]["usage_headers"] == ["X-App-Usage", "X-Business-Use-Case-Usage"]
    assert "code" in data["graph"]["error_form_keys"]


def test_the_token_facts_behind_the_static_connection() -> None:
    auth = facts()["auth"]
    # The code exchange gives a short-lived token without expires_in or refresh_token ...
    assert auth["code_exchange_answer_fields"] == ["access_token", "token_type", "user_id"]
    assert auth["short_lived"] is True
    # ... and only Threads' own grants make it long-lived or renew it.
    assert auth["long_lived_grant"] == "th_exchange_token"
    assert auth["refresh_grant"] == "th_refresh_token"
    assert auth["refresh_takes_a_refresh_token"] is False
