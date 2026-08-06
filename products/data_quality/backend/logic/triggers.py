"""Gates the event-driven triggers consult before starting a check suite.

Called from other products' pipelines (via inversion hooks or facade functions), so they must be
cheap, never raise, and answer the do-nothing value when the product flag is off.
"""

import uuid

from ..facade.contracts import QUALITY_AUDIT_GATE, QUALITY_AUDIT_SKIP, QUALITY_AUDIT_WARN
from ..facade.enums import CheckSeverity
from .flags import is_data_quality_checks_enabled_for_team_id


def source_sync_checks_needed(team_id: int, table_id: "str | uuid.UUID") -> bool:
    """Whether a completed sync of this table should start a check suite."""
    # Deferred so this module imports before the app registry is ready.
    from ..models import DataQualityCheck  # noqa: PLC0415

    if not is_data_quality_checks_enabled_for_team_id(team_id):
        return False
    return DataQualityCheck.objects.for_team(team_id).filter(table_id=table_id, enabled=True, deleted=False).exists()


def materialization_audit_mode(team_id: int, saved_query_id: "str | uuid.UUID") -> str:
    """How a materialization of this view should treat its checks.

    ``gate`` requires both the team setting and at least one error-severity check: warn-severity
    checks can never block a publish, so gating on them would only add latency.
    """
    # Deferred so this module imports before the app registry is ready.
    from ..models import DataQualityCheck, TeamDataQualityConfig  # noqa: PLC0415

    if not is_data_quality_checks_enabled_for_team_id(team_id):
        return QUALITY_AUDIT_SKIP
    checks = DataQualityCheck.objects.for_team(team_id).filter(
        saved_query_id=saved_query_id, enabled=True, deleted=False
    )
    if not checks.exists():
        return QUALITY_AUDIT_SKIP
    config = TeamDataQualityConfig.objects.filter(team_id=team_id).first()
    gate_on = config is not None and config.gate_materialization_on_checks
    if gate_on and checks.filter(severity=CheckSeverity.ERROR).exists():
        return QUALITY_AUDIT_GATE
    return QUALITY_AUDIT_WARN
