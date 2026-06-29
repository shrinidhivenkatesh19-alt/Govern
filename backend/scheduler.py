"""SLA scheduler — auto-nudges and hard escalation."""
import asyncio
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends

from core import db, now_iso, get_current_user, logger
from notifications import create_notification
from email_service import send_assignment, send_nudge
from submissions import _pick_next_assignee

router = APIRouter()

AGENT_ACTOR = {"name": "GOVERN Agent", "designation": "Automated SLA", "role": "system"}


async def _send_email(coro) -> None:
    try:
        await coro
    except Exception as e:
        logger.error(f"SLA email send failed: {e!r}")


async def _resolve_assignee(item: dict):
    if item.get("assigned_user_id"):
        return await db.users.find_one(
            {"id": item["assigned_user_id"]}, {"_id": 0, "password_hash": 0}
        )
    role = item.get("reviewer_role")
    if role:
        return await _pick_next_assignee(item, role)
    return None


async def _fire_sla_notification(
    item: dict, sub_id: str, kind: str, msg: str, activity_additions: list
) -> None:
    assignee = await _resolve_assignee(item)
    if assignee:
        await create_notification(assignee["id"], sub_id, kind, f"SLA breach: {item['title']}", msg)
        await _send_email(send_nudge(assignee, item, AGENT_ACTOR, msg))
    else:
        logger.warning(f"SLA nudge skipped — no assignee for submission {sub_id}")
    activity_additions.append({
        "ts": now_iso(), "actor": "Agent", "actor_role": "system",
        "action": kind, "note": msg,
    })


def _calculate_deadline_progress(item: dict, now: datetime) -> float:
    try:
        created = datetime.fromisoformat(item["created_at"])
        deadline_str = item.get("deadline", "")
        deadline_dt = (
            datetime.fromisoformat(deadline_str + "T23:59:59+00:00")
            if "T" not in deadline_str else datetime.fromisoformat(deadline_str)
        )
        total = (deadline_dt - created).total_seconds()
        elapsed = (now - created).total_seconds()
        return elapsed / total if total > 0 else 1.0
    except Exception:
        return 0.0


async def _handle_hard_escalation(
    item: dict, sub_id: str, now: datetime, today: str,
    activity_additions: list, new_nudges: dict,
) -> None:
    next_role_map = {"reviewer": "marketing_lead", "marketing_lead": "vp", "vp": "vp", "ceo": "ceo"}
    current_role = item["reviewer_role"]
    new_role = next_role_map.get(current_role, current_role)
    elapsed_secs = (now - datetime.fromisoformat(item["stage_entered_at"])).total_seconds()
    durations = item.get("stage_durations", {}) or {}
    durations[item["status"]] = durations.get(item["status"], 0) + elapsed_secs

    if new_role != current_role:
        target: Optional[dict] = await _pick_next_assignee(item, new_role)
        target_name = target["name"] if target else f"any {new_role}"
        activity_additions.append({
            "ts": now_iso(), "actor": "Agent", "actor_role": "system",
            "action": "auto_escalated",
            "note": f"≥80% of timeline elapsed without decision; routed from {current_role} to {target_name}",
        })
        update_set: dict = {
            "status": "escalated", "reviewer_role": new_role,
            "stage_entered_at": now_iso(), "stage_durations": durations,
            "updated_at": now_iso(),
        }
        if target:
            update_set.update({
                "assigned_user_id": target["id"], "assigned_user_name": target["name"],
                "assigned_user_email": target.get("email"),
                "assigned_user_designation": target.get("designation", ""),
                "assigned_user_team": target.get("team", ""),
            })
            await create_notification(target["id"], sub_id, "auto_escalation",
                                      f"Auto-escalated to you: {item['title']}",
                                      f"Reached deadline threshold; previously with {current_role}")
            submitter = await db.users.find_one(
                {"id": item["submitter_id"]}, {"_id": 0, "password_hash": 0}
            )
            merged = {**item, **update_set, "id": sub_id}
            tl = merged.get("timeline") or {}
            await _send_email(send_assignment(
                target, merged, submitter or {}, tl.get("accept_by", ""),
            ))
        await db.submissions.update_one({"id": sub_id}, {"$set": update_set})
    else:
        activity_additions.append({
            "ts": now_iso(), "actor": "Agent", "actor_role": "system",
            "action": "auto_escalated",
            "note": "≥80% of timeline elapsed without decision (no higher role available)",
        })
    new_nudges["hard_escalation"] = today


async def run_sla_check() -> None:
    open_statuses = ["pending_acceptance", "in_progress", "under_review", "escalated"]
    items = await db.submissions.find({"status": {"$in": open_statuses}}).to_list(2000)
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    for item in items:
        sub_id = item["id"]
        tl = item.get("timeline") or {}
        last_nudges = item.get("auto_nudges_sent", {}) or {}
        new_nudges = dict(last_nudges)
        activity_additions: list = []

        if item["status"] == "pending_acceptance" and tl.get("accept_by") and today > tl["accept_by"]:
            if last_nudges.get("accept") != today:
                await _fire_sla_notification(
                    item, sub_id, "auto_nudge_accept",
                    f"Past accept-by date ({tl['accept_by']}). Reviewer has not accepted.",
                    activity_additions,
                )
                new_nudges["accept"] = today

        if item["status"] == "in_progress" and tl.get("review_by") and today > tl["review_by"]:
            if last_nudges.get("review") != today:
                await _fire_sla_notification(
                    item, sub_id, "auto_nudge_review",
                    f"Past review-by date ({tl['review_by']}). Decision pending.",
                    activity_additions,
                )
                new_nudges["review"] = today

        progress = _calculate_deadline_progress(item, now)

        if progress >= 0.8 and item["status"] in ("pending_acceptance", "in_progress", "under_review"):
            if not last_nudges.get("hard_escalation"):
                await _handle_hard_escalation(item, sub_id, now, today, activity_additions, new_nudges)

        if activity_additions or new_nudges != last_nudges:
            full_activity = item.get("activity", []) + activity_additions
            await db.submissions.update_one(
                {"id": sub_id},
                {"$set": {"activity": full_activity, "auto_nudges_sent": new_nudges, "updated_at": now_iso()}},
            )


async def sla_scheduler_loop() -> None:
    interval = int(os.environ.get("SLA_INTERVAL_SECONDS", "900"))
    await asyncio.sleep(20)
    while True:
        try:
            await run_sla_check()
        except Exception as e:
            logger.error(f"SLA loop error: {e}")
        await asyncio.sleep(interval)


@router.post("/scheduler/run")
async def manual_run_scheduler(user: dict = Depends(get_current_user)) -> dict:
    await run_sla_check()
    return {"ok": True}
