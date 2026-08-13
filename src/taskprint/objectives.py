from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    ConstraintOperator,
    ConstraintPhase,
    ObjectiveDirection,
    ObjectiveMetric,
    OutcomeConstraint,
    OutcomeContract,
    Trace,
)

_MISSING = object()


class MetricAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    source: str
    direction: ObjectiveDirection
    observed: float | None = None
    target: float
    unacceptable: float
    weight: float
    score: float = Field(ge=0, le=1)
    samples: int = Field(ge=0)
    missing: int = Field(ge=0)


class ConstraintAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    passed: bool
    enforcement: str
    phase: str
    action: str | None = None
    source: str
    observed: Any = None
    expected: Any = None
    message: str
    observation_index: int | None = None


class OutcomeAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0, le=1)
    feasible: bool
    observations: int = Field(ge=0)
    metrics: list[MetricAssessment]
    constraint_checks: list[ConstraintAssessment]
    blocking_violations: int = Field(ge=0)
    review_violations: int = Field(ge=0)
    warnings: int = Field(ge=0)


class CandidateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    observations: list[dict[str, Any]] = Field(min_length=1)


class RankedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    name: str
    assessment: OutcomeAssessment


def resolve_source(context: Mapping[str, Any], source: str) -> Any:
    """Resolve a dotted path without executing user-controlled expressions."""

    current: Any = context
    for segment in source.split("."):
        if isinstance(current, Mapping) and segment in current:
            current = current[segment]
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return _MISSING
        else:
            return _MISSING
    return current


def source_exists(context: Mapping[str, Any], source: str) -> bool:
    return resolve_source(context, source) is not _MISSING


def numeric_source_exists(context: Mapping[str, Any], source: str) -> bool:
    value = resolve_source(context, source)
    return value is not _MISSING and isinstance(value, (int, float))


def _metric_score(metric: ObjectiveMetric, observed: float) -> float:
    span = abs(metric.target - metric.unacceptable)
    if metric.direction == ObjectiveDirection.MAXIMIZE:
        return min(1.0, max(0.0, (observed - metric.unacceptable) / span))
    return min(1.0, max(0.0, (metric.unacceptable - observed) / span))


def _compare(operator: ConstraintOperator, observed: Any, expected: Any) -> bool:
    if operator == ConstraintOperator.EXISTS:
        return observed is not _MISSING
    if observed is _MISSING:
        return False
    if operator == ConstraintOperator.EQ:
        return bool(observed == expected)
    if operator == ConstraintOperator.NE:
        return bool(observed != expected)
    if operator == ConstraintOperator.GT:
        return bool(observed > expected)
    if operator == ConstraintOperator.GTE:
        return bool(observed >= expected)
    if operator == ConstraintOperator.LT:
        return bool(observed < expected)
    if operator == ConstraintOperator.LTE:
        return bool(observed <= expected)
    if operator == ConstraintOperator.IN:
        return bool(observed in expected)
    if operator == ConstraintOperator.NOT_IN:
        return bool(observed not in expected)
    return False


def check_constraint(
    constraint: OutcomeConstraint,
    context: Mapping[str, Any],
    *,
    observation_index: int | None = None,
) -> ConstraintAssessment:
    observed = resolve_source(context, constraint.source)
    if observed is _MISSING:
        passed = constraint.missing_passes
    else:
        try:
            passed = _compare(constraint.operator, observed, constraint.expected)
        except (TypeError, ValueError):
            passed = False
    display_observed = None if observed is _MISSING else observed
    message = (
        f"constraint '{constraint.id}' passed"
        if passed
        else f"constraint '{constraint.id}' failed: {constraint.source} "
        f"{constraint.operator.value} {constraint.expected!r} (observed {display_observed!r})"
    )
    return ConstraintAssessment(
        id=constraint.id,
        passed=passed,
        enforcement=constraint.enforcement.value,
        phase=constraint.phase.value,
        action=constraint.action,
        source=constraint.source,
        observed=display_observed,
        expected=constraint.expected,
        message=message,
        observation_index=observation_index,
    )


def assess_outcomes(
    contract: OutcomeContract,
    observations: Sequence[Mapping[str, Any]],
) -> OutcomeAssessment:
    """Score historical or simulated observations against an Outcome Contract."""

    metrics: list[MetricAssessment] = []
    weighted_score = 0.0
    available_weight = 0.0
    for metric in contract.objectives:
        values: list[float] = []
        missing = 0
        for observation in observations:
            value = resolve_source(observation, metric.source)
            if value is _MISSING or not isinstance(value, (int, float)):
                missing += 1
            else:
                values.append(float(value))
        observed = sum(values) / len(values) if values else None
        score = _metric_score(metric, observed) if observed is not None else 0.0
        metrics.append(
            MetricAssessment(
                name=metric.name,
                source=metric.source,
                direction=metric.direction,
                observed=observed,
                target=metric.target,
                unacceptable=metric.unacceptable,
                weight=metric.weight,
                score=score,
                samples=len(values),
                missing=missing,
            )
        )
        weighted_score += score * metric.weight
        available_weight += metric.weight

    checks = [
        check_constraint(constraint, observation, observation_index=index)
        for index, observation in enumerate(observations)
        for constraint in contract.constraints
        if constraint.phase == ConstraintPhase.OUTCOME
    ]
    failed = [check for check in checks if not check.passed]
    blocking = sum(check.enforcement == "block" for check in failed)
    reviews = sum(check.enforcement == "review" for check in failed)
    warnings = sum(check.enforcement == "warn" for check in failed)
    return OutcomeAssessment(
        score=weighted_score / available_weight if available_weight else 0,
        feasible=blocking == 0,
        observations=len(observations),
        metrics=metrics,
        constraint_checks=checks,
        blocking_violations=blocking,
        review_violations=reviews,
        warnings=warnings,
    )


def trace_observation(trace: Trace) -> dict[str, Any]:
    duration_ms: float | None = None
    if trace.started_at and trace.ended_at:
        duration_ms = (trace.ended_at - trace.started_at).total_seconds() * 1_000
    return {
        "trace": {"id": trace.id, "success": trace.success, "duration_ms": duration_ms},
        "run": {"success": trace.success, "duration_ms": duration_ms},
        "outcome": trace.outcome,
        "labels": trace.labels,
    }


def assess_traces(contract: OutcomeContract, traces: Sequence[Trace]) -> OutcomeAssessment:
    return assess_outcomes(contract, [trace_observation(trace) for trace in traces])


def rank_candidates(
    contract: OutcomeContract,
    candidates: Sequence[CandidateEvidence],
) -> list[RankedCandidate]:
    """Rank feasible candidates first, followed by objective score and evidence volume."""

    assessed = [
        (candidate, assess_outcomes(contract, candidate.observations)) for candidate in candidates
    ]
    assessed.sort(
        key=lambda item: (
            item[1].feasible,
            -item[1].review_violations,
            item[1].score,
            item[1].observations,
            item[0].name,
        ),
        reverse=True,
    )
    return [
        RankedCandidate(rank=index, name=candidate.name, assessment=assessment)
        for index, (candidate, assessment) in enumerate(assessed, 1)
    ]
