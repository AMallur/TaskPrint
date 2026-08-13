from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from .models import Trace, Workflow
from .objectives import numeric_source_exists, trace_observation


class LearningNeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    priority: int = Field(ge=1, le=3)
    code: str
    message: str
    node_id: str | None = None
    edge: str | None = None
    requested_demonstration: str


class LearningReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ready_for_optimization: bool
    needs: list[LearningNeed]


def analyze_learning_needs(
    workflow: Workflow,
    traces: Sequence[Trace] = (),
    *,
    confidence_threshold: float = 0.35,
    branch_observation_minimum: int = 3,
) -> LearningReport:
    """Request demonstrations that reduce consequential uncertainty first."""

    needs: list[LearningNeed] = []
    for node in workflow.nodes:
        if node.confidence < confidence_threshold:
            needs.append(
                LearningNeed(
                    priority=2,
                    code="low_node_confidence",
                    node_id=node.id,
                    message=f"'{node.action}' has only {node.observed_count} supporting traces",
                    requested_demonstration=(
                        "Record another successful case that reaches "
                        f"'{node.action}', plus one case where that action should be "
                        "skipped if such a case exists."
                    ),
                )
            )
        outgoing = workflow.outgoing(node.id)
        for edge in outgoing:
            target = workflow.node(edge.target)
            if len(outgoing) > 1 and edge.observed_count < branch_observation_minimum:
                needs.append(
                    LearningNeed(
                        priority=1,
                        code="underobserved_branch",
                        node_id=node.id,
                        edge=f"{edge.source}->{edge.target}",
                        message=(
                            f"branch '{node.action}' -> '{target.action}' has only "
                            f"{edge.observed_count} observations"
                        ),
                        requested_demonstration=(
                            f"Record {branch_observation_minimum - edge.observed_count} more "
                            f"case(s) where '{node.action}' should route to "
                            f"'{target.action}', including the business reason for that decision."
                        ),
                    )
                )

    if workflow.outcome_contract:
        observations = [trace_observation(trace) for trace in traces]
        for metric in workflow.outcome_contract.objectives:
            present = sum(
                numeric_source_exists(observation, metric.source) for observation in observations
            )
            if present < len(observations) or not observations:
                missing = len(observations) - present
                needs.append(
                    LearningNeed(
                        priority=1,
                        code="missing_objective_evidence",
                        message=(
                            f"objective '{metric.name}' is missing from {missing} of "
                            f"{len(observations)} held-out observations"
                            if observations
                            else f"objective '{metric.name}' has no held-out evidence"
                        ),
                        requested_demonstration=(
                            f"Run held-out cases and record numeric '{metric.source}' values so "
                            f"Taskprint can optimize '{metric.name}'."
                        ),
                    )
                )

    needs.sort(key=lambda need: (need.priority, need.code, need.node_id or ""))
    return LearningReport(
        ready_for_optimization=not any(need.priority == 1 for need in needs),
        needs=needs,
    )
