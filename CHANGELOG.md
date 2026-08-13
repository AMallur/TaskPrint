# Changelog

This project follows Semantic Versioning for the Python package and explicit versioning for
serialized artifacts.

## 0.3.0 - 2026-08-12

### Added

- Embedded Outcome Contracts with weighted maximize/minimize metrics
- Declarative block, review, and warning constraints for actions and outcomes
- Historical outcome assessment and objective scoring in held-out evaluation
- Evidence-based candidate ranking that always prioritizes feasibility
- Active-learning reports for sparse branches and missing objective measurements
- Runtime constraint checks and `needs_review` / `constraint_violation` statuses
- `--objectives` induction option plus `optimize` and `gaps` CLI commands
- Outcome optimization guide and runnable refund optimization examples

### Compatibility

- The `taskprint/1.0` workflow schema gains an optional `outcome_contract` field. Existing 1.0
  artifacts and Python APIs remain valid.

## 0.2.0 - 2026-08-12

### Added

- Stable `taskprint-trace/1.0` and `taskprint/1.0` schemas
- Automatic workflow migration from `taskprint/0.1`
- Failure-path statistics, Wilson confidence estimates, and cycle metadata
- Async execution, retries, timeouts, bounded traversal, and routing validation
- SQLite checkpoint store and structured execution results
- Browser-event normalization with sensitive-value redaction
- Mermaid, Graphviz, handler-skeleton, and JSON Schema exports
- Semantic workflow validation and expanded CLI
- Python 3.10–3.13 CI, type checking, coverage, package, and security checks

### Changed

- Public models now reject unknown fields instead of silently accepting misspellings
- Workflow schema moved from `taskprint/0.1` to `taskprint/1.0`
- Failure paths are included by default

## 0.1.0 - 2026-08-12

- Initial deterministic induction, evaluation, CLI, and synchronous runtime prototype
