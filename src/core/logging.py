# Single logging configuration owner for the whole application.
#
# Rules for this module:
#   * It is the ONLY place that calls logging.basicConfig / configures handlers.
#     Other modules obtain a logger with logging.getLogger(__name__) and pass
#     correlation fields via `extra=` or the context variables below.
#   * Every emitted line is redacted so credentials, request bodies, provider
#     bodies, and database parameter values never reach a log sink.
#
# Correlation IDs are carried in ContextVars so a request handler or a worker
# task can attach them once and have every subsequent log line include them.
import logging
import re
from contextlib import contextmanager
from contextvars import ContextVar

from src.core.config import LOG_LEVEL

REDACTED = "***redacted***"

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
ticket_id_var: ContextVar[str] = ContextVar("ticket_id", default="-")
analysis_result_id_var: ContextVar[str] = ContextVar("analysis_result_id", default="-")
job_id_var: ContextVar[str] = ContextVar("job_id", default="-")
attempt_id_var: ContextVar[str] = ContextVar("attempt_id", default="-")

# Correlation fields carried on every record. The ContextVar is only a fallback:
# an explicit value passed with ``extra=`` wins, so a caller-supplied ID is
# never overwritten with the context default ``"-"``.
_CORRELATION_FIELDS = {
    "request_id": request_id_var,
    "ticket_id": ticket_id_var,
    "analysis_result_id": analysis_result_id_var,
    "job_id": job_id_var,
    "attempt_id": attempt_id_var,
}


@contextmanager
def correlation_context(**ids: str | None):
    """Bind correlation IDs for the duration of a request or job, then clear.

    Any field not supplied keeps its previous value. Fields are always restored
    on exit so a value never leaks into the next request or job.
    """
    tokens = []
    for name, value in ids.items():
        variable = _CORRELATION_FIELDS.get(name)
        if variable is None or value is None:
            continue
        tokens.append((variable, variable.set(value)))
    try:
        yield
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)

# Value patterns that look like secrets wherever they appear in a message.
_SECRET_PATTERN = re.compile(
    r"(?i)("
    r"bearer\s+[A-Za-z0-9._\-]+"
    r"|(?:api[_-]?key|token|secret|password|passwd)\s*[:=]\s*[^\s,;\"']+"
    r"|eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"  # JWT
    r")"
)

# Field names whose values are redacted even when passed through `extra=`.
_SENSITIVE_FIELDS = frozenset(
    {
        "password",
        "refresh_token",
        "access_token",
        "authorization",
        "api_key",
        "secret",
        "request_body",
        "provider_body",
        "db_params",
    }
)


def redact_secrets(value: str) -> str:
    """Replace secret-looking substrings with :data:`REDACTED`."""
    if not isinstance(value, str) or not value:
        return value
    return _SECRET_PATTERN.sub(REDACTED, value)


class RedactionFilter(logging.Filter):
    """Attach correlation IDs and neutralize sensitive `extra` fields."""

    def filter(self, record: logging.LogRecord) -> bool:
        for name, variable in _CORRELATION_FIELDS.items():
            supplied = getattr(record, name, None)
            if supplied in (None, "", "-"):
                setattr(record, name, variable.get())
        for field in _SENSITIVE_FIELDS:
            if hasattr(record, field):
                setattr(record, field, REDACTED)
        return True


class RedactingFormatter(logging.Formatter):
    """Formatter that redacts the fully rendered line.

    Redacting the rendered output (instead of mutating ``record.args``) keeps
    ``%d``/``%s`` formatting intact while still removing secrets.
    """

    def format(self, record: logging.LogRecord) -> str:
        return redact_secrets(super().format(record))


LOG_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s "
    "[request=%(request_id)s ticket=%(ticket_id)s "
    "analysis=%(analysis_result_id)s job=%(job_id)s attempt=%(attempt_id)s] "
    "%(message)s"
)

_configured = False


def setup_logging() -> None:
    """Configure logging exactly once and install redaction + correlation."""
    global _configured
    if not _configured:
        logging.basicConfig(level=LOG_LEVEL, format=LOG_FORMAT)
        _configured = True

    redaction = RedactionFilter()
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(existing, RedactionFilter) for existing in handler.filters):
            handler.addFilter(redaction)
        # Replace any formatter so redaction cannot be bypassed by a formatter
        # a host configured before us.
        if not isinstance(handler.formatter, RedactingFormatter):
            handler.setFormatter(RedactingFormatter(LOG_FORMAT))
