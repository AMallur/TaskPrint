from datetime import datetime, timezone

import pytest

from taskprint import BrowserRecord, EventKind, browser_records_to_trace


def test_browser_capture_filters_noise_and_maps_kinds() -> None:
    trace = browser_records_to_trace(
        [
            {"event": "mousemove"},
            {"event": "navigate", "url": "https://example.com"},
            {"event": "fill", "selector": "#email", "value": "a@example.com"},
            {"event": "click", "selector": "button.submit"},
        ],
        trace_id="browser-1",
        task="Submit form",
    )
    assert len(trace.events) == 3
    assert [event.kind for event in trace.events] == [
        EventKind.OBSERVE,
        EventKind.INPUT,
        EventKind.ACTION,
    ]


def test_browser_capture_redacts_sensitive_values() -> None:
    trace = browser_records_to_trace(
        [{"event": "fill", "selector": "#password", "value": "do-not-store"}],
        trace_id="browser-2",
        task="Sign in",
    )
    assert trace.events[0].value == "[REDACTED]"


def test_browser_capture_redacts_sensitive_metadata_and_url() -> None:
    trace = browser_records_to_trace(
        [
            {
                "event": "navigate",
                "url": "https://example.test/callback?token=abc&view=full#secret",
                "metadata": {"authorization": "Bearer abc", "safe": "yes"},
            }
        ],
        trace_id="browser-3",
        task="Callback",
    )
    event = trace.events[0]
    assert "abc" not in (event.target or "")
    assert "secret" not in (event.target or "")
    assert event.data["authorization"] == "[REDACTED]"
    assert event.data["safe"] == "yes"


def test_browser_capture_preserves_time_bounds() -> None:
    now = datetime.now(timezone.utc)
    trace = browser_records_to_trace(
        [BrowserRecord(event="click", timestamp=now)], trace_id="b", task="Click"
    )
    assert trace.started_at == now
    assert trace.ended_at == now


def test_browser_capture_rejects_empty_semantic_capture() -> None:
    with pytest.raises(ValueError, match="no meaningful"):
        browser_records_to_trace([{"event": "scroll"}], trace_id="b", task="Noise")
