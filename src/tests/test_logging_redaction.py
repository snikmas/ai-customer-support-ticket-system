"""Redaction must remove synthetic secret sentinels from log output."""

import io
import logging

from src.core.logging import (
    REDACTED,
    RedactingFormatter,
    RedactionFilter,
    analysis_result_id_var,
    correlation_context,
    redact_secrets,
    request_id_var,
    ticket_id_var,
)


def test_redact_secrets_removes_bearer_and_assigned_values():
    sentinel = "SENTINEL-9f3a2b7c4d"
    text = (
        f"Authorization: Bearer {sentinel} "
        f"api_key={sentinel} password={sentinel} "
        "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJzeW50aGV0aWMifQ.c2lnbmF0dXJl"
    )
    redacted = redact_secrets(text)
    assert sentinel not in redacted
    assert "eyJhbGciOiJSUzI1NiJ9" not in redacted
    assert REDACTED in redacted


def test_log_records_are_redacted_and_carry_correlation_ids():
    sentinel = "SENTINEL-abc123def456"
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingFormatter("%(message)s request=%(request_id)s"))
    handler.addFilter(RedactionFilter())

    logger = logging.getLogger("redaction-test")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    token = request_id_var.set("req-synthetic-id")
    try:
        logger.info("login failed password=%s bearer %s", sentinel, sentinel)
    finally:
        request_id_var.reset(token)

    output = stream.getvalue()
    assert sentinel not in output
    assert "req-synthetic-id" in output


def test_sensitive_extra_fields_are_replaced():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingFormatter("%(message)s api_key=%(api_key)s"))
    handler.addFilter(RedactionFilter())

    logger = logging.getLogger("redaction-extra-test")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    logger.info("provider call", extra={"api_key": "SENTINEL-key-value"})
    assert "SENTINEL-key-value" not in stream.getvalue()


def test_filter_preserves_supplied_correlation_ids():
    record = logging.LogRecord("t", logging.INFO, "", 1, "done", (), None)
    record.ticket_id = "ticket-demo"
    record.job_id = "job-demo"
    record.analysis_result_id = "analysis-demo"

    RedactionFilter().filter(record)

    assert record.ticket_id == "ticket-demo"
    assert record.job_id == "job-demo"
    assert record.analysis_result_id == "analysis-demo"
    assert record.request_id == "-"


def test_correlation_context_sets_and_clears_ids():
    assert ticket_id_var.get() == "-"
    with correlation_context(ticket_id="ticket-ctx", job_id="job-ctx"):
        assert ticket_id_var.get() == "ticket-ctx"
    # The value must not leak into the next request or job.
    assert ticket_id_var.get() == "-"


def test_worker_boundary_binds_and_clears_analysis_correlation(monkeypatch):
    from src.jobs import tasks as jobs_tasks

    seen = {}

    def fake_attempt(analysis_result_id):
        seen["during"] = analysis_result_id_var.get()
        return {}

    monkeypatch.setattr(jobs_tasks, "_analyze_analysis_result", fake_attempt)

    jobs_tasks.analyze_analysis_result("result-synthetic")

    assert seen["during"] == "result-synthetic"
    assert analysis_result_id_var.get() == "-"


def test_exception_message_is_redacted():
    sentinel = "SENTINEL-exc-1234"
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingFormatter("%(message)s"))
    handler.addFilter(RedactionFilter())

    logger = logging.getLogger("redaction-exception-test")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    try:
        raise ValueError(f"provider rejected api_key={sentinel}")
    except ValueError:
        logger.exception("analysis failed")

    assert sentinel not in stream.getvalue()
