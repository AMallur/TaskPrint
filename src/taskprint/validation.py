from __future__ import annotations

from pydantic import BaseModel, Field

from .models import ConstraintPhase, Workflow


class ValidationIssue(BaseModel):
    level: str
    code: str
    message: str
    node_id: str | None = None


class ValidationReport(BaseModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


def validate_workflow(workflow: Workflow) -> ValidationReport:
    issues: list[ValidationIssue] = []
    reachable: set[str] = set()
    stack = [workflow.start]
    while stack:
        current = stack.pop()
        if current in reachable:
            continue
        reachable.add(current)
        stack.extend(edge.target for edge in workflow.outgoing(current))
    for node in workflow.nodes:
        if node.id not in reachable:
            issues.append(
                ValidationIssue(
                    level="error",
                    code="unreachable_node",
                    message="node is unreachable",
                    node_id=node.id,
                )
            )
        outgoing = workflow.outgoing(node.id)
        probability = sum(edge.probability for edge in outgoing)
        if outgoing and abs(probability - 1.0) > 1e-6:
            issues.append(
                ValidationIssue(
                    level="error",
                    code="probability_sum",
                    message=f"outgoing probability sums to {probability:.6f}",
                    node_id=node.id,
                )
            )
        if node.id in workflow.terminals and outgoing:
            issues.append(
                ValidationIssue(
                    level="warning",
                    code="terminal_has_edges",
                    message="terminal node also has outgoing edges",
                    node_id=node.id,
                )
            )
    for terminal in workflow.terminals:
        if terminal not in reachable:
            issues.append(
                ValidationIssue(
                    level="error",
                    code="unreachable_terminal",
                    message="terminal is unreachable",
                    node_id=terminal,
                )
            )
    if workflow.outcome_contract:
        actions = {node.action for node in workflow.nodes}
        for constraint in workflow.outcome_contract.constraints:
            if constraint.action and constraint.action not in actions:
                issues.append(
                    ValidationIssue(
                        level="error",
                        code="unknown_constraint_action",
                        message=(
                            f"constraint '{constraint.id}' targets unknown action "
                            f"'{constraint.action}'"
                        ),
                    )
                )
            if (
                constraint.phase in {ConstraintPhase.BEFORE_ACTION, ConstraintPhase.AFTER_ACTION}
                and constraint.action is None
            ):
                issues.append(
                    ValidationIssue(
                        level="warning",
                        code="global_action_constraint",
                        message=(f"constraint '{constraint.id}' applies to every workflow action"),
                    )
                )
    return ValidationReport(
        valid=not any(issue.level == "error" for issue in issues), issues=issues
    )
