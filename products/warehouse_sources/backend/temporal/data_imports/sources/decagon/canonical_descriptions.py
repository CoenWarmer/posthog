from products.warehouse_sources.backend.temporal.data_imports.sources.common.canonical_descriptions import (
    CanonicalDescriptions,
)

CANONICAL_DESCRIPTIONS: CanonicalDescriptions = {
    "conversations": {
        "description": (
            "A conversation between a user and a Decagon AI agent, including every message, "
            "the customer satisfaction rating, tags, and metadata attached to the conversation."
        ),
        "docs_url": "https://docs.decagon.ai/api/exporting-conversations",
        "columns": {
            "conversation_id": "Unique identifier for the conversation.",
            "user_id": "Identifier of the end user who had the conversation.",
            "created_at": "Timestamp at which the conversation was created.",
            "updated_at": "Timestamp at which the conversation was last updated. Advances whenever the conversation receives new messages.",
            "destination": "Channel the conversation was handled on (e.g. AI).",
            "messages": "All messages in the conversation; each message has text, a role (USER or AI), and a created_at timestamp.",
            "csat_rating": "Customer satisfaction rating the user gave the conversation, if any.",
            "tags": "Tags applied to the conversation; each tag has a name and a level.",
            "metadata": "Custom metadata attached to the conversation (e.g. user attributes).",
        },
    },
    "team_members": {
        "description": (
            "A member of the Decagon team, one row per user including pending invites. "
            "Resolves the user ids referenced by other Decagon tables to a person."
        ),
        "docs_url": "https://docs.decagon.ai/api-reference/getting-started",
        "columns": {
            "id": "Unique identifier for the team member.",
            "email": "Email address of the team member.",
            "access": "Access level of the team member: viewer, QA, or admin.",
        },
    },
    "watchtower_jobs": {
        "description": (
            "A Watchtower QA/evaluation job, including the rubric and configuration needed to "
            "interpret its quality scoring."
        ),
        "docs_url": "https://docs.decagon.ai/api-reference/getting-started",
        "columns": {
            "id": "Unique identifier for the job.",
            "name": "Name of the job.",
            "description": "Description of the job.",
            "rubric": "Rubric the job evaluates against, as free-form JSON.",
            "rubric_type": "Type of the rubric.",
            "prompt": "Prompt the job runs, as free-form JSON.",
            "outputs": "Outputs the job produces, as free-form JSON.",
            "config": "Configuration of the job, as free-form JSON.",
            "created_at": "Timestamp at which the job was created.",
            "updated_at": "Timestamp at which the job was last updated.",
            "last_run_at": "Timestamp at which the job last ran.",
            "status": "Status of the job.",
        },
    },
}
