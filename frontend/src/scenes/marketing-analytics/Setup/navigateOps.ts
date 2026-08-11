import api from 'lib/api'
import { urls } from 'scenes/urls'
import {
    SetupSection,
    marketingAnalyticsLogic,
} from 'scenes/web-analytics/tabs/marketing-analytics/frontend/logic/marketingAnalyticsLogic'
import { marketingAnalyticsSettingsLogic } from 'scenes/web-analytics/tabs/marketing-analytics/frontend/logic/marketingAnalyticsSettingsLogic'
import type { ApplyOp } from 'scenes/web-analytics/tabs/marketing-analytics/frontend/logic/setupPlanLogic'

/** Perform an op the browser owns, returning whether it handled it.
 *
 * Lives in the view rather than in `setupPlanLogic`: these need the router and the
 * scene's own logics, and importing those into the plan logic drags the whole scene
 * dependency graph — sourceManagementLogic and friends — into everything that touches
 * a suggestion. The plan logic changes config; the view moves the user.
 *
 * Anything that leaves the product opens in a new tab. The user is midway through a
 * setup checklist, and navigating away to authorise an ad platform loses their place
 * in it. In-product destinations stay in this tab, because they're part of the task.
 */
export function runNavigateOp(op: ApplyOp): boolean {
    switch (op.op) {
        case 'open_oauth':
            window.open(
                api.integrations.authorizeUrl({
                    kind: op.kind as string,
                    next: window.location.pathname + window.location.search,
                }),
                '_blank',
                'noopener'
            )
            return true
        case 'open_source_wizard':
            window.open(
                urls.dataWarehouseSourceNew(op.kind as string, urls.marketingAnalyticsApp(), 'Marketing analytics'),
                '_blank',
                'noopener'
            )
            return true
        case 'open_settings':
            window.open(urls.settings(op.anchor as any, 'marketing-settings'), '_blank', 'noopener')
            return true
        case 'open_schemas':
            // The Schemas tab is a different product area with its own sync state —
            // a new tab keeps the setup checklist where the user left it.
            window.open(op.url as string, '_blank', 'noopener')
            return true
        case 'open_source_columns':
        case 'open_sources_section':
            // Findings that span platforms end here: every platform has its own row in
            // that section, which is the honest destination when one call can't fix
            // all of them.
            marketingAnalyticsLogic.actions.setSetupSection(SetupSection.SOURCES)
            return true
        case 'open_goal_editor':
            marketingAnalyticsLogic.actions.setSetupSection(SetupSection.CONVERSION_GOALS)
            marketingAnalyticsSettingsLogic.actions.setEditingConversionGoalId(op.conversion_goal_id as string)
            return true
        case 'open_mapping_editor':
            marketingAnalyticsSettingsLogic.actions.openIntegrationSettingsModal(
                op.integration as any,
                'mappings',
                op.raw_utm_value as string,
                (op.campaign_name as string) || ''
            )
            return true
        default:
            return false
    }
}
