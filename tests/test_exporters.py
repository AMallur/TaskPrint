import json

from conftest import make_workflow

from taskprint.exporters import schema_json, to_dot, to_handler_skeleton, to_mermaid


def test_mermaid_export_contains_edges() -> None:
    output = to_mermaid(make_workflow())
    assert "flowchart TD" in output
    assert "n1 -->|100%| n2" in output


def test_dot_export_is_valid_shape() -> None:
    output = to_dot(make_workflow())
    assert output.startswith('digraph "example"')
    assert output.rstrip().endswith("}")


def test_handler_skeleton_registers_every_action() -> None:
    output = to_handler_skeleton(make_workflow())
    assert 'registry.register("start", start)' in output
    assert 'registry.register("finish", finish)' in output


def test_schemas_are_json() -> None:
    assert json.loads(schema_json("workflow"))["title"] == "Workflow"
    assert json.loads(schema_json("trace"))["title"] == "Trace"
