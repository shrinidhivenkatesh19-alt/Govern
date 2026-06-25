"""Stats & overview aggregation endpoints — powers the Governance dashboard charts."""
from fastapi import APIRouter, Depends
from core import db, get_current_user

router = APIRouter()


@router.get("/stats/overview")
async def get_overview(user: dict = Depends(get_current_user)):
    """
    Returns counts and breakdowns used by the Overview and Governance chart pages.
    All numbers are scoped to the current user's org (all users for now — add org_id filter later).
    """
    pipeline_totals = [
        {"$match": {"is_deleted": {"$ne": True}}},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
        }},
    ]
    status_counts = {}
    async for doc in db.submissions.aggregate(pipeline_totals):
        status_counts[doc["_id"]] = doc["count"]

    total = sum(status_counts.values())
    pending = status_counts.get("pending_acceptance", 0) + status_counts.get("under_review", 0)
    approved = status_counts.get("approved", 0)
    rejected = status_counts.get("rejected", 0)
    in_progress = status_counts.get("in_progress", 0)

    # Tier breakdown
    tier_pipeline = [
        {"$match": {"is_deleted": {"$ne": True}}},
        {"$group": {"_id": "$recommended_tier", "count": {"$sum": 1}}},
    ]
    tier_counts = {}
    async for doc in db.submissions.aggregate(tier_pipeline):
        tier_counts[doc["_id"]] = doc["count"]

    # Risk flag breakdown (flatten arrays)
    risk_pipeline = [
        {"$match": {"is_deleted": {"$ne": True}, "risk_flags": {"$exists": True, "$ne": []}}},
        {"$unwind": "$risk_flags"},
        {"$group": {"_id": "$risk_flags", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    risk_counts = {}
    async for doc in db.submissions.aggregate(risk_pipeline):
        risk_counts[doc["_id"]] = doc["count"]

    # Submissions over time (last 30 days, by day)
    trend_pipeline = [
        {"$match": {"is_deleted": {"$ne": True}}},
        {"$project": {
            "day": {"$dateToString": {"format": "%Y-%m-%d", "date": {"$toDate": "$created_at"}}},
            "status": 1,
        }},
        {"$group": {
            "_id": "$day",
            "total": {"$sum": 1},
            "approved": {"$sum": {"$cond": [{"$eq": ["$status", "approved"]}, 1, 0]}},
            "rejected": {"$sum": {"$cond": [{"$eq": ["$status", "rejected"]}, 1, 0]}},
        }},
        {"$sort": {"_id": 1}},
        {"$limit": 30},
    ]
    trend = []
    async for doc in db.submissions.aggregate(trend_pipeline):
        trend.append({
            "date": doc["_id"],
            "total": doc["total"],
            "approved": doc["approved"],
            "rejected": doc["rejected"],
        })

    # Average scores
    score_pipeline = [
        {"$match": {"is_deleted": {"$ne": True}, "overall_score": {"$exists": True}}},
        {"$group": {
            "_id": None,
            "avg_overall": {"$avg": "$overall_score"},
            "avg_brand": {"$avg": "$brand_alignment_score"},
            "avg_completeness": {"$avg": "$completeness_score"},
        }},
    ]
    avg_scores = {"avg_overall": 0, "avg_brand": 0, "avg_completeness": 0}
    async for doc in db.submissions.aggregate(score_pipeline):
        avg_scores = {
            "avg_overall": round(doc.get("avg_overall") or 0, 1),
            "avg_brand": round(doc.get("avg_brand") or 0, 1),
            "avg_completeness": round(doc.get("avg_completeness") or 0, 1),
        }

    return {
        "totals": {
            "total": total,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "in_progress": in_progress,
        },
        "tier_breakdown": tier_counts,
        "risk_breakdown": risk_counts,
        "trend": trend,
        "avg_scores": avg_scores,
    }


@router.get("/stats/queue")
async def get_queue(user: dict = Depends(get_current_user)):
    """
    Returns submissions pending approval — drives the Approval Queue page.
    Sorted by created_at descending.
    """
    cursor = db.submissions.find(
        {
            "is_deleted": {"$ne": True},
            "status": {"$in": ["pending_acceptance", "under_review", "escalated"]},
        },
        {"_id": 0, "grid_id": 0},
    ).sort("created_at", -1)

    items = []
    async for doc in cursor:
        items.append(doc)

    return {"items": items, "count": len(items)}