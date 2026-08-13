from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from taskprint import Event, EventKind, Trace, Workflow, WorkflowEdge, WorkflowNode


def test_rejects_dangling_edge() -> None:
    with pytest.raises(ValidationError):
        Workflow(
            name="bad",
            task="bad",
            nodes=[WorkflowNode(id="n1", action="start", kind=EventKind.ACTION)],
            edges=[WorkflowEdge(source="n1", target="missing", probability=1)],
            start="n1",
            terminals=["n1"],
            trace_count=1,
        )


def test_rejects_duplicate_edges() -> None:
    with pytest.raises(ValidationError, match="duplicate edge"):
        Workflow(
            name="bad",
            task="bad",
            nodes=[
                WorkflowNode(id="n1", action="start", kind=EventKind.ACTION),
                WorkflowNode(id="n2", action="end", kind=EventKind.OUTPUT),
            ],
            edges=[
                WorkflowEdge(source="n1", target="n2", probability=0.5),
                WorkflowEdge(source="n1", target="n2", probability=0.5),
            ],
            start="n1",
            terminals=["n2"],
            trace_count=1,
        )


def test_rejects_non_monotonic_trace() -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError, match="monotonic"):
        Trace(
            id="t1",
            task="x",
            events=[
                Event(type="later", timestamp=now),
                Event(type="earlier", timestamp=now - timedelta(seconds=1)),
            ],
        )


def test_fingerprint_ignores_created_at_and_metadata() -> None:
    values = dict(
        name="stable",
        task="stable",
        nodes=[WorkflowNode(id="n1", action="x", kind=EventKind.ACTION)],
        start="n1",
        terminals=["n1"],
        trace_count=1,
    )
    first = Workflow(**values, metadata={"a": 1})
    second = Workflow(**values, metadata={"b": 2})
    assert first.fingerprint == second.fingerprint
