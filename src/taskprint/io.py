from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .errors import SchemaVersionError
from .models import OutcomeContract, Trace, Workflow
from .objectives import CandidateEvidence

MAX_ARTIFACT_BYTES = 100 * 1024 * 1024


def _read_text(path: str | Path) -> str:
    source = Path(path)
    if source.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError(f"artifact exceeds {MAX_ARTIFACT_BYTES} bytes")
    return source.read_text(encoding="utf-8")


def _atomic_write(path: str | Path, content: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def migrate_workflow_payload(payload: dict[str, Any]) -> dict[str, Any]:
    version = payload.get("schema_version", "taskprint/0.1")
    if version == "taskprint/1.0":
        return payload
    if version != "taskprint/0.1":
        raise SchemaVersionError(f"unsupported workflow schema: {version}")
    migrated = dict(payload)
    migrated["schema_version"] = "taskprint/1.0"
    migrated.setdefault("successful_trace_count", migrated.get("trace_count", 0))
    migrated.setdefault("failed_trace_count", 0)
    for node in migrated.get("nodes", []):
        node.setdefault("success_count", node.get("observed_count", 0))
        node.setdefault("failure_count", 0)
        trace_count = migrated.get("trace_count", 1) or 1
        node.setdefault("support", node.get("observed_count", 0) / trace_count)
        node.setdefault("confidence", 0.0)
    for edge in migrated.get("edges", []):
        edge.setdefault("success_count", edge.get("observed_count", 0))
        edge.setdefault("failure_count", 0)
        edge.setdefault("confidence", 0.0)
        edge.setdefault("is_cycle", edge.get("source") == edge.get("target"))
    return migrated


def load_traces(path: str | Path) -> list[Trace]:
    source = Path(path)
    if source.suffix == ".jsonl":
        rows = [json.loads(line) for line in _read_text(source).splitlines() if line.strip()]
    else:
        payload = json.loads(_read_text(source))
        rows = payload if isinstance(payload, list) else payload.get("traces", [payload])
    return [Trace.model_validate(row) for row in rows]


def load_outcome_contract(path: str | Path) -> OutcomeContract:
    return OutcomeContract.model_validate_json(_read_text(path))


def load_candidate_evidence(path: str | Path) -> list[CandidateEvidence]:
    payload = json.loads(_read_text(path))
    rows = payload if isinstance(payload, list) else payload.get("candidates", [])
    return [CandidateEvidence.model_validate(row) for row in rows]


def save_traces(traces: Iterable[Trace], path: str | Path) -> None:
    _atomic_write(
        path, "\n".join(trace.model_dump_json(exclude_none=True) for trace in traces) + "\n"
    )


def load_workflow(path: str | Path) -> Workflow:
    payload = json.loads(_read_text(path))
    return Workflow.model_validate(migrate_workflow_payload(payload))


def save_workflow(workflow: Workflow, path: str | Path) -> None:
    _atomic_write(path, workflow.model_dump_json(indent=2, exclude_none=True) + "\n")
