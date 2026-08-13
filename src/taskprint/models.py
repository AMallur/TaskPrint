from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from itertools import pairwise
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class EventKind(str, Enum):
    OBSERVE = "observe"
    INPUT = "input"
    ACTION = "action"
    DECISION = "decision"
    OUTPUT = "output"
    HUMAN = "human"


class ObjectiveDirection(str, Enum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


class ConstraintOperator(str, Enum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    EXISTS = "exists"


class ConstraintPhase(str, Enum):
    BEFORE_ACTION = "before_action"
    AFTER_ACTION = "after_action"
    OUTCOME = "outcome"


class ConstraintEnforcement(str, Enum):
    BLOCK = "block"
    REVIEW = "review"
    WARN = "warn"


class ObjectiveMetric(StrictModel):
    """A measurable definition of a good workflow outcome.

    ``target`` is the desired value and ``unacceptable`` is the zero-score
    boundary. Values between them receive a linear desirability score.
    """

    name: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=500)
    direction: ObjectiveDirection
    weight: float = Field(default=1, gt=0, le=1_000_000, allow_inf_nan=False)
    target: float = Field(allow_inf_nan=False)
    unacceptable: float = Field(allow_inf_nan=False)
    unit: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2_000)

    @model_validator(mode="after")
    def validate_bounds(self) -> ObjectiveMetric:
        if self.direction == ObjectiveDirection.MAXIMIZE and self.unacceptable >= self.target:
            raise ValueError("maximize metric requires unacceptable < target")
        if self.direction == ObjectiveDirection.MINIMIZE and self.target >= self.unacceptable:
            raise ValueError("minimize metric requires target < unacceptable")
        return self


class OutcomeConstraint(StrictModel):
    """A non-negotiable rule evaluated against execution or outcome context."""

    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    description: str = Field(min_length=1, max_length=2_000)
    source: str = Field(min_length=1, max_length=500)
    operator: ConstraintOperator
    expected: Any = None
    phase: ConstraintPhase = ConstraintPhase.OUTCOME
    enforcement: ConstraintEnforcement = ConstraintEnforcement.BLOCK
    action: str | None = Field(default=None, min_length=1, max_length=200)
    missing_passes: bool = False

    @model_validator(mode="after")
    def validate_expected(self) -> OutcomeConstraint:
        if self.operator != ConstraintOperator.EXISTS and self.expected is None:
            raise ValueError("expected is required unless operator is 'exists'")
        if self.phase == ConstraintPhase.OUTCOME and self.action is not None:
            raise ValueError("outcome constraints cannot target a workflow action")
        return self


class OutcomeContract(StrictModel):
    """The objective function and hard boundaries for a learned workflow."""

    objectives: list[ObjectiveMetric] = Field(min_length=1)
    constraints: list[OutcomeConstraint] = Field(default_factory=list)
    description: str | None = Field(default=None, max_length=5_000)

    @model_validator(mode="after")
    def validate_unique_names(self) -> OutcomeContract:
        names = [metric.name for metric in self.objectives]
        if len(names) != len(set(names)):
            raise ValueError("objective metric names must be unique")
        constraint_ids = [constraint.id for constraint in self.constraints]
        if len(constraint_ids) != len(set(constraint_ids)):
            raise ValueError("constraint ids must be unique")
        return self


class Event(StrictModel):
    """One meaningful action or observation in a completed task."""

    type: str = Field(min_length=1, max_length=200, description="Stable semantic action name")
    kind: EventKind = EventKind.ACTION
    actor: str = Field(default="human", min_length=1, max_length=200)
    target: str | None = Field(default=None, max_length=500)
    value: Any = None
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | None = None
    duration_ms: float | None = Field(default=None, ge=0)

    @field_validator("type", "actor")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @property
    def signature(self) -> str:
        return f"{self.kind.value}:{self.type}:{self.target or ''}"


class Trace(StrictModel):
    """A successful or failed example of a task being performed."""

    schema_version: Literal["taskprint-trace/1.0"] = "taskprint-trace/1.0"
    id: str = Field(min_length=1, max_length=300)
    task: str = Field(min_length=1, max_length=500)
    events: list[Event] = Field(min_length=1, max_length=100_000)
    success: bool = True
    outcome: dict[str, Any] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    source: str | None = Field(default=None, max_length=500)
    started_at: datetime | None = None
    ended_at: datetime | None = None

    @field_validator("id", "task")
    @classmethod
    def strip_trace_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def validate_times(self) -> Trace:
        if self.started_at and self.ended_at and self.ended_at < self.started_at:
            raise ValueError("ended_at must not precede started_at")
        timestamps = [event.timestamp for event in self.events if event.timestamp]
        if any(later < earlier for earlier, later in pairwise(timestamps)):
            raise ValueError("event timestamps must be monotonic")
        return self


class WorkflowNode(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")
    action: str = Field(min_length=1, max_length=200)
    kind: EventKind
    target: str | None = None
    required: bool = True
    observed_count: int = Field(default=0, ge=0)
    success_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    support: float = Field(default=0, ge=0, le=1)
    confidence: float = Field(default=0, ge=0, le=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    variants: dict[str, list[Any]] = Field(default_factory=dict)

    @field_validator("action")
    @classmethod
    def strip_action(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def validate_counts(self) -> WorkflowNode:
        if self.success_count + self.failure_count > self.observed_count:
            raise ValueError("node outcome counts cannot exceed observed_count")
        return self


class WorkflowEdge(StrictModel):
    source: str
    target: str
    observed_count: int = Field(default=0, ge=0)
    success_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    probability: float = Field(ge=0, le=1)
    confidence: float = Field(default=0, ge=0, le=1)
    is_cycle: bool = False
    condition: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> WorkflowEdge:
        if self.success_count + self.failure_count > self.observed_count:
            raise ValueError("edge outcome counts cannot exceed observed_count")
        return self


class Workflow(StrictModel):
    """An editable workflow induced from demonstrations."""

    schema_version: Literal["taskprint/1.0"] = "taskprint/1.0"
    name: str = Field(min_length=1, max_length=200)
    task: str = Field(min_length=1, max_length=500)
    nodes: list[WorkflowNode] = Field(min_length=1)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    start: str
    terminals: list[str] = Field(min_length=1)
    trace_count: int = Field(ge=1)
    successful_trace_count: int = Field(default=0, ge=0)
    failed_trace_count: int = Field(default=0, ge=0)
    outcome_contract: OutcomeContract | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "task")
    @classmethod
    def strip_workflow_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @model_validator(mode="after")
    def validate_graph(self) -> Workflow:
        ids = {node.id for node in self.nodes}
        if len(ids) != len(self.nodes):
            raise ValueError("workflow node ids must be unique")
        if self.start not in ids:
            raise ValueError("start node does not exist")
        if len(set(self.terminals)) != len(self.terminals):
            raise ValueError("terminal node ids must be unique")
        if not set(self.terminals).issubset(ids):
            raise ValueError("terminal node does not exist")
        edge_pairs: set[tuple[str, str]] = set()
        for edge in self.edges:
            if edge.source not in ids or edge.target not in ids:
                raise ValueError(f"edge references unknown node: {edge.source}->{edge.target}")
            pair = (edge.source, edge.target)
            if pair in edge_pairs:
                raise ValueError(f"duplicate edge: {edge.source}->{edge.target}")
            edge_pairs.add(pair)
        if self.successful_trace_count + self.failed_trace_count > self.trace_count:
            raise ValueError("trace outcome counts cannot exceed trace_count")
        return self

    @property
    def fingerprint(self) -> str:
        payload = self.model_dump(
            mode="json", exclude={"created_at", "metadata"}, exclude_none=True
        )
        canonical = __import__("json").dumps(payload, sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode()).hexdigest()[:16]

    def node(self, node_id: str) -> WorkflowNode:
        for node in self.nodes:
            if node.id == node_id:
                return node
        raise KeyError(node_id)

    def outgoing(self, node_id: str) -> list[WorkflowEdge]:
        return sorted(
            (edge for edge in self.edges if edge.source == node_id),
            key=lambda edge: (-edge.probability, edge.target),
        )

    def incoming(self, node_id: str) -> list[WorkflowEdge]:
        return sorted(
            (edge for edge in self.edges if edge.target == node_id),
            key=lambda edge: (-edge.probability, edge.source),
        )
