from __future__ import annotations

from itertools import pairwise

from pydantic import BaseModel, Field

from .models import Trace, Workflow
from .objectives import OutcomeAssessment, assess_traces


class Evaluation(BaseModel):
    traces: int
    exact_path_rate: float = Field(ge=0, le=1)
    event_coverage: float = Field(ge=0, le=1)
    transition_coverage: float = Field(ge=0, le=1)
    mean_path_similarity: float = Field(ge=0, le=1)
    successful_exact_path_rate: float = Field(ge=0, le=1)
    failed_exact_path_rate: float = Field(ge=0, le=1)
    unseen_events: dict[str, int]
    unseen_transitions: dict[str, int]
    outcomes: OutcomeAssessment | None = None


def _edit_similarity(actual: list[str], candidates: list[list[str]]) -> float:
    if not actual:
        return 1.0

    def distance(left: list[str], right: list[str]) -> int:
        previous = list(range(len(right) + 1))
        for i, left_value in enumerate(left, 1):
            current = [i]
            for j, right_value in enumerate(right, 1):
                current.append(
                    min(
                        current[-1] + 1,
                        previous[j] + 1,
                        previous[j - 1] + (left_value != right_value),
                    )
                )
            previous = current
        return previous[-1]

    if not candidates:
        return 0.0
    best = min(distance(actual, candidate) for candidate in candidates)
    scale = max(len(actual), min((len(candidate) for candidate in candidates), default=0), 1)
    return max(0.0, 1 - best / scale)


def _enumerate_paths(workflow: Workflow, limit: int = 1_000) -> list[list[str]]:
    node_signature = {
        node.id: f"{node.kind.value}:{node.action}:{node.target or ''}" for node in workflow.nodes
    }
    paths: list[list[str]] = []
    stack: list[tuple[str, list[str], dict[str, int]]] = [(workflow.start, [], {})]
    while stack and len(paths) < limit:
        node_id, path, visits = stack.pop()
        updated_visits = dict(visits)
        updated_visits[node_id] = updated_visits.get(node_id, 0) + 1
        updated_path = [*path, node_signature[node_id]]
        outgoing = workflow.outgoing(node_id)
        if not outgoing or node_id in workflow.terminals:
            paths.append(updated_path)
            continue
        for edge in reversed(outgoing):
            if updated_visits.get(edge.target, 0) < 2:
                stack.append((edge.target, updated_path, updated_visits))
    return paths


def evaluate(workflow: Workflow, traces: list[Trace]) -> Evaluation:
    signatures = {f"{node.kind.value}:{node.action}:{node.target or ''}" for node in workflow.nodes}
    id_to_signature = {
        node.id: f"{node.kind.value}:{node.action}:{node.target or ''}" for node in workflow.nodes
    }
    transitions = {
        (id_to_signature[edge.source], id_to_signature[edge.target]) for edge in workflow.edges
    }
    total_events = covered_events = total_transitions = covered_transitions = exact = 0
    success_total = success_exact = failure_total = failure_exact = 0
    similarities: list[float] = []
    candidate_paths = _enumerate_paths(workflow)
    unseen_events: dict[str, int] = {}
    unseen_transitions: dict[str, int] = {}
    for trace in traces:
        path = [event.signature for event in trace.events]
        path_ok = True
        for signature in path:
            total_events += 1
            if signature in signatures:
                covered_events += 1
            else:
                path_ok = False
                unseen_events[signature] = unseen_events.get(signature, 0) + 1
        for pair in pairwise(path):
            total_transitions += 1
            if pair in transitions:
                covered_transitions += 1
            else:
                path_ok = False
                key = " -> ".join(pair)
                unseen_transitions[key] = unseen_transitions.get(key, 0) + 1
        exact += int(path_ok)
        similarities.append(_edit_similarity(path, candidate_paths))
        if trace.success:
            success_total += 1
            success_exact += int(path_ok)
        else:
            failure_total += 1
            failure_exact += int(path_ok)
    count = len(traces)
    return Evaluation(
        traces=count,
        exact_path_rate=exact / count if count else 0,
        event_coverage=covered_events / total_events if total_events else 0,
        transition_coverage=covered_transitions / total_transitions if total_transitions else 1,
        mean_path_similarity=sum(similarities) / count if count else 0,
        successful_exact_path_rate=success_exact / success_total if success_total else 0,
        failed_exact_path_rate=failure_exact / failure_total if failure_total else 0,
        unseen_events=unseen_events,
        unseen_transitions=unseen_transitions,
        outcomes=(
            assess_traces(workflow.outcome_contract, traces) if workflow.outcome_contract else None
        ),
    )
