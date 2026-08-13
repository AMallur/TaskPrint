import asyncio
import time
from pathlib import Path

import pytest
from conftest import make_workflow

from taskprint import (
    ExecutionError,
    HandlerNotFoundError,
    HandlerRegistry,
    RoutingError,
    RuntimeConfig,
    SQLiteRunStore,
    WorkflowRunner,
)


def populated_registry() -> HandlerRegistry:
    registry = HandlerRegistry()
    registry.register("start", lambda node, state: "started")
    registry.register("finish", lambda node, state: "finished")
    return registry


def test_registry_rejects_accidental_replace() -> None:
    registry = HandlerRegistry()
    registry.register("x", lambda node, state: None)
    with pytest.raises(ValueError, match="already"):
        registry.register("x", lambda node, state: None)


def test_registry_lists_missing_handlers() -> None:
    assert populated_registry().missing(make_workflow()) == []
    with pytest.raises(HandlerNotFoundError):
        HandlerRegistry().handler("missing")


def test_retries_then_succeeds() -> None:
    registry = populated_registry()
    attempts = 0

    def flaky(node, state):  # type: ignore[no-untyped-def]
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary")
        return "ok"

    registry.register("start", flaky, replace=True)
    result = WorkflowRunner(make_workflow(), registry, config=RuntimeConfig(retries=1)).run()
    assert result.steps[0].attempts == 2
    assert result.status == "completed"


def test_non_fail_fast_returns_failure() -> None:
    registry = populated_registry()
    registry.register("start", lambda node, state: 1 / 0, replace=True)
    result = WorkflowRunner(make_workflow(), registry, config=RuntimeConfig(fail_fast=False)).run()
    assert result.status == "failed"
    assert "ZeroDivisionError" in (result.error or "")


def test_fail_fast_raises_execution_error() -> None:
    registry = populated_registry()
    registry.register("start", lambda node, state: 1 / 0, replace=True)
    with pytest.raises(ExecutionError):
        WorkflowRunner(make_workflow(), registry).run()


def test_timeout_is_reported() -> None:
    registry = populated_registry()
    registry.register("start", lambda node, state: time.sleep(0.05), replace=True)
    result = WorkflowRunner(
        make_workflow(),
        registry,
        config=RuntimeConfig(timeout_seconds=0.001, fail_fast=False),
    ).run()
    assert result.status == "failed"
    assert "TimeoutError" in (result.error or "")


def test_router_must_choose_real_edge() -> None:
    with pytest.raises(RoutingError):
        WorkflowRunner(make_workflow(), populated_registry()).run(
            router=lambda node, edges, state: "missing"
        )


def test_cycle_stops_at_visit_limit() -> None:
    workflow = make_workflow(cycle=True)
    result = WorkflowRunner(
        workflow,
        populated_registry(),
        config=RuntimeConfig(max_visits_per_node=2),
    ).run()
    assert result.status == "visit_limit"


def test_sqlite_checkpoints_roundtrip(tmp_path: Path) -> None:
    store = SQLiteRunStore(tmp_path / "runs.sqlite")
    result = WorkflowRunner(make_workflow(), populated_registry(), store=store).run()
    loaded = store.load(result.run_id)
    assert loaded is not None
    assert loaded.status == "completed"
    assert store.list(limit=1)[0].run_id == result.run_id


def test_async_runtime_supports_async_handlers() -> None:
    registry = HandlerRegistry()

    async def handler(node, state):  # type: ignore[no-untyped-def]
        await asyncio.sleep(0)
        return node.action

    registry.register("start", handler)
    registry.register("finish", handler)
    result = asyncio.run(WorkflowRunner(make_workflow(), registry).arun())
    assert result.status == "completed"
    assert [step.output for step in result.steps] == ["start", "finish"]
