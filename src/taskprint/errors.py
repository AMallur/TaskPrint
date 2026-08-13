"""Stable public exception hierarchy for Taskprint."""


class TaskprintError(Exception):
    """Base class for all expected Taskprint failures."""


class TraceValidationError(TaskprintError):
    """A trace set cannot be used for induction."""


class WorkflowValidationError(TaskprintError):
    """A workflow is structurally invalid."""


class HandlerNotFoundError(TaskprintError):
    """No executable handler exists for a workflow action."""


class ExecutionError(TaskprintError):
    """A workflow action failed after applying its runtime policy."""


class RoutingError(TaskprintError):
    """A router returned an invalid transition."""


class SchemaVersionError(TaskprintError):
    """An artifact uses an unsupported schema version."""
