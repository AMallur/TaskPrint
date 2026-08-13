import asyncio
import json
from pathlib import Path

import pytest
from conftest import make_trace, make_workflow
from pydantic import ValidationError
from typer.testing import CliRunner

from taskprint import (
    CandidateEvidence,
    ConstraintEnforcement,
    ConstraintOperator,
    ConstraintPhase,
    HandlerRegistry,
    ObjectiveDirection,
    ObjectiveMetric,
    OutcomeConstraint,
    OutcomeContract,
    RuntimeConfig,
    WorkflowRunner,
    analyze_learning_needs,
    assess_traces,
    induce,
    rank_candidates,
)
from taskprint.cli import app
from taskprint.io import save_traces, save_workflow
from taskprint.objectives import check_constraint, resolve_source


def make_contract() -> OutcomeContract:
    return OutcomeContract(
        description="Recover value safely",
        objectives=[
            ObjectiveMetric(
                name="success rate",
                source="trace.success",
                direction=ObjectiveDirection.MAXIMIZE,
                target=0.9,
                unacceptable=0.5,
                weight=3,
            ),
            ObjectiveMetric(
                name="review minutes",
                source="outcome.review_minutes",
                direction=ObjectiveDirection.MINIMIZE,
                target=5,
                unacceptable=30,
            ),
        ],
        constraints=[
            OutcomeConstraint(
                id="no_privacy_incident",
                description="Privacy incidents are prohibited",
                source="outcome.privacy_incidents",
                operator=ConstraintOperator.EQ,
                expected=0,
            )
        ],
    )


def test_contract_rejects_invalid_metric_bounds() -> None:
    with pytest.raises(ValidationError, match="unacceptable < target"):
        ObjectiveMetric(
            name="bad",
            source="outcome.x",
            direction=ObjectiveDirection.MAXIMIZE,
            target=1,
            unacceptable=2,
        )


def test_contract_rejects_duplicate_names_and_missing_expected() -> None:
    metric = ObjectiveMetric(
        name="duplicate",
        source="outcome.x",
        direction=ObjectiveDirection.MAXIMIZE,
        target=1,
        unacceptable=0,
    )
    with pytest.raises(ValidationError, match="metric names"):
        OutcomeContract(objectives=[metric, metric])
    with pytest.raises(ValidationError, match="expected is required"):
        OutcomeConstraint(
            id="missing",
            description="invalid",
            source="state.x",
            operator=ConstraintOperator.EQ,
        )


@pytest.mark.parametrize(
    ("operator", "observed", "expected", "passed"),
    [
        (ConstraintOperator.EQ, 2, 2, True),
        (ConstraintOperator.NE, 2, 3, True),
        (ConstraintOperator.GT, 3, 2, True),
        (ConstraintOperator.GTE, 2, 2, True),
        (ConstraintOperator.LT, 1, 2, True),
        (ConstraintOperator.LTE, 2, 2, True),
        (ConstraintOperator.IN, "a", ["a", "b"], True),
        (ConstraintOperator.NOT_IN, "z", ["a", "b"], True),
        (ConstraintOperator.EQ, 2, 3, False),
    ],
)
def test_declarative_constraint_operators(
    operator: ConstraintOperator, observed: object, expected: object, passed: bool
) -> None:
    constraint = OutcomeConstraint(
        id="check",
        description="operator check",
        source="value",
        operator=operator,
        expected=expected,
    )
    assert check_constraint(constraint, {"value": observed}).passed is passed


def test_exists_constraint_and_safe_path_resolution() -> None:
    constraint = OutcomeConstraint(
        id="present",
        description="value must exist",
        source="items.0.value",
        operator=ConstraintOperator.EXISTS,
    )
    context = {"items": [{"value": 7}]}
    assert resolve_source(context, "items.0.value") == 7
    assert check_constraint(constraint, context).passed is True
    assert check_constraint(constraint, {}).passed is False
    incompatible = OutcomeConstraint(
        id="typed",
        description="invalid comparisons fail closed",
        source="value",
        operator=ConstraintOperator.GT,
        expected=2,
    )
    assert check_constraint(incompatible, {"value": "not-a-number"}).passed is False


def test_assesses_trace_outcomes_and_constraints() -> None:
    first = make_trace("t1")
    first.outcome = {"review_minutes": 5, "privacy_incidents": 0}
    second = make_trace("t2", success=False)
    second.outcome = {"review_minutes": 15, "privacy_incidents": 1}
    report = assess_traces(make_contract(), [first, second])
    assert report.observations == 2
    assert report.metrics[0].observed == 0.5
    assert report.metrics[1].score == pytest.approx(0.8)
    assert report.feasible is False
    assert report.blocking_violations == 1


def test_rank_candidates_puts_feasibility_before_score() -> None:
    contract = make_contract()
    risky = CandidateEvidence(
        name="risky",
        observations=[
            {
                "trace": {"success": True},
                "outcome": {"review_minutes": 1, "privacy_incidents": 1},
            }
        ],
    )
    safe = CandidateEvidence(
        name="safe",
        observations=[
            {
                "trace": {"success": True},
                "outcome": {"review_minutes": 10, "privacy_incidents": 0},
            }
        ],
    )
    ranked = rank_candidates(contract, [risky, safe])
    assert [candidate.name for candidate in ranked] == ["safe", "risky"]
    assert ranked[0].rank == 1


def test_induction_embeds_contract_and_evaluation_uses_it() -> None:
    trace = make_trace()
    trace.outcome = {"review_minutes": 5, "privacy_incidents": 0}
    workflow = induce([trace], outcome_contract=make_contract())
    assert workflow.outcome_contract is not None
    assert workflow.outcome_contract.objectives[0].name == "success rate"


def test_runtime_pauses_for_human_review_gate() -> None:
    workflow = make_workflow()
    workflow.outcome_contract = OutcomeContract(
        objectives=[
            ObjectiveMetric(
                name="completion",
                source="run.success",
                direction=ObjectiveDirection.MAXIMIZE,
                target=1,
                unacceptable=0,
            )
        ],
        constraints=[
            OutcomeConstraint(
                id="approval",
                description="Approval is required before finishing",
                source="state.approved",
                operator=ConstraintOperator.EQ,
                expected=True,
                phase=ConstraintPhase.BEFORE_ACTION,
                enforcement=ConstraintEnforcement.REVIEW,
                action="finish",
            )
        ],
    )
    registry = HandlerRegistry()
    registry.register("start", lambda node, state: "started")
    registry.register("finish", lambda node, state: "finished")
    result = WorkflowRunner(workflow, registry).run()
    assert result.status == "needs_review"
    assert [step.action for step in result.steps] == ["start"]
    assert result.constraint_checks[-1].id == "approval"


def test_runtime_enforces_post_action_block_and_can_be_disabled() -> None:
    workflow = make_workflow()
    workflow.outcome_contract = OutcomeContract(
        objectives=[
            ObjectiveMetric(
                name="completion",
                source="run.success",
                direction=ObjectiveDirection.MAXIMIZE,
                target=1,
                unacceptable=0,
            )
        ],
        constraints=[
            OutcomeConstraint(
                id="safe_output",
                description="Handler must report safe output",
                source="output.safe",
                operator=ConstraintOperator.EQ,
                expected=True,
                phase=ConstraintPhase.AFTER_ACTION,
                action="start",
            )
        ],
    )
    registry = HandlerRegistry()
    registry.register("start", lambda node, state: {"safe": False})
    registry.register("finish", lambda node, state: "finished")
    blocked = WorkflowRunner(workflow, registry).run()
    assert blocked.status == "constraint_violation"
    bypassed = WorkflowRunner(
        workflow, registry, config=RuntimeConfig(enforce_constraints=False)
    ).run()
    assert bypassed.status == "completed"


def test_async_runtime_enforces_post_action_constraint() -> None:
    workflow = make_workflow()
    workflow.outcome_contract = OutcomeContract(
        objectives=[
            ObjectiveMetric(
                name="completion",
                source="run.success",
                direction=ObjectiveDirection.MAXIMIZE,
                target=1,
                unacceptable=0,
            )
        ],
        constraints=[
            OutcomeConstraint(
                id="async_safe",
                description="Async output must be safe",
                source="output.safe",
                operator=ConstraintOperator.EQ,
                expected=True,
                phase=ConstraintPhase.AFTER_ACTION,
                action="start",
            )
        ],
    )
    registry = HandlerRegistry()

    async def unsafe(node, state):  # type: ignore[no-untyped-def]
        await asyncio.sleep(0)
        return {"safe": False}

    registry.register("start", unsafe)
    registry.register("finish", unsafe)
    result = asyncio.run(WorkflowRunner(workflow, registry).arun())
    assert result.status == "constraint_violation"


def test_warning_constraint_is_recorded_without_stopping() -> None:
    workflow = make_workflow()
    workflow.outcome_contract = OutcomeContract(
        objectives=[
            ObjectiveMetric(
                name="completion",
                source="run.success",
                direction=ObjectiveDirection.MAXIMIZE,
                target=1,
                unacceptable=0,
            )
        ],
        constraints=[
            OutcomeConstraint(
                id="warning",
                description="Record an optional flag",
                source="state.optional_flag",
                operator=ConstraintOperator.EQ,
                expected=True,
                phase=ConstraintPhase.BEFORE_ACTION,
                enforcement=ConstraintEnforcement.WARN,
                action="start",
            )
        ],
    )
    registry = HandlerRegistry()
    registry.register("start", lambda node, state: "started")
    registry.register("finish", lambda node, state: "finished")
    result = WorkflowRunner(workflow, registry).run()
    assert result.status == "completed"
    assert result.constraint_checks[0].passed is False


def test_completed_run_receives_objective_score() -> None:
    workflow = make_workflow()
    workflow.outcome_contract = OutcomeContract(
        objectives=[
            ObjectiveMetric(
                name="completion",
                source="run.success",
                direction=ObjectiveDirection.MAXIMIZE,
                target=1,
                unacceptable=0,
            )
        ]
    )
    registry = HandlerRegistry()
    registry.register("start", lambda node, state: "started")
    registry.register("finish", lambda node, state: "finished")
    result = WorkflowRunner(workflow, registry).run()
    assert result.outcome_assessment is not None
    assert result.outcome_assessment.score == 1


def test_active_learning_prioritizes_sparse_branch_and_missing_outcomes() -> None:
    traces = [
        make_trace("a", actions=("start", "common")),
        make_trace("b", actions=("start", "rare")),
    ]
    workflow = induce(traces, outcome_contract=make_contract())
    report = analyze_learning_needs(workflow, traces)
    assert report.ready_for_optimization is False
    assert "underobserved_branch" in {need.code for need in report.needs}
    assert "missing_objective_evidence" in {need.code for need in report.needs}


def test_cli_learn_optimize_and_gaps(tmp_path: Path) -> None:
    runner = CliRunner()
    traces_path = tmp_path / "traces.jsonl"
    contract_path = tmp_path / "objectives.json"
    workflow_path = tmp_path / "workflow.json"
    evidence_path = tmp_path / "candidates.json"
    trace = make_trace()
    trace.outcome = {"review_minutes": 5, "privacy_incidents": 0}
    save_traces([trace], traces_path)
    contract_path.write_text(make_contract().model_dump_json())

    learned = runner.invoke(
        app,
        [
            "learn",
            str(traces_path),
            "--objectives",
            str(contract_path),
            "-o",
            str(workflow_path),
        ],
    )
    assert learned.exit_code == 0, learned.output

    evidence_path.write_text(
        json.dumps(
            [
                {
                    "name": "candidate-a",
                    "observations": [
                        {
                            "trace": {"success": True},
                            "outcome": {"review_minutes": 5, "privacy_incidents": 0},
                        }
                    ],
                }
            ]
        )
    )
    optimized = runner.invoke(app, ["optimize", str(workflow_path), str(evidence_path)])
    assert optimized.exit_code == 0, optimized.output
    assert '"name": "candidate-a"' in optimized.output

    gaps = runner.invoke(app, ["gaps", str(workflow_path), "--traces", str(traces_path)])
    assert gaps.exit_code == 0, gaps.output
    assert "ready_for_optimization" in gaps.output


def test_save_workflow_preserves_contract(tmp_path: Path) -> None:
    workflow = make_workflow()
    workflow.outcome_contract = make_contract()
    path = tmp_path / "workflow.json"
    save_workflow(workflow, path)
    assert '"outcome_contract"' in path.read_text()
