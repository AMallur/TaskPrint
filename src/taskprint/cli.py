from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

import typer

from .capture import browser_records_to_trace
from .evaluate import evaluate
from .exporters import schema_json, to_dot, to_handler_skeleton, to_mermaid
from .induce import InductionConfig, induce
from .io import (
    load_candidate_evidence,
    load_outcome_contract,
    load_traces,
    load_workflow,
    save_traces,
    save_workflow,
)
from .learning import analyze_learning_needs
from .objectives import rank_candidates
from .validation import validate_workflow

app = typer.Typer(no_args_is_help=True, help="Learn executable workflows from task traces.")


@app.command()
def learn(
    traces: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("workflow.taskprint.json"),
    name: Annotated[str | None, typer.Option()] = None,
    minimum_support: Annotated[float, typer.Option(min=0, max=1)] = 0.5,
    include_failures: Annotated[bool, typer.Option("--include-failures/--success-only")] = True,
    objectives: Annotated[
        Path | None, typer.Option("--objectives", exists=True, readable=True)
    ] = None,
) -> None:
    """Induce an editable workflow from JSON or JSONL demonstrations."""
    contract = load_outcome_contract(objectives) if objectives else None
    workflow = induce(
        load_traces(traces),
        name=name,
        config=InductionConfig(
            minimum_support=minimum_support, include_failure_paths=include_failures
        ),
        outcome_contract=contract,
    )
    save_workflow(workflow, output)
    typer.echo(
        f"Learned {len(workflow.nodes)} nodes and {len(workflow.edges)} transitions "
        f"from {workflow.trace_count} traces -> {output}"
    )


@app.command("capture-browser")
def capture_browser(
    records: Annotated[Path, typer.Argument(exists=True, readable=True)],
    task: Annotated[str, typer.Option("--task")],
    trace_id: Annotated[str, typer.Option("--trace-id")],
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("trace.jsonl"),
    success: Annotated[bool, typer.Option("--success/--failure")] = True,
) -> None:
    """Normalize generic browser event JSON into a Taskprint trace."""
    payload = json.loads(records.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("events", [])
    trace = browser_records_to_trace(rows, trace_id=trace_id, task=task, success=success)
    save_traces([trace], output)
    typer.echo(f"Captured {len(trace.events)} semantic events -> {output}")


@app.command()
def inspect(
    workflow: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    """Print a compact, human-readable workflow."""
    graph = load_workflow(workflow)
    typer.echo(f"{graph.name} [{graph.fingerprint}] — {graph.task}")
    if graph.outcome_contract:
        typer.echo(
            f"  objectives: {len(graph.outcome_contract.objectives)}; "
            f"constraints: {len(graph.outcome_contract.constraints)}"
        )
    for node in graph.nodes:
        marker = "*" if node.required else "?"
        typer.echo(
            f"  {marker} {node.id}: {node.action} ({node.kind.value}) support={node.support:.0%}"
        )
        for edge in graph.outgoing(node.id):
            cycle = " loop" if edge.is_cycle else ""
            typer.echo(
                f"      -> {edge.target}  p={edge.probability:.2f} n={edge.observed_count}{cycle}"
            )


@app.command()
def check(
    workflow: Annotated[Path, typer.Argument(exists=True, readable=True)],
    traces: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    """Measure how well a workflow explains held-out task traces."""
    report = evaluate(load_workflow(workflow), load_traces(traces))
    typer.echo(json.dumps(report.model_dump(), indent=2))


@app.command()
def validate(
    workflow: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    """Validate schema and graph integrity; exit nonzero on errors."""
    graph = load_workflow(workflow)
    report = validate_workflow(graph)
    typer.echo(json.dumps(report.model_dump(), indent=2))
    if not report.valid:
        raise typer.Exit(code=1)


@app.command()
def optimize(
    workflow: Annotated[Path, typer.Argument(exists=True, readable=True)],
    evidence: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    """Rank candidate workflow designs against the embedded Outcome Contract."""
    graph = load_workflow(workflow)
    if not graph.outcome_contract:
        raise typer.BadParameter("workflow has no Outcome Contract")
    candidates = load_candidate_evidence(evidence)
    if not candidates:
        raise typer.BadParameter("candidate evidence must contain at least one candidate")
    ranked = rank_candidates(graph.outcome_contract, candidates)
    typer.echo(json.dumps([item.model_dump(mode="json") for item in ranked], indent=2))


@app.command()
def gaps(
    workflow: Annotated[Path, typer.Argument(exists=True, readable=True)],
    traces: Annotated[Path | None, typer.Option("--traces", exists=True, readable=True)] = None,
    confidence: Annotated[float, typer.Option(min=0, max=1)] = 0.35,
) -> None:
    """Request the demonstrations that would reduce important uncertainty."""
    report = analyze_learning_needs(
        load_workflow(workflow),
        load_traces(traces) if traces else (),
        confidence_threshold=confidence,
    )
    typer.echo(json.dumps(report.model_dump(mode="json"), indent=2))


@app.command("export")
def export_workflow(
    workflow: Annotated[Path, typer.Argument(exists=True, readable=True)],
    format: Annotated[Literal["mermaid", "dot", "handlers"], typer.Option("--format", "-f")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Export a workflow as a diagram or executable handler skeleton."""
    graph = load_workflow(workflow)
    rendered = {
        "mermaid": to_mermaid,
        "dot": to_dot,
        "handlers": to_handler_skeleton,
    }[format](graph)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        typer.echo(str(output))
    else:
        typer.echo(rendered, nl=False)


@app.command()
def schema(
    kind: Annotated[Literal["workflow", "trace"], typer.Argument()],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Emit the authoritative JSON Schema for a public artifact."""
    rendered = schema_json(kind)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        typer.echo(str(output))
    else:
        typer.echo(rendered, nl=False)


@app.command()
def migrate(
    workflow: Annotated[Path, typer.Argument(exists=True, readable=True)],
    output: Annotated[Path, typer.Option("--output", "-o")],
) -> None:
    """Migrate an older supported workflow to the current schema."""
    graph = load_workflow(workflow)
    save_workflow(graph, output)
    typer.echo(f"Migrated to {graph.schema_version} -> {output}")


if __name__ == "__main__":
    app()
