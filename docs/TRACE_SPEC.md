# Taskprint trace specification 1.0

A trace is one observed attempt to complete one named task. JSONL is recommended: one trace
per line.

## Required trace fields

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | string | `taskprint-trace/1.0` |
| `id` | string | Unique within an induction dataset |
| `task` | string | Stable task-family name |
| `events` | array | At least one semantic event |
| `success` | boolean | Whether the attempt achieved its intended outcome |

Optional fields include `outcome`, `labels`, `source`, `started_at`, and `ended_at`.

## Event contract

An event has a semantic `type` and one of six kinds:

- `observe`: read or inspect state;
- `input`: enter or select information;
- `action`: change or request state;
- `decision`: choose a policy or branch;
- `output`: produce or communicate a result;
- `human`: obtain human judgment or approval.

The canonical event signature is `kind:type:target`. Consistent semantic names are therefore
important. Put per-run values in `value` or `data`; do not embed order numbers or customer
identifiers in `type`.

## Dataset rules

- Trace IDs must be unique.
- Event timestamps, when supplied, must be monotonically increasing.
- Strict induction requires all traces to have the same task name.
- Mark failures honestly. Failure paths are useful evidence, not invalid data.
- Remove secrets and unnecessary personal data before storage.
- Split training and held-out traces before tuning induction settings.

Generate the machine-readable schema using `taskprint schema trace`.
