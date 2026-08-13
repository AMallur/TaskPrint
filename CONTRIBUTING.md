# Contributing

Taskprint is early and evidence-led. A useful contribution should improve at least one of:

- trace normalization,
- workflow induction on held-out demonstrations,
- workflow evaluation,
- export into an established agent runtime, or
- a reproducible task dataset.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff format .
ruff check .
mypy src/taskprint
pytest --cov=taskprint --cov-fail-under=85
python -m build
```

New induction behavior must include a trace fixture and a held-out assertion. Avoid adding
provider abstractions, memory systems, or agent orchestration features that belong in the
downstream runtimes Taskprint will export to.

Public changes must update type hints, tests, and the changelog. Serialized artifact changes
must also update JSON Schemas and the compatibility document.
