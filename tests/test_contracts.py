"""The generated contracts are what the pinned facts produce, and they cover every endpoint."""

from __future__ import annotations

import json
import sys

import pytest
import yaml
from support import BUNDLE

sys.path.insert(0, str(BUNDLE / "tests" / "reference"))

import build_contracts  # noqa: E402

from runtime import catalog, composites, generic  # noqa: E402

OUTPUTS = build_contracts.outputs()


@pytest.mark.parametrize("path", sorted(OUTPUTS))
def test_a_generated_file_does_not_drift(path: str) -> None:
    on_disk = (BUNDLE / path).read_text(encoding="utf-8")
    assert on_disk == build_contracts.render(path, OUTPUTS[path]), (
        f"run build_contracts.py ({path})"
    )


def test_every_documented_endpoint_is_a_step_or_has_a_reason() -> None:
    facts = build_contracts.facts()
    documented = {(o["method"], o["path"]) for o in facts["operations"]}
    documented |= {(o["method"], o["path"]) for o in facts["guide_operations"]}
    steps = {(e["method"], e["path"]) for e in generic.registry().values()}
    assert documented == steps | set(build_contracts.EXCLUDED)
    assert not steps & set(build_contracts.EXCLUDED)
    assert len(steps) == 25 and len(build_contracts.EXCLUDED) == 6
    assert all(len(reason) > 40 for reason in build_contracts.EXCLUDED.values())


def manifest() -> dict:
    return yaml.safe_load((BUNDLE / "extension.yaml").read_text(encoding="utf-8"))


def test_the_manifest_lists_exactly_the_routable_steps() -> None:
    ops = yaml.safe_load((BUNDLE / "contracts/operation_manifest.yaml").read_text(encoding="utf-8"))
    ids = [o["operation_id"] for o in ops["operations"]]
    assert len(ids) == len(set(ids)) == 34
    assert set(ids) == catalog.OPERATION_IDS
    actions = yaml.safe_load((BUNDLE / "ui/actions/actions.yaml").read_text(encoding="utf-8"))
    assert {a["action_id"] for a in actions["actions"]} == catalog.OPERATION_IDS


def test_every_write_is_a_suppressed_external_effect() -> None:
    effects = manifest()["external_effects"]
    assert {e["operation_id"] for e in effects} == catalog.EFFECT_OPERATION_IDS
    assert all(e["test_mode_behavior"] == "suppress" for e in effects)
    assert composites.COMPOSITE_WRITES <= catalog.EFFECT_OPERATION_IDS
    assert len(catalog.EFFECT_OPERATION_IDS) == 8


def test_every_result_has_warnings_and_rate_limit_usage() -> None:
    ops = yaml.safe_load((BUNDLE / "contracts/operation_manifest.yaml").read_text(encoding="utf-8"))
    for op in ops["operations"]:
        names = {o["name"] for o in op["outputs"]}
        assert {"warnings", "rate_limit_usage"} <= names, op["operation_id"]
        if op["operation_id"] in catalog.EFFECT_OPERATION_IDS:
            assert {"processing", "applied", "check", "external_effect_status"} <= names


def test_identity_and_links() -> None:
    data = manifest()
    # Flow Steward installs the bundle in a folder named after the id ("." and "-" become
    # "_"); the checkout folder itself may have any name (the repository's, on GitHub).
    assert data["extension_id"] == "flowsteward.threads"
    assert data["extension_id"].replace(".", "_").replace("-", "_") == "flowsteward_threads"
    assert data["version"] == "0.1.0"
    assert data["vendor"] == {
        "name": "Flow Steward",
        "support_url": "https://github.com/Flow-Steward/ext-marketing-threads/issues",
        "website_url": "https://github.com/Flow-Steward/ext-marketing-threads",
    }
    assert data["egress"]["hosts"] == ["graph.threads.com"]
    assert data["entrypoint"]["timeout_seconds"] == 600


def test_the_connection_is_a_static_token_like_the_instagram_extension() -> None:
    types = yaml.safe_load((BUNDLE / "contracts/connection_types.yaml").read_text(encoding="utf-8"))
    (only,) = types["connection_types"]
    assert only["auth"]["type"] == "static_secret"
    assert set(only["secret_schema"]["properties"]) == {"access_token"}
    assert "oauth_providers" not in manifest()["runtime"]["extension_contract_v2"]


def test_the_registry_is_built_from_the_pinned_facts() -> None:
    import hashlib

    source = json.loads(generic.REGISTRY_FILE.read_text(encoding="utf-8"))["source"]
    assert source["facts_sha256"] == hashlib.sha256(build_contracts.FACTS.read_bytes()).hexdigest()
    assert source["api_version"] == "v1.0"
