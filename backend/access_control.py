"""Who can see which submissions — shared by list/get endpoints and analytics."""
from typing import Any

ACTIVE_STATUSES = [
    "pending_acceptance",
    "in_progress",
    "under_review",
    "escalated",
    "revision_requested",
]


def submission_visibility_query(user: dict) -> dict[str, Any]:
    """
    MongoDB filter: submissions visible to this user in queue / overview / analytics.
    Users always see items they submitted or are currently assigned to.
    Role-based expansions follow approval-tier workflow rules.
    """
    uid = user["id"]
    role = user["role"]

    clauses: list[dict[str, Any]] = [
        {"submitter_id": uid},
        {"assigned_user_id": uid},
    ]

    if role in ("reviewer", "marketing_lead", "vp", "ceo"):
        # Unassigned pool for this role only (not broadcast to other roles)
        clauses.append({
            "reviewer_role": role,
            "assigned_user_id": None,
            "status": {"$in": ACTIVE_STATUSES},
        })

    if role == "vp":
        clauses.append({
            "chosen_tier": "ceo_required",
            "status": {"$in": ACTIVE_STATUSES},
        })

    if role == "ceo":
        clauses.append({
            "$or": [
                {"chosen_tier": "ceo_required"},
                {"reviewer_role": "ceo"},
            ],
            "status": {"$in": ACTIVE_STATUSES},
        })

    return {"$or": clauses}


def can_view_submission(user: dict, item: dict) -> bool:
    """True if this user is allowed to open a single submission."""
    uid = user["id"]
    if item.get("submitter_id") == uid or item.get("assigned_user_id") == uid:
        return True

    role = user["role"]
    status = item.get("status", "")
    active = status in ACTIVE_STATUSES

    if not active:
        # Completed items: only submitter or someone in the chain who was assigned
        return item.get("submitter_id") == uid or item.get("assigned_user_id") == uid

    if role in ("reviewer", "marketing_lead", "vp", "ceo"):
        if item.get("reviewer_role") == role and not item.get("assigned_user_id"):
            return True

    if role == "vp" and item.get("chosen_tier") == "ceo_required":
        return True

    if role == "ceo" and (
        item.get("chosen_tier") == "ceo_required" or item.get("reviewer_role") == "ceo"
    ):
        return True

    return False
