import json
from pathlib import Path

from conftest import make_trace
from typer.testing import CliRunner

from taskprint.cli import app
from taskprint.io import save_traces

runner = CliRunner()


def test_cli_end_to_end(tmp_path: Path) -> None:
    traces = tmp_path / "traces.jsonl"
    workflow = tmp_path / "workflow.json"
    diagram = tmp_path / "workflow.mmd"
    save_traces([make_trace()], traces)

    learned = runner.invoke(app, ["learn", str(traces), "-o", str(workflow)])
    assert learned.exit_code == 0, learned.output
    assert workflow.exists()

    validated = runner.invoke(app, ["validate", str(workflow)])
    assert validated.exit_code == 0
    assert '"valid": true' in validated.output

    checked = runner.invoke(app, ["check", str(workflow), str(traces)])
    assert checked.exit_code == 0
    assert '"exact_path_rate": 1.0' in checked.output

    exported = runner.invoke(
        app, ["export", str(workflow), "--format", "mermaid", "-o", str(diagram)]
    )
    assert exported.exit_code == 0
    assert "flowchart TD" in diagram.read_text()


def test_cli_capture_browser(tmp_path: Path) -> None:
    raw = tmp_path / "raw.json"
    output = tmp_path / "trace.jsonl"
    raw.write_text(json.dumps([{"event": "click", "selector": "#go"}]))
    result = runner.invoke(
        app,
        [
            "capture-browser",
            str(raw),
            "--task",
            "Go",
            "--trace-id",
            "t1",
            "-o",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert output.exists()
