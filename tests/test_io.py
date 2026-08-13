import json
from pathlib import Path

import pytest
from conftest import make_trace, make_workflow

from taskprint.errors import SchemaVersionError
from taskprint.io import (
    load_candidate_evidence,
    load_outcome_contract,
    load_traces,
    load_workflow,
    save_traces,
    save_workflow,
)


def test_trace_jsonl_roundtrip(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "traces.jsonl"
    save_traces([make_trace()], destination)
    assert load_traces(destination) == [make_trace()]


def test_workflow_roundtrip(tmp_path: Path) -> None:
    destination = tmp_path / "workflow.json"
    workflow = make_workflow()
    save_workflow(workflow, destination)
    assert load_workflow(destination).fingerprint == workflow.fingerprint


def test_migrates_v01_workflow(tmp_path: Path) -> None:
    old = {
        "schema_version": "taskprint/0.1",
        "name": "old",
        "task": "Old",
        "nodes": [{"id": "n1", "action": "done", "kind": "output", "observed_count": 1}],
        "edges": [],
        "start": "n1",
        "terminals": ["n1"],
        "trace_count": 1,
    }
    source = tmp_path / "old.json"
    source.write_text(json.dumps(old), encoding="utf-8")
    migrated = load_workflow(source)
    assert migrated.schema_version == "taskprint/1.0"
    assert migrated.nodes[0].success_count == 1


def test_rejects_unknown_schema(tmp_path: Path) -> None:
    source = tmp_path / "future.json"
    source.write_text(json.dumps({"schema_version": "taskprint/99"}), encoding="utf-8")
    with pytest.raises(SchemaVersionError):
        load_workflow(source)


def test_invalid_json_is_not_silently_accepted(tmp_path: Path) -> None:
    source = tmp_path / "bad.json"
    source.write_text("not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_workflow(source)


def test_loads_objective_and_candidate_artifacts() -> None:
    root = Path(__file__).parents[1] / "examples" / "refund"
    contract = load_outcome_contract(root / "objectives.json")
    candidates = load_candidate_evidence(root / "candidates.json")
    assert contract.objectives[0].name == "successful resolution rate"
    assert [candidate.name for candidate in candidates] == [
        "manual-review-first",
        "policy-check-first",
    ]
