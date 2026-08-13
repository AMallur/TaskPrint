from pathlib import Path

import pytest
from conftest import make_trace

from taskprint import HandlerRegistry, WorkflowRunner, evaluate, induce
from taskprint.errors import TraceValidationError
from taskprint.induce import InductionConfig
from taskprint.io import load_traces

TRACES = Path(__file__).parents[1] / "examples" / "refund" / "traces.jsonl"


def test_induces_branching_workflow() -> None:
    traces = load_traces(TRACES)
    workflow = induce(traces)
    assert workflow.trace_count == 3
    assert len(workflow.nodes) == 6
    check_policy = next(node for node in workflow.nodes if node.action == "check_policy")
    edges = workflow.outgoing(check_policy.id)
    assert len(edges) == 2
    assert [edge.probability for edge in edges] == [2 / 3, 1 / 3]


def test_training_traces_are_explained() -> None:
    traces = load_traces(TRACES)
    report = evaluate(induce(traces), traces)
    assert report.exact_path_rate == 1
    assert report.event_coverage == 1
    assert report.transition_coverage == 1


def test_runner_uses_most_likely_path() -> None:
    workflow = induce(load_traces(TRACES))
    registry = HandlerRegistry()
    for node in workflow.nodes:
        registry.register(node.action, lambda current, state: current.action)
    result = WorkflowRunner(workflow, registry).run()
    assert result.status == "completed"
    assert [step.action for step in result.steps][-2:] == ["issue_refund", "notify_customer"]


def test_failure_paths_are_counted() -> None:
    traces = [
        make_trace("ok", actions=("start", "finish")),
        make_trace("bad", success=False, actions=("start", "error")),
    ]
    workflow = induce(traces)
    assert workflow.successful_trace_count == 1
    assert workflow.failed_trace_count == 1
    error = next(node for node in workflow.nodes if node.action == "error")
    assert error.failure_count == 1
    assert error.success_count == 0


def test_can_exclude_failure_topology() -> None:
    traces = [
        make_trace("ok"),
        make_trace("bad", success=False, actions=("start", "error")),
    ]
    workflow = induce(traces, config=InductionConfig(include_failure_paths=False))
    assert {node.action for node in workflow.nodes} == {"start", "finish"}


def test_detects_cycles() -> None:
    workflow = induce([make_trace(actions=("a", "b", "a", "done"))])
    assert any(edge.is_cycle for edge in workflow.edges)


def test_rejects_duplicate_trace_ids() -> None:
    with pytest.raises(TraceValidationError, match="unique"):
        induce([make_trace(), make_trace()])


def test_rejects_mixed_task_names() -> None:
    other = make_trace("t2")
    other.task = "Other"
    with pytest.raises(TraceValidationError, match="multiple task"):
        induce([make_trace(), other])


def test_none_can_be_a_stable_parameter() -> None:
    workflow = induce([make_trace()])
    assert workflow.nodes[0].parameters["value"] is None
