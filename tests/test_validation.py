from conftest import make_workflow

from taskprint import EventKind, WorkflowNode
from taskprint.validation import validate_workflow


def test_valid_workflow_has_no_errors() -> None:
    assert validate_workflow(make_workflow()).valid


def test_unreachable_node_is_error() -> None:
    workflow = make_workflow()
    workflow.nodes.append(WorkflowNode(id="n3", action="lost", kind=EventKind.ACTION))
    report = validate_workflow(workflow)
    assert not report.valid
    assert any(issue.code == "unreachable_node" for issue in report.issues)


def test_terminal_with_outgoing_edge_warns() -> None:
    report = validate_workflow(make_workflow(cycle=True))
    assert report.valid
    assert any(issue.code == "terminal_has_edges" for issue in report.issues)
