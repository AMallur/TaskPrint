# Outcome optimization

Taskprint separates observed behavior from the result the workflow is meant to produce.
Demonstrations provide evidence about how work is currently done; an Outcome Contract defines
what a better process means.

## Outcome Contract

Every objective is a numeric dotted-path measurement, a direction, a weight, a desired target,
and an unacceptable boundary. Taskprint linearly normalizes observations between those two
bounds and computes a weighted score from 0 to 1.

```json
{
  "objectives": [
    {
      "name": "resolution rate",
      "source": "trace.success",
      "direction": "maximize",
      "weight": 3,
      "target": 0.98,
      "unacceptable": 0.8
    },
    {
      "name": "review minutes",
      "source": "outcome.review_minutes",
      "direction": "minimize",
      "weight": 1,
      "target": 2,
      "unacceptable": 20
    }
  ]
}
```

Weights express relative preference only. Hard requirements belong in `constraints`, never as
very large objective weights.

## Constraints

Constraints use dotted paths and declarative comparison operators; no expression or application
code is evaluated. They can apply before an action, after an action, or to a final/historical
outcome. Enforcement has three levels:

- `block`: stop the run with `constraint_violation` and make a candidate infeasible.
- `review`: stop the run with `needs_review` or flag historical evidence for review.
- `warn`: record the failed check without stopping execution.

Missing values fail closed by default. Set `missing_passes` only when absence is deliberately
acceptable. An action constraint can target one named action or, if omitted, every action.

## Historical evaluation

Embed a contract during induction and evaluate held-out traces:

```bash
taskprint learn examples/refund/traces.jsonl \
  --objectives examples/refund/objectives.json \
  --output refund.taskprint.json

taskprint check refund.taskprint.json examples/refund/traces.jsonl
```

Structural measures explain whether the workflow covers observed behavior. The `outcomes` section
answers the separate question of whether the observed results satisfy the business objective.

## Candidate optimization

Candidate evidence is deliberately explicit. Each candidate contains historical, simulated, or
pilot observations collected under that process design. Taskprint places feasible candidates
before infeasible ones and then ranks by objective score and evidence volume.

```bash
taskprint optimize refund.taskprint.json examples/refund/candidates.json
```

Taskprint does not claim causal improvement merely because a candidate scores higher. Comparable
cases, sufficient sample sizes, temporal controls, and randomized or carefully matched pilots are
still required for causal claims.

## Active learning

```bash
taskprint gaps refund.taskprint.json --traces held-out.jsonl
```

The report prioritizes sparse branches and missing objective measurements. Its requested
demonstrations are acquisition instructions: collect evidence for the uncertain decision rather
than indiscriminately recording more ordinary cases.

## Runtime context

Runtime objective paths use `state.*`, `run.*`, and the equivalent `trace.*` aliases. Runtime
`outcome.*` reads from `state.outcome`. Before/after action constraints may additionally use
`node.id`, `node.action`, and `output.*`. Historical trace evaluation uses `trace.*`, `run.*`,
`outcome.*`, and `labels.*`.

The application remains responsible for placing business measurements in state and for ensuring
that metrics are defined consistently across candidates and releases.
