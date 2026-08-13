from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field

from .models import Event, EventKind, Trace


class BrowserRecord(BaseModel):
    """Framework-neutral browser or UI telemetry record."""

    model_config = ConfigDict(extra="allow")

    event: str = Field(min_length=1)
    selector: str | None = None
    url: str | None = None
    value: Any = None
    timestamp: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaptureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    redact_values: bool = True
    sensitive_pattern: str = r"(?i)(password|secret|token|authorization|api.?key|ssn|card)"
    drop_events: set[str] = Field(default_factory=lambda: {"mousemove", "scroll", "hover"})


_KIND_MAP = {
    "click": EventKind.ACTION,
    "submit": EventKind.ACTION,
    "navigate": EventKind.OBSERVE,
    "navigation": EventKind.OBSERVE,
    "goto": EventKind.OBSERVE,
    "fill": EventKind.INPUT,
    "input": EventKind.INPUT,
    "type": EventKind.INPUT,
    "select": EventKind.INPUT,
    "download": EventKind.OUTPUT,
    "upload": EventKind.ACTION,
    "human_approval": EventKind.HUMAN,
}


def _semantic_name(record: BrowserRecord) -> str:
    event = re.sub(r"[^a-z0-9]+", "_", record.event.lower()).strip("_")
    if record.selector:
        target = record.selector
    elif record.url:
        parts = urlsplit(record.url)
        target = f"{parts.netloc}{parts.path}"
    else:
        target = "page"
    target = re.sub(r"[^a-zA-Z0-9]+", "_", target).strip("_").lower()[:60]
    return f"{event}_{target}" if target else event


def _sanitize_url(url: str | None, sensitive: re.Pattern[str]) -> str | None:
    if not url:
        return url
    parts = urlsplit(url)
    query = [
        (key, "[REDACTED]" if sensitive.search(key) else value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def browser_records_to_trace(
    records: list[BrowserRecord | dict[str, Any]],
    *,
    trace_id: str,
    task: str,
    success: bool = True,
    config: CaptureConfig | None = None,
) -> Trace:
    """Normalize browser telemetry into a safe Taskprint trace."""

    config = config or CaptureConfig()
    sensitive = re.compile(config.sensitive_pattern)
    events: list[Event] = []
    parsed = [
        record if isinstance(record, BrowserRecord) else BrowserRecord.model_validate(record)
        for record in records
    ]
    for record in parsed:
        event_name = record.event.lower()
        if event_name in config.drop_events:
            continue
        value = record.value
        sanitized_metadata = {
            key: "[REDACTED]" if config.redact_values and sensitive.search(key) else item
            for key, item in record.metadata.items()
        }
        searchable = " ".join([record.selector or "", *record.metadata.keys()])
        if config.redact_values and sensitive.search(searchable):
            value = "[REDACTED]"
        sanitized_url = _sanitize_url(record.url, sensitive) if config.redact_values else record.url
        sanitized = record.model_copy(update={"url": sanitized_url})
        events.append(
            Event(
                type=_semantic_name(sanitized),
                kind=_KIND_MAP.get(event_name, EventKind.ACTION),
                actor="human",
                target=record.selector or sanitized_url,
                value=value,
                data={"source_event": record.event, **sanitized_metadata},
                timestamp=record.timestamp,
            )
        )
    if not events:
        raise ValueError("capture contains no meaningful events after filtering")
    timestamps = [record.timestamp for record in parsed if record.timestamp]
    return Trace(
        id=trace_id,
        task=task,
        events=events,
        success=success,
        source="browser",
        started_at=min(timestamps) if timestamps else None,
        ended_at=max(timestamps) if timestamps else None,
    )
