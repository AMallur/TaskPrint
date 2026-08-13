from __future__ import annotations

import json
import re
from typing import Any

from .models import Trace, Workflow


def _safe_identifier(value: str) -> str:
    result = re.sub(r"\W+", "_", value).strip("_")
    if not result or result[0].isdigit():
        result = f"action_{result}"
    return result


def to_mermaid(workflow: Workflow) -> str:
    lines = ["flowchart TD"]
    terminal_set = set(workflow.terminals)
    for node in workflow.nodes:
        label = f"{node.action}\\n{node.kind.value}".replace('"', "'")
        shape = f'(("{label}"))' if node.id in terminal_set else f'["{label}"]'
        lines.append(f"    {node.id}{shape}")
    for edge in workflow.edges:
        cycle = " · loop" if edge.is_cycle else ""
        lines.append(f"    {edge.source} -->|{edge.probability:.0%}{cycle}| {edge.target}")
    return "\n".join(lines) + "\n"


def to_dot(workflow: Workflow) -> str:
    lines = [f'digraph "{workflow.name}" {{', "  rankdir=LR;"]
    for node in workflow.nodes:
        label = node.action.replace('"', r"\"")
        shape = "doublecircle" if node.id in workflow.terminals else "box"
        lines.append(f'  {node.id} [label="{label}", shape={shape}];')
    for edge in workflow.edges:
        lines.append(f'  {edge.source} -> {edge.target} [label="{edge.probability:.0%}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def to_handler_skeleton(workflow: Workflow) -> str:
    actions = sorted(
        {_safe_identifier(node.action): node.action for node in workflow.nodes}.items()
    )
    lines = [
        '"""Generated Taskprint handler skeleton. Replace every NotImplementedError."""',
        "",
        "from typing import Any",
        "",
        "from taskprint import HandlerRegistry, WorkflowNode",
        "",
    ]
    for identifier, action in actions:
        lines.extend(
            [
                f"def {identifier}(node: WorkflowNode, state: dict[str, Any]) -> Any:",
                f'    """Implement `{action}`."""',
                f'    raise NotImplementedError("implement {action}")',
                "",
            ]
        )
    lines.extend(
        ["", "def build_registry() -> HandlerRegistry:", "    registry = HandlerRegistry()"]
    )
    for identifier, action in actions:
        lines.append(f'    registry.register("{action}", {identifier})')
    lines.extend(["    return registry", ""])
    return "\n".join(lines)


def workflow_json_schema() -> dict[str, Any]:
    return Workflow.model_json_schema()


def trace_json_schema() -> dict[str, Any]:
    return Trace.model_json_schema()


def schema_json(kind: str) -> str:
    schema = workflow_json_schema() if kind == "workflow" else trace_json_schema()
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"
