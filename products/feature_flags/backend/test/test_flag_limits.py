from posthog.test.base import BaseTest

from parameterized import parameterized

from posthog.models.team.extensions import get_or_create_team_extension

from products.feature_flags.backend.flag_limits import get_max_feature_flags_for_team
from products.feature_flags.backend.models.team_feature_flags_config import TeamFeatureFlagsConfig


class TestGetMaxFeatureFlagsForTeam(BaseTest):
    @parameterized.expand(
        [
            ("no_config_row", None, False, 2000),
            ("null_override", None, True, 2000),
            ("small_override_below_global", 1, True, 1),
            ("override_above_global", 5000, True, 5000),
        ]
    )
    def test_resolves_effective_limit(self, _name, override, has_row, expected_limit):
        if has_row:
            config = get_or_create_team_extension(self.team, TeamFeatureFlagsConfig)
            config.max_feature_flags_override = override
            config.save(update_fields=["max_feature_flags_override"])
        else:
            # Models a legacy team that predates this field, or any lookup that hasn't
            # lazily created the row yet: get_max_feature_flags_for_team must fall back to
            # the global default rather than raising on the missing row.
            TeamFeatureFlagsConfig.objects.filter(team=self.team).delete()

        with self.settings(MAX_FEATURE_FLAGS_PER_TEAM=2000):
            self.assertEqual(get_max_feature_flags_for_team(self.team.id), expected_limit)
