"""Periodic RQ schedule for recovery-oriented background work."""

from rq import cron

from src.core import (
    ANALYSIS_RECONCILIATION_BATCH_SIZE,
    ANALYSIS_RECONCILIATION_INTERVAL_SECONDS,
    OVERDUE_SCAN_BATCH_SIZE,
    OVERDUE_SCAN_INTERVAL_SECONDS,
    ROUTING_RECONCILIATION_BATCH_SIZE,
    ROUTING_RECONCILIATION_INTERVAL_SECONDS,
)
from src.jobs.queue import QUEUE_NAME, ROUTING_QUEUE_NAME
from src.jobs.service import (
    ANALYSIS_FAILURE_TTL_SECONDS,
    ANALYSIS_JOB_TIMEOUT_SECONDS,
    ANALYSIS_RESULT_TTL_SECONDS,
    ROUTING_FAILURE_TTL_SECONDS,
    ROUTING_JOB_TIMEOUT_SECONDS,
    ROUTING_RESULT_TTL_SECONDS,
    reconcile_analysis_results,
    route_waiting_tickets,
)
from src.jobs.tasks import scan_overdue_tickets


ROUTING_RECONCILIATION_SCHEDULE = cron.register(
    route_waiting_tickets,
    queue_name=ROUTING_QUEUE_NAME,
    kwargs={"batch_size": ROUTING_RECONCILIATION_BATCH_SIZE},
    interval=ROUTING_RECONCILIATION_INTERVAL_SECONDS,
    job_timeout=ROUTING_JOB_TIMEOUT_SECONDS,
    result_ttl=ROUTING_RESULT_TTL_SECONDS,
    failure_ttl=ROUTING_FAILURE_TTL_SECONDS,
)


OVERDUE_SCAN_SCHEDULE = cron.register(
    scan_overdue_tickets,
    queue_name=ROUTING_QUEUE_NAME,
    kwargs={"batch_size": OVERDUE_SCAN_BATCH_SIZE},
    interval=OVERDUE_SCAN_INTERVAL_SECONDS,
    job_timeout=ROUTING_JOB_TIMEOUT_SECONDS,
    result_ttl=ROUTING_RESULT_TTL_SECONDS,
    failure_ttl=ROUTING_FAILURE_TTL_SECONDS,
)


ANALYSIS_RECONCILIATION_SCHEDULE = cron.register(
    reconcile_analysis_results,
    queue_name=QUEUE_NAME,
    kwargs={"batch_size": ANALYSIS_RECONCILIATION_BATCH_SIZE},
    interval=ANALYSIS_RECONCILIATION_INTERVAL_SECONDS,
    job_timeout=ANALYSIS_JOB_TIMEOUT_SECONDS,
    result_ttl=ANALYSIS_RESULT_TTL_SECONDS,
    failure_ttl=ANALYSIS_FAILURE_TTL_SECONDS,
)
