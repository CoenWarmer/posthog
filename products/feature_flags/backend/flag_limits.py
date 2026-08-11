from django.conf import settings

from products.feature_flags.backend.models.team_feature_flags_config import TeamFeatureFlagsConfig

# Ceiling on a staff-granted override. The global default exists to bound the flag-definitions
# blob and the flags service's in-memory flag set, so an unbounded grant would reintroduce the
# memory risk the limit was added for. Ten times the current default leaves real headroom while
# making a fat-fingered extra zero impossible.
MAX_FEATURE_FLAGS_OVERRIDE_CEILING = 20_000


def resolve_max_feature_flags(override: int | None) -> int:
    """Effective flag-count cap for a team, given its stored override."""
    return override if override is not None else settings.MAX_FEATURE_FLAGS_PER_TEAM


def get_max_feature_flags_for_team(team_id: int) -> int:
    # A missing config row and a row holding a null override both mean "no override", and
    # .first() returns None for both.
    #
    # This reads the raw team, while check_flag_limits_for_team counts flags through
    # FeatureFlag.objects (a RootTeamManager), which scopes the count to the project root. The
    # two agree only while Team.parent_team is unset, which it is everywhere today. If
    # environment teams are ever populated, an override and the flag count it is compared
    # against would come from different teams, and both this lookup and the write side in
    # staff_team_config.py need to move to the project root together.
    override = (
        TeamFeatureFlagsConfig.objects.filter(team_id=team_id)
        .values_list("max_feature_flags_override", flat=True)
        .first()
    )
    return resolve_max_feature_flags(override)
