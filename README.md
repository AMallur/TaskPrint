# Taskprint

**Show Taskprint how work is done and define what good means. Get a constrained, measurable,
executable workflow.**

Taskprint is a Python framework for **workflow induction**: learning an explicit,
reviewable workflow from successful and failed demonstrations of a task. Its Outcome Contract
then separates imitation from optimization: workflows are scored by results, cost, time, human
effort, and risk instead of only by how closely they reproduce observed clicks.

```text
browser or application events
            ↓
normalized task traces
            ↓
workflow induction + confidence estimates
            ↓
Outcome Contract + held-out evaluation
            ↓
candidate ranking + active learning
            ↓
constrained application-owned execution
```

Taskprint does not replace LangGraph, CrewAI, or an LLM SDK. Those systems execute logic a
developer has already specified. Taskprint addresses the prior question: **what workflow
should the agent execute, according to actual demonstrations—and which valid version best achieves
the intended outcome?**

## Status

Version 0.3 is a production-candidate SDK, not a claim of universal workflow understanding or
causal process optimization.

| Capability | Status |
| --- | --- |
| Strict trace/workflow schemas | Implemented and versioned |
| v0.1 workflow migration | Implemented |
| Branch, variant, failure-path, and cycle discovery | Implemented |
| Confidence and held-out path metrics | Implemented |
| Weighted Outcome Contracts and outcome scoring | Implemented |
| Candidate evidence ranking under hard constraints | Implemented |
| Active-learning demonstration requests | Implemented baseline |
| Runtime block, review, and warning constraints | Implemented |
| Sync/async runtime, retries, timeout, bounded cycles | Implemented |
| SQLite run checkpoints | Implemented |
| Browser-event normalization and secret redaction | Implemented baseline |
| Mermaid, Graphviz, handler, and JSON Schema exports | Implemented |
| Learned semantic alignment across visually different actions | Research roadmap |
| Hosted multimodal Taskprint Capture | Not included |
| Large integration ecosystem and production history | Requires external adoption |

## Install and verify

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

taskprint learn examples/refund/traces.jsonl \
  --objectives examples/refund/objectives.json \
  -o refund.taskprint.json
taskprint validate refund.taskprint.json
taskprint inspect refund.taskprint.json
taskprint check refund.taskprint.json examples/refund/traces.jsonl
taskprint optimize refund.taskprint.json examples/refund/candidates.json
taskprint gaps refund.taskprint.json --traces examples/refund/traces.jsonl
taskprint export refund.taskprint.json --format mermaid

pytest --cov=taskprint --cov-fail-under=85
mypy src/taskprint
ruff check .
```

No model key or hosted service is required.

## Trace format

```json
{
  "schema_version": "taskprint-trace/1.0",
  "id": "refund-001",
  "task": "Process a customer refund",
  "success": true,
  "events": [
    {"type": "read_request", "kind": "observe", "target": "support_ticket"},
    {"type": "lookup_order", "kind": "action", "target": "orders_api"},
    {"type": "check_policy", "kind": "decision", "target": "refund_policy"},
    {"type": "issue_refund", "kind": "action", "target": "payments_api"}
  ]
}
```

Generate authoritative schemas with:

```bash
taskprint schema trace
taskprint schema workflow
```

See [Trace specification](docs/TRACE_SPEC.md) and [Compatibility](docs/COMPATIBILITY.md).

## Induce and evaluate

```python
from taskprint import InductionConfig, evaluate, induce
from taskprint.io import load_traces

training = load_traces("train.jsonl")
workflow = induce(
    training,
    name="refund",
    config=InductionConfig(
        minimum_support=0.6,
        include_failure_paths=True,
    ),
)

held_out = load_traces("held-out.jsonl")
report = evaluate(workflow, held_out)
print(report.exact_path_rate)
print(report.mean_path_similarity)
print(report.outcomes.score if report.outcomes else "no Outcome Contract")
```

The baseline inducer is deterministic and inspectable. It constructs a directly-follows
graph, records stable parameters and variants, separates success/failure observations,
computes Wilson lower confidence bounds, and marks cycle membership.

## Optimize for the outcome

An Outcome Contract defines weighted preferences and non-negotiable boundaries:

```python
from taskprint import ObjectiveDirection, ObjectiveMetric, OutcomeContract

contract = OutcomeContract(
    objectives=[
        ObjectiveMetric(
            name="resolution rate",
            source="trace.success",
            direction=ObjectiveDirection.MAXIMIZE,
            weight=3,
            target=0.98,
            unacceptable=0.80,
        ),
        ObjectiveMetric(
            name="review minutes",
            source="outcome.review_minutes",
            direction=ObjectiveDirection.MINIMIZE,
            target=2,
            unacceptable=20,
        ),
    ]
)

workflow = induce(training, outcome_contract=contract)
```

`taskprint optimize` ranks candidate process designs using historical, simulated, or pilot
observations. A candidate that violates a blocking constraint is never recommended over a feasible
candidate merely because it is faster. `taskprint gaps` asks for demonstrations of sparse branches
and for missing outcome evidence.

See [Outcome optimization](docs/OUTCOME_OPTIMIZATION.md) for scoring semantics, constraint phases,
runtime context, and the limits of causal claims.

## Execute reliably

Execution is explicit: application code owns every action handler.

```python
from taskprint import (
    HandlerRegistry,
    RuntimeConfig,
    SQLiteRunStore,
    WorkflowRunner,
)

handlers = HandlerRegistry()
handlers.register("lookup_order", lookup_order)
handlers.register("check_policy", check_policy)
handlers.register("issue_refund", issue_refund)

runner = WorkflowRunner(
    workflow,
    handlers,
    config=RuntimeConfig(
        retries=2,
        timeout_seconds=30,
        max_visits_per_node=5,
    ),
    store=SQLiteRunStore("taskprint-runs.sqlite"),
)

result = runner.run({"order_id": "ORD-900"})
# async: result = await runner.arun(...)
```

The default route is the most frequently observed eligible transition. Supply a router for
business-specific decisions. A router may only select an actual outgoing edge.
Before/after action constraints are evaluated around handlers. A failed `block` rule returns
`constraint_violation`; a failed `review` rule returns `needs_review`; a `warn` rule is recorded and
execution continues. Final objective scores and outcome constraints are attached to completed runs.

## Capture browser work

Normalize generic browser telemetry before induction:

```bash
taskprint capture-browser examples/browser/events.json \
  --task "Submit a support request" \
  --trace-id browser-001 \
  --output browser-trace.jsonl
```

Noisy events such as scrolling and mouse movement are dropped. Values associated with
passwords, tokens, authorization, API keys, SSNs, or cards are redacted by default. This is
a safety baseline, not a substitute for an organization’s data-loss-prevention controls.

## Repository map

```text
src/taskprint/
  capture.py       browser-event normalization
  induce.py        deterministic workflow induction
  evaluate.py      held-out evaluation
  objectives.py    objective scoring and candidate ranking
  learning.py      active-learning evidence requests
  models.py        public versioned schemas
  runtime.py       reliable sync/async execution
  persistence.py   SQLite checkpoints
  exporters.py     diagrams, code skeletons, JSON Schema
  validation.py    semantic workflow validation
  io.py            atomic I/O and schema migration
tests/              unit, integration, CLI, async, and persistence tests
schemas/            checked-in JSON Schemas
docs/               architecture and operating contracts
```

## Product boundary

Taskprint Core remains open: schemas, induction, optimization, evaluation, execution, migration,
and export. The potential commercial product is **Taskprint Capture**, a higher-accuracy service
for converting screen video, browser sessions, email threads, documents, and application
logs into normalized traces. It does not exist in this repository and should not be marketed
as released.

## Security and production use

Read [Production guide](docs/PRODUCTION.md) before running handlers with access to real
systems. Taskprint does not sandbox handlers or infer authorization. Use least-privilege
credentials, idempotent actions, approval gates, and application-level transaction controls.
Report security issues according to [SECURITY.md](SECURITY.md).

Apache-2.0. See [CHANGELOG.md](CHANGELOG.md) for compatibility-impacting changes.
