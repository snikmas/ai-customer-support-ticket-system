from src.constants import logger
from src.jobs import route_waiting_tickets


def dispatch_waiting_tickets_after_capacity_event(
    event_name: str,
    entity_id: str,
) -> None:
    """Best-effort event trigger; reconciliation remains the safety net."""
    try:
        result = route_waiting_tickets()
    except Exception:
        logger.exception(
            "Capacity event routing dispatch failed",
            extra={"capacity_event": event_name, "entity_id": entity_id},
        )
        return

    logger.info(
        "Capacity event routing dispatch completed",
        extra={
            "capacity_event": event_name,
            "entity_id": entity_id,
            **result,
        },
    )
