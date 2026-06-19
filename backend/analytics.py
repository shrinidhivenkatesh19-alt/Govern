"""Analytics + dashboard router."""
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Depends

from core import db, get_current_user

router = APIRouter()


def _count_status_tier_type(items: list[dict]) -> tuple[dict, dict, dict, dict]:
    """Return by_status, by_tier, by_type, risk_flag_counts tallies."""
    by_status: dict = {}
    by_tier: dict = {}
    by_type: dict = {}
    risk_flag_counts: dict = {}
    for it in items:
        by_status[it["status"]] = by_status.get(it["status"], 0) + 1
        by_tier[it["chosen_tier"]] = by_tier.get(it["chosen_tier"], 0) + 1
        content_key = it.get("request_type") or it.get("content_type", "unknown")
        by_type[content_key] = by_type.get(content_key, 0) + 1
        for flag in (it.get("score_result") or {}).get("risk_flags", []):
            risk_flag_counts[flag] = risk_flag_counts.get(flag, 0) + 1
    return by_status, by_tier, by_type, risk_flag_counts


def _collect_idle_stats(items: list[dict], now: datetime) -> tuple[int, list[dict]]:
    """Return count and breakdown of submissions idle >= 24h."""
    idle_count = 0
    idle_breakdown: list[dict] = []
    active_statuses = {"under_review", "escalated", "revision_requested", "pending_acceptance", "in_progress"}
    for it in items:
        entered = datetime.fromisoformat(it["stage_entered_at"])
        idle_hours = (now - entered).total_seconds() / 3600
        if it["status"] in active_statuses and idle_hours >= 24:
            idle_count += 1
            idle_breakdown.append({
                "id": it["id"],
                "title": it["title"],
                "status": it["status"],
                "idle_hours": round(idle_hours, 1),
                "reviewer_role": it.get("reviewer_role"),
                "assigned_user_name": it.get("assigned_user_name"),
            })
    return idle_count, idle_breakdown


def _collect_stage_stats(items: list[dict], now: datetime) -> tuple[dict, dict, dict]:
    """Return stage_seconds totals, stage_counts, and bottleneck_reviewers idle hours."""
    stage_seconds: dict = {}
    stage_counts: dict = {}
    bottleneck_reviewers: dict = {}
    bottleneck_statuses = {"under_review", "escalated", "in_progress", "pending_acceptance"}
    for it in items:
        for stage, secs in (it.get("stage_durations") or {}).items():
            stage_seconds[stage] = stage_seconds.get(stage, 0) + secs
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
        if it["status"] in bottleneck_statuses:
            entered = datetime.fromisoformat(it["stage_entered_at"])
            idle_hours = (now - entered).total_seconds() / 3600
            role = it.get("reviewer_role", "unknown")
            bottleneck_reviewers[role] = bottleneck_reviewers.get(role, 0) + idle_hours
    return stage_seconds, stage_counts, bottleneck_reviewers


def _calculate_avg_approval_hours(items: list[dict]) -> tuple[float, list[dict]]:
    """Return average approval time in hours and the list of completed items."""
    completed = [it for it in items if it["status"] in ("approved", "live")]
    if not completed:
        return 0, completed
    total_secs = sum(
        (datetime.fromisoformat(it["updated_at"]) - datetime.fromisoformat(it["created_at"])).total_seconds()
        for it in completed
    )
    return round(total_secs / len(completed) / 3600, 2), completed


@router.get("/dashboard/stats")
async def dashboard_stats(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Lightweight stats for the Overview page — available to all authenticated users."""
    items = await db.submissions.find({}, {"_id": 0}).to_list(2000)
    by_status: dict = {}
    completed = []
    for it in items:
        by_status[it["status"]] = by_status.get(it["status"], 0) + 1
        if it["status"] in ("approved", "live"):
            completed.append(it)
    if completed:
        secs = sum(
            (datetime.fromisoformat(it["updated_at"]) - datetime.fromisoformat(it["created_at"])).total_seconds()
            for it in completed
        )
        avg_approval_hours = round(secs / len(completed) / 3600, 2)
    else:
        avg_approval_hours = 0
    return {
        "total": len(items),
        "by_status": by_status,
        "avg_approval_hours": avg_approval_hours,
        "completed_count": len(completed),
    }


@router.get("/analytics/overview")
async def analytics_overview(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    if user["role"] not in ("vp", "ceo"):
        raise HTTPException(status_code=403, detail="Governance analytics restricted to VP and CEO roles")
    items = await db.submissions.find({}, {"_id": 0}).to_list(2000)
    now = datetime.now(timezone.utc)

    by_status, by_tier, by_type, risk_flag_counts = _count_status_tier_type(items)
    idle_count, idle_breakdown = _collect_idle_stats(items, now)
    stage_seconds, stage_counts, bottleneck_reviewers = _collect_stage_stats(items, now)
    avg_approval_hours, completed = _calculate_avg_approval_hours(items)

    avg_stage_hours = {
        k: round(v / max(stage_counts.get(k, 1), 1) / 3600, 2)
        for k, v in stage_seconds.items()
    }

    return {
        "total": len(items),
        "by_status": by_status,
        "by_tier": by_tier,
        "by_type": by_type,
        "risk_flag_counts": risk_flag_counts,
        "idle_count": idle_count,
        "idle_breakdown": sorted(idle_breakdown, key=lambda x: -x["idle_hours"])[:10],
        "avg_stage_hours": avg_stage_hours,
        "avg_approval_hours": avg_approval_hours,
        "bottleneck_reviewers": {k: round(v, 1) for k, v in bottleneck_reviewers.items()},
        "completed_count": len(completed),
    }
