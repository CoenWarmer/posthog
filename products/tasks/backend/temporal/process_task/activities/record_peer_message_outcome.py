from dataclasses import dataclass

import structlog
from temporalio import activity

from posthog.temporal.common.utils import close_db_connections

# Re-exported for the workflows' failure-isolation gate, so workflow code takes the
# peer-context check from one place without importing the storage-heavy service.
from products.tasks.backend.logic.services.peer_messages import peer_message_id_from_context

__all__ = [
    "RecordPeerMessageOutcomeInput",
    "peer_message_id_from_context",
    "record_peer_message_outcome",
]

logger = structlog.get_logger(__name__)


@dataclass
class RecordPeerMessageOutcomeInput:
    peer_message_id: str
    outcome: str
    failure_phase: str = ""
    failure_detail: str = ""


@activity.defn
@close_db_connections
def record_peer_message_outcome(input: RecordPeerMessageOutcomeInput) -> bool:
    """Terminalize a peer message row from the workflow's failure-isolation path.

    Peer-message delivery failures never touch the recipient run's completion state;
    this is how the workflow reports them instead. Idempotent: only non-terminal rows
    transition, so racing the delivery activity's own bookkeeping is harmless. Covers
    the failure class the delivery activity can't record itself (worker death,
    heartbeat/start-to-close timeout — the activity code never ran to completion).
    """
    from products.tasks.backend.logic.services.peer_messages import (  # noqa: PLC0415 — keep storage deps lazy
        mark_peer_message_outcome,
    )

    updated = mark_peer_message_outcome(
        input.peer_message_id,
        input.outcome,
        failure_phase=input.failure_phase,
        failure_detail=input.failure_detail,
    )
    logger.info(
        "peer_message_outcome_recorded",
        peer_message_id=input.peer_message_id,
        outcome=input.outcome,
        failure_phase=input.failure_phase,
        already_terminal=not updated,
    )
    return updated
