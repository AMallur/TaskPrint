# Production operating guide

Taskprint v0.3 is suitable for controlled pilots where developers review the induced workflow
and provide explicit handlers. It should not be allowed to operate privileged systems merely
because a workflow was learned from demonstrations.

## Required controls

1. Review and version-control every workflow before deployment.
2. Evaluate against held-out traces, including known failures and exceptions.
3. Use idempotency keys for handlers that create, send, refund, delete, or modify state.
4. Give each handler the smallest practical credential scope.
5. Put consequential branches behind deterministic policy checks or human approval.
6. Set runtime timeouts, retry limits, step limits, and node-visit limits.
7. Persist runs and correlate `run_id` with external transaction IDs.
8. Redact or tokenize sensitive data before creating traces.
9. Test rollback and reconciliation outside the Taskprint process.
10. Pin dependency versions and run vulnerability scans in release CI.
11. Define objective units, collection windows, and denominators before comparing candidates.
12. Treat missing constraint inputs as failures unless a reviewed policy explicitly allows them.
13. Require approval and a versioned release before promoting an optimized candidate.

## Runtime semantics

- A successful handler output is written under its node ID in execution state.
- Retries apply to any exception raised across the handler boundary.
- Sync timeouts return control but cannot forcibly stop arbitrary Python thread code. Handlers
  must therefore use their own network/database timeouts and cancellation mechanisms.
- Async timeouts use `asyncio.wait_for` and propagate cancellation to cooperative handlers.
- Default routing selects the highest observed-probability eligible edge.
- Routers cannot select a node that is not an outgoing eligible transition.
- A run returns `visit_limit` or `step_limit` instead of traversing forever.
- With `fail_fast=True`, failed handlers are checkpointed before `ExecutionError` is raised.
- Before/after action constraints receive only declarative dotted-path context; Taskprint never
  evaluates arbitrary expressions from a workflow artifact.
- Blocking constraints return `constraint_violation`; review constraints return `needs_review`;
  warnings are recorded in `constraint_checks` and do not stop execution.
- Completed runs include `outcome_assessment`. Applications must deliberately put the necessary
  business measurements under `state.*`; Taskprint does not infer missing financial or risk data.

## Optimization evidence

Candidate rankings are decision support, not causal proof. Compare candidates on equivalent case
populations and collection windows. For consequential changes, use a randomized pilot or a
pre-registered matched design, minimum sample sizes, confidence intervals, and human review of
constraint violations. Never use the objective score as the only approval criterion.

## Deployment boundary

The included SQLite store is appropriate for local processes and modest single-service pilots.
High-throughput distributed execution needs an external transactional store and coordination
layer. The `RunStore` protocol is the supported extension boundary.
