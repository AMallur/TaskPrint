from __future__ import annotations

from taskprint import Event, EventKind, Trace, Workflow, WorkflowEdge, WorkflowNode


def make_trace(
    trace_id: str = "t1",
    *,
    success: bool = True,
    actions: tuple[str, ...] = ("start", "finish"),
) -> Trace:
    return Trace(
        id=trace_id,
        task="Example task",
        success=success,
        events=[Event(type=action, kind=EventKind.ACTION) for action in actions],
    )


def make_workflow(*, cycle: bool = False) -> Workflow:
    nodes = [
        WorkflowNode(id="n1", action="start", kind=EventKind.ACTION, support=1),
        WorkflowNode(id="n2", action="finish", kind=EventKind.OUTPUT, support=1),
    ]
    edges = [WorkflowEdge(source="n1", target="n2", probability=1)]
    if cycle:
        edges.append(WorkflowEdge(source="n2", target="n1", probability=1, is_cycle=True))
    return Workflow(
        name="example",
        task="Example task",
        nodes=nodes,
        edges=edges,
        start="n1",
        terminals=["n2"],
        trace_count=1,
        successful_trace_count=1,
    )
