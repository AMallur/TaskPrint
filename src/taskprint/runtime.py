from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .errors import ExecutionError, HandlerNotFoundError, RoutingError
from .models import ConstraintPhase, Workflow, WorkflowEdge, WorkflowNode
from .objectives import (
    ConstraintAssessment,
    OutcomeAssessment,
    assess_outcomes,
    check_constraint,
)

HandlerResult = Any | Awaitable[Any]
Handler = Callable[[WorkflowNode, dict[str, Any]], HandlerResult]
Router = Callable[[WorkflowNode, list[WorkflowEdge], dict[str, Any]], str]
AsyncRouter = Callable[[WorkflowNode, list[WorkflowEdge], dict[str, Any]], str | Awaitable[str]]
StepCallback = Callable[["ExecutionStep"], None]


async def _await_result(value: Awaitable[Any]) -> Any:
    return await value


class ExecutionStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STEP_LIMIT = "step_limit"
    VISIT_LIMIT = "visit_limit"
    NEEDS_REVIEW = "needs_review"
    CONSTRAINT_VIOLATION = "constraint_violation"


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_steps: int = Field(default=100, ge=1, le=1_000_000)
    max_visits_per_node: int = Field(default=10, ge=1, le=100_000)
    retries: int = Field(default=0, ge=0, le=100)
    retry_delay_seconds: float = Field(default=0, ge=0, le=3_600)
    timeout_seconds: float | None = Field(default=None, gt=0, le=86_400)
    fail_fast: bool = True
    enforce_constraints: bool = True


class ExecutionStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    action: str
    status: str
    attempts: int = Field(ge=1)
    started_at: datetime
    ended_at: datetime
    duration_ms: float = Field(ge=0)
    output: Any = None
    error: str | None = None


class ExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    workflow: str
    fingerprint: str
    status: ExecutionStatus
    current_node: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    steps: list[ExecutionStep] = Field(default_factory=list)
    state: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    constraint_checks: list[ConstraintAssessment] = Field(default_factory=list)
    outcome_assessment: OutcomeAssessment | None = None


class RunStore(Protocol):
    def save(self, result: ExecutionResult) -> None: ...


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, action: str, handler: Handler, *, replace: bool = False) -> None:
        if action in self._handlers and not replace:
            raise ValueError(f"handler already registered for action '{action}'")
        self._handlers[action] = handler

    def handler(self, action: str) -> Handler:
        try:
            return self._handlers[action]
        except KeyError as exc:
            raise HandlerNotFoundError(f"no handler registered for action '{action}'") from exc

    def missing(self, workflow: Workflow) -> list[str]:
        return sorted({node.action for node in workflow.nodes} - self._handlers.keys())


class WorkflowRunner:
    """Execute induced workflows with retries, limits, callbacks, and checkpoints."""

    def __init__(
        self,
        workflow: Workflow,
        registry: HandlerRegistry,
        *,
        config: RuntimeConfig | None = None,
        store: RunStore | None = None,
        on_step: StepCallback | None = None,
    ) -> None:
        self.workflow = workflow
        self.registry = registry
        self.config = config or RuntimeConfig()
        self.store = store
        self.on_step = on_step
        self.nodes = {node.id: node for node in workflow.nodes}

    def _action_constraints(
        self,
        node: WorkflowNode,
        phase: ConstraintPhase,
        state: dict[str, Any],
        *,
        output: Any = None,
    ) -> list[ConstraintAssessment]:
        if not self.config.enforce_constraints or not self.workflow.outcome_contract:
            return []
        context = {
            "state": state,
            "node": {"id": node.id, "action": node.action},
            "output": output,
        }
        return [
            check_constraint(constraint, context)
            for constraint in self.workflow.outcome_contract.constraints
            if constraint.phase == phase
            and (constraint.action is None or constraint.action == node.action)
        ]

    def _constraint_stop(self, result: ExecutionResult, checks: list[ConstraintAssessment]) -> bool:
        result.constraint_checks.extend(checks)
        failed = [check for check in checks if not check.passed]
        blocking = next((check for check in failed if check.enforcement == "block"), None)
        review = next((check for check in failed if check.enforcement == "review"), None)
        if blocking:
            result.status = ExecutionStatus.CONSTRAINT_VIOLATION
            result.error = blocking.message
        elif review:
            result.status = ExecutionStatus.NEEDS_REVIEW
            result.error = review.message
        else:
            return False
        result.ended_at = datetime.now(timezone.utc)
        self._checkpoint(result)
        return True

    def _complete(self, result: ExecutionResult) -> ExecutionResult:
        result.status = ExecutionStatus.COMPLETED
        result.current_node = None
        result.ended_at = datetime.now(timezone.utc)
        if self.workflow.outcome_contract:
            duration_ms = (result.ended_at - result.started_at).total_seconds() * 1_000
            result.outcome_assessment = assess_outcomes(
                self.workflow.outcome_contract,
                [
                    {
                        "state": result.state,
                        "trace": {"success": True, "duration_ms": duration_ms},
                        "run": {"success": True, "duration_ms": duration_ms},
                        "outcome": result.state.get("outcome", {}),
                    }
                ],
            )
            outcome_failed = [
                check for check in result.outcome_assessment.constraint_checks if not check.passed
            ]
            result.constraint_checks.extend(result.outcome_assessment.constraint_checks)
            blocking = next(
                (check for check in outcome_failed if check.enforcement == "block"), None
            )
            review = next(
                (check for check in outcome_failed if check.enforcement == "review"), None
            )
            if blocking:
                result.status = ExecutionStatus.CONSTRAINT_VIOLATION
                result.error = blocking.message
            elif review:
                result.status = ExecutionStatus.NEEDS_REVIEW
                result.error = review.message
        self._checkpoint(result)
        return result

    def _checkpoint(self, result: ExecutionResult) -> None:
        if self.store:
            self.store.save(result)

    def _choose(
        self,
        node: WorkflowNode,
        outgoing: list[WorkflowEdge],
        state: dict[str, Any],
        visits: dict[str, int],
        router: Router | None,
    ) -> str | None:
        eligible = [
            edge
            for edge in outgoing
            if visits.get(edge.target, 0) < self.config.max_visits_per_node
        ]
        if not eligible:
            return None
        target = router(node, eligible, state) if router else eligible[0].target
        if target not in {edge.target for edge in eligible}:
            raise RoutingError(
                f"router selected '{target}', which is not an eligible edge from '{node.id}'"
            )
        return target

    def _call_sync(self, handler: Handler, node: WorkflowNode, state: dict[str, Any]) -> Any:
        def invoke() -> Any:
            value = handler(node, state)
            if inspect.isawaitable(value):
                return asyncio.run(_await_result(value))
            return value

        if self.config.timeout_seconds is None:
            return invoke()
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="taskprint")
        future = executor.submit(invoke)
        try:
            return future.result(timeout=self.config.timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise TimeoutError(
                f"action '{node.action}' exceeded {self.config.timeout_seconds}s"
            ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _execute_sync(self, node: WorkflowNode, state: dict[str, Any]) -> tuple[ExecutionStep, Any]:
        started = datetime.now(timezone.utc)
        start_clock = time.perf_counter()
        error: Exception | None = None
        attempts = 0
        output: Any = None
        for attempt in range(self.config.retries + 1):
            attempts = attempt + 1
            try:
                output = self._call_sync(self.registry.handler(node.action), node, state)
                error = None
                break
            except Exception as exc:  # handler boundary intentionally catches application errors
                error = exc
                if attempt < self.config.retries and self.config.retry_delay_seconds:
                    time.sleep(self.config.retry_delay_seconds)
        ended = datetime.now(timezone.utc)
        step = ExecutionStep(
            node_id=node.id,
            action=node.action,
            status="failed" if error else "completed",
            attempts=attempts,
            started_at=started,
            ended_at=ended,
            duration_ms=(time.perf_counter() - start_clock) * 1_000,
            output=output,
            error=f"{type(error).__name__}: {error}" if error else None,
        )
        return step, error

    def run(
        self,
        state: dict[str, Any] | None = None,
        *,
        router: Router | None = None,
        run_id: str | None = None,
    ) -> ExecutionResult:
        current = self.workflow.start
        result = ExecutionResult(
            run_id=run_id or str(uuid4()),
            workflow=self.workflow.name,
            fingerprint=self.workflow.fingerprint,
            status=ExecutionStatus.RUNNING,
            current_node=current,
            started_at=datetime.now(timezone.utc),
            state=dict(state or {}),
        )
        visits: dict[str, int] = {}
        self._checkpoint(result)
        for _ in range(self.config.max_steps):
            node = self.nodes[current]
            visits[current] = visits.get(current, 0) + 1
            before = self._action_constraints(node, ConstraintPhase.BEFORE_ACTION, result.state)
            if self._constraint_stop(result, before):
                return result
            step, error = self._execute_sync(node, result.state)
            result.steps.append(step)
            if self.on_step:
                self.on_step(step)
            if error:
                result.status = ExecutionStatus.FAILED
                result.error = step.error
                result.ended_at = datetime.now(timezone.utc)
                self._checkpoint(result)
                if self.config.fail_fast:
                    raise ExecutionError(
                        f"run {result.run_id} failed at {node.id}: {step.error}"
                    ) from error
                return result
            result.state[node.id] = step.output
            after = self._action_constraints(
                node, ConstraintPhase.AFTER_ACTION, result.state, output=step.output
            )
            if self._constraint_stop(result, after):
                return result
            outgoing = self.workflow.outgoing(current)
            if not outgoing or (current in self.workflow.terminals and not outgoing):
                return self._complete(result)
            next_node = self._choose(node, outgoing, result.state, visits, router)
            if next_node is None:
                result.status = ExecutionStatus.VISIT_LIMIT
                result.ended_at = datetime.now(timezone.utc)
                self._checkpoint(result)
                return result
            current = next_node
            result.current_node = current
            self._checkpoint(result)
        result.status = ExecutionStatus.STEP_LIMIT
        result.ended_at = datetime.now(timezone.utc)
        self._checkpoint(result)
        return result

    async def arun(
        self,
        state: dict[str, Any] | None = None,
        *,
        router: AsyncRouter | None = None,
        run_id: str | None = None,
    ) -> ExecutionResult:
        current = self.workflow.start
        result = ExecutionResult(
            run_id=run_id or str(uuid4()),
            workflow=self.workflow.name,
            fingerprint=self.workflow.fingerprint,
            status=ExecutionStatus.RUNNING,
            current_node=current,
            started_at=datetime.now(timezone.utc),
            state=dict(state or {}),
        )
        visits: dict[str, int] = {}
        self._checkpoint(result)
        for _ in range(self.config.max_steps):
            node = self.nodes[current]
            visits[current] = visits.get(current, 0) + 1
            before = self._action_constraints(node, ConstraintPhase.BEFORE_ACTION, result.state)
            if self._constraint_stop(result, before):
                return result
            started = datetime.now(timezone.utc)
            start_clock = time.perf_counter()
            attempts = 0
            error: Exception | None = None
            output: Any = None
            for attempt in range(self.config.retries + 1):
                attempts = attempt + 1
                try:
                    handler = self.registry.handler(node.action)
                    awaitable: Awaitable[Any]
                    if inspect.iscoroutinefunction(handler):
                        awaitable = handler(node, result.state)
                    else:
                        awaitable = asyncio.to_thread(handler, node, result.state)
                    if self.config.timeout_seconds:
                        output = await asyncio.wait_for(
                            awaitable, timeout=self.config.timeout_seconds
                        )
                    else:
                        output = await awaitable
                    if inspect.isawaitable(output):
                        output = await output
                    error = None
                    break
                except Exception as exc:
                    error = exc
                    if attempt < self.config.retries and self.config.retry_delay_seconds:
                        await asyncio.sleep(self.config.retry_delay_seconds)
            ended = datetime.now(timezone.utc)
            step = ExecutionStep(
                node_id=node.id,
                action=node.action,
                status="failed" if error else "completed",
                attempts=attempts,
                started_at=started,
                ended_at=ended,
                duration_ms=(time.perf_counter() - start_clock) * 1_000,
                output=output,
                error=f"{type(error).__name__}: {error}" if error else None,
            )
            result.steps.append(step)
            if self.on_step:
                self.on_step(step)
            if error:
                result.status = ExecutionStatus.FAILED
                result.error = step.error
                result.ended_at = datetime.now(timezone.utc)
                self._checkpoint(result)
                if self.config.fail_fast:
                    raise ExecutionError(
                        f"run {result.run_id} failed at {node.id}: {step.error}"
                    ) from error
                return result
            result.state[node.id] = output
            after = self._action_constraints(
                node, ConstraintPhase.AFTER_ACTION, result.state, output=output
            )
            if self._constraint_stop(result, after):
                return result
            outgoing = self.workflow.outgoing(current)
            if not outgoing or (current in self.workflow.terminals and not outgoing):
                return self._complete(result)
            eligible = [
                edge
                for edge in outgoing
                if visits.get(edge.target, 0) < self.config.max_visits_per_node
            ]
            if not eligible:
                result.status = ExecutionStatus.VISIT_LIMIT
                result.ended_at = datetime.now(timezone.utc)
                self._checkpoint(result)
                return result
            if router:
                routed = router(node, eligible, result.state)
                next_node = await routed if inspect.isawaitable(routed) else routed
            else:
                next_node = eligible[0].target
            if next_node not in {edge.target for edge in eligible}:
                raise RoutingError(
                    f"router selected '{next_node}', which is not an eligible edge from '{node.id}'"
                )
            current = next_node
            result.current_node = current
            self._checkpoint(result)
        result.status = ExecutionStatus.STEP_LIMIT
        result.ended_at = datetime.now(timezone.utc)
        self._checkpoint(result)
        return result
