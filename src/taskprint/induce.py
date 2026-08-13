from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from .errors import TraceValidationError
from .models import Event, OutcomeContract, Trace, Workflow, WorkflowEdge, WorkflowNode


@dataclass(frozen=True)
class InductionConfig:
    """Controls the transparent directly-follows induction algorithm."""

    minimum_support: float = 0.5
    include_failure_paths: bool = True
    merge_consecutive_repeats: bool = False
    strict_task_name: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.minimum_support <= 1:
            raise ValueError("minimum_support must be between 0 and 1")


_MISSING = object()


def _stable_value(values: list[Any]) -> tuple[Any, list[Any]]:
    encoded = [repr(value) for value in values]
    if len(set(encoded)) == 1:
        return values[0], []
    unique: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = repr(value)
        if key not in seen:
            seen.add(key)
            unique.append(value)
    return _MISSING, unique


def _wilson_lower(successes: int, total: int, z: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    p = successes / total
    denominator = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return max(0.0, (centre - margin) / denominator)


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return result or "workflow"


def _has_path(adjacency: dict[str, set[str]], start: str, target: str) -> bool:
    stack = [start]
    visited: set[str] = set()
    while stack:
        current = stack.pop()
        if current == target:
            return True
        if current in visited:
            continue
        visited.add(current)
        stack.extend(adjacency.get(current, ()))
    return False


def induce(
    traces: list[Trace],
    *,
    name: str | None = None,
    config: InductionConfig | None = None,
    outcome_contract: OutcomeContract | None = None,
) -> Workflow:
    """Induce an inspectable probabilistic workflow from task demonstrations."""

    config = config or InductionConfig()
    if not traces:
        raise TraceValidationError("at least one trace is required")
    ids = [trace.id for trace in traces]
    if len(ids) != len(set(ids)):
        raise TraceValidationError("trace ids must be unique")
    tasks = Counter(trace.task for trace in traces)
    if config.strict_task_name and len(tasks) != 1:
        raise TraceValidationError(f"traces contain multiple task names: {sorted(tasks)}")
    task = tasks.most_common(1)[0][0]
    selected = [trace for trace in traces if trace.success or config.include_failure_paths]
    if not selected:
        raise TraceValidationError("no eligible traces remain after applying induction policy")

    signature_events: dict[str, list[Event]] = defaultdict(list)
    signature_traces: dict[str, set[str]] = defaultdict(set)
    signature_successes: dict[str, set[str]] = defaultdict(set)
    signature_failures: dict[str, set[str]] = defaultdict(set)
    transition_counts: Counter[tuple[str, str]] = Counter()
    transition_successes: Counter[tuple[str, str]] = Counter()
    transition_failures: Counter[tuple[str, str]] = Counter()
    outgoing_counts: Counter[str] = Counter()
    terminal_counts: Counter[str] = Counter()
    ordered_signatures: list[str] = []
    paths: list[tuple[Trace, list[str]]] = []

    for trace in selected:
        path: list[str] = []
        for event in trace.events:
            signature = event.signature
            signature_events[signature].append(event)
            signature_traces[signature].add(trace.id)
            (signature_successes if trace.success else signature_failures)[signature].add(trace.id)
            if signature not in ordered_signatures:
                ordered_signatures.append(signature)
            if config.merge_consecutive_repeats and path and path[-1] == signature:
                continue
            path.append(signature)
        paths.append((trace, path))
        for transition in pairwise(path):
            transition_counts[transition] += 1
            outgoing_counts[transition[0]] += 1
            (transition_successes if trace.success else transition_failures)[transition] += 1
        terminal_counts[path[-1]] += 1

    node_ids = {signature: f"n{index + 1}" for index, signature in enumerate(ordered_signatures)}
    nodes: list[WorkflowNode] = []
    for signature in ordered_signatures:
        events = signature_events[signature]
        first = events[0]
        parameters: dict[str, Any] = {}
        variants: dict[str, list[Any]] = {}
        stable, variable = _stable_value([event.value for event in events])
        if stable is not _MISSING:
            parameters["value"] = stable
        elif variable:
            variants["value"] = variable
        for key in sorted({key for event in events for key in event.data}):
            stable, variable = _stable_value([event.data.get(key) for event in events])
            if stable is not _MISSING:
                parameters[key] = stable
            elif variable:
                variants[key] = variable
        observed = len(signature_traces[signature])
        successes = len(signature_successes[signature])
        failures = len(signature_failures[signature])
        support = observed / len(selected)
        nodes.append(
            WorkflowNode(
                id=node_ids[signature],
                action=first.type,
                kind=first.kind,
                target=first.target,
                required=support >= config.minimum_support,
                observed_count=observed,
                success_count=successes,
                failure_count=failures,
                support=support,
                confidence=_wilson_lower(observed, len(selected)),
                parameters=parameters,
                variants=variants,
            )
        )

    adjacency: dict[str, set[str]] = defaultdict(set)
    for source, target in transition_counts:
        adjacency[source].add(target)
    edges: list[WorkflowEdge] = []
    for (source, target), count in sorted(transition_counts.items()):
        is_cycle = source == target or _has_path(adjacency, target, source)
        edges.append(
            WorkflowEdge(
                source=node_ids[source],
                target=node_ids[target],
                observed_count=count,
                success_count=transition_successes[(source, target)],
                failure_count=transition_failures[(source, target)],
                probability=count / outgoing_counts[source],
                confidence=_wilson_lower(count, outgoing_counts[source]),
                is_cycle=is_cycle,
            )
        )

    start_signature = Counter(path[0] for _, path in paths).most_common(1)[0][0]
    terminals = [node_ids[signature] for signature, _ in terminal_counts.most_common()]
    successful = sum(trace.success for trace in selected)
    failed = len(selected) - successful
    return Workflow(
        name=name or _slug(task),
        task=task,
        nodes=nodes,
        edges=edges,
        start=node_ids[start_signature],
        terminals=terminals,
        trace_count=len(selected),
        successful_trace_count=successful,
        failed_trace_count=failed,
        outcome_contract=outcome_contract,
        metadata={
            "inducer": "directly-follows-v2",
            "minimum_support": config.minimum_support,
            "includes_failure_paths": config.include_failure_paths,
        },
    )
