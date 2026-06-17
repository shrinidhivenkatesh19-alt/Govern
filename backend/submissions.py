"""Submissions router — create, list, get, transitions (accept/approve/forward/escalate/etc.)."""
from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, HTTPException, Depends

from core import db, now_iso, get_current_user, DECISION_ALLOWED_FROM, MAX_CHAIN_DEPTH
from models import (
    SubmissionCreate, AcceptIn, ActionIn, RevisionIn, EscalateIn,
    ApproveForwardIn, TimelineProposal, Tier, SubmissionStatus,
)
from notifications import create_notification, notify_role

router = APIRouter()


# ---------------- helpers ----------------
def _initial_status_for_tier(tier: Tier) -> SubmissionStatus:
    return "approved" if tier == "auto_approve" else "pending_acceptance"


def _reviewer_role_for_tier(tier: Tier) -> str:
    return {"auto_approve": "system", "product_only": "reviewer", "ceo_required": "vp"}[tier]


def _annotate(item: dict) -> dict:
    """Compute SLA / idle / timeline-breach flags on a submission."""
    now = datetime.now(timezone.utc)
    entered = datetime.fromisoformat(item["stage_entered_at"])
    item["idle_hours"] = round((now - entered).total_seconds() / 3600, 1)
    item["idle_days"] = round(item["idle_hours"] / 24, 2)

    tl = item.get("timeline") or {}
    today = now.date().isoformat()

    overdue = {}
    if tl:
        try:
            overdue["accept"] = item["status"] == "pending_acceptance" and tl.get("accept_by") and today > tl["accept_by"]
            overdue["review"] = item["status"] == "in_progress" and tl.get("review_by") and today > tl["review_by"]
            overdue["approve"] = (
                item["status"] in ("in_progress", "pending_acceptance", "under_review", "escalated")
                and tl.get("approve_by") and today > tl["approve_by"]
            )
        except Exception:
            overdue = {}
    item["timeline_overdue"] = overdue
    item["any_overdue"] = bool(overdue.get("accept") or overdue.get("review") or overdue.get("approve"))

    try:
        created = datetime.fromisoformat(item["created_at"])
        deadline_str = item.get("deadline", "")
        deadline_dt = (
            datetime.fromisoformat(deadline_str + "T23:59:59+00:00")
            if "T" not in deadline_str else datetime.fromisoformat(deadline_str)
        )
        total = (deadline_dt - created).total_seconds()
        elapsed = (now - created).total_seconds()
        item["deadline_progress"] = round(min(max(elapsed / total, 0), 1), 3) if total > 0 else 1.0
    except Exception:
        item["deadline_progress"] = 0.0

    item["needs_nudge"] = item["any_overdue"] and item["status"] in ("pending_acceptance", "in_progress", "under_review", "escalated")
    item["needs_escalation"] = item["deadline_progress"] >= 0.8 and item["status"] in ("pending_acceptance", "in_progress", "under_review")
    return item


async def _pick_next_assignee(item: dict, next_role: str) -> Optional[dict]:
    """Pick a specific user for the next role, preferring same team."""
    current_team = (item.get("assigned_user_team") or "").strip()
    candidates = await db.users.find({"role": next_role}).to_list(100)
    if not candidates:
        return None
    if current_team:
        same_team = [c for c in candidates if (c.get("team") or "").strip() == current_team]
        if same_team:
            return same_team[0]
    return candidates[0]


async def _transition(sub_id: str, new_status: str, actor: dict, action: str, note: str):
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Submission not found")
    now = datetime.now(timezone.utc)
    entered = datetime.fromisoformat(item["stage_entered_at"])
    elapsed = (now - entered).total_seconds()
    durations = item.get("stage_durations", {}) or {}
    durations[item["status"]] = durations.get(item["status"], 0) + elapsed
    activity = item.get("activity", [])
    activity.append({
        "ts": now.isoformat(),
        "actor": actor["name"],
        "actor_role": actor["role"],
        "action": action,
        "note": note or "",
    })
    await db.submissions.update_one(
        {"id": sub_id},
        {"$set": {
            "status": new_status,
            "stage_entered_at": now.isoformat(),
            "stage_durations": durations,
            "activity": activity,
            "updated_at": now.isoformat(),
        }},
    )
    return await db.submissions.find_one({"id": sub_id}, {"_id": 0})


# ---------------- routes ----------------
@router.post("/submissions")
async def create_submission(body: SubmissionCreate, user: dict = Depends(get_current_user)):
    sub_id = str(uuid.uuid4())
    status_val = _initial_status_for_tier(body.chosen_tier)
    suggested_role = _reviewer_role_for_tier(body.chosen_tier)
    now = now_iso()

    assignee = await db.users.find_one({"id": body.assigned_user_id}, {"_id": 0, "password_hash": 0})
    if not assignee and status_val != "approved":
        raise HTTPException(status_code=400, detail="Assigned user not found")

    activity = [{
        "ts": now, "actor": user["name"], "actor_role": user["role"], "action": "submitted",
        "note": f"Submitted as {body.chosen_tier}" + (f"; assigned to {assignee['name']}" if assignee else "; auto-approved"),
    }]
    if status_val == "approved":
        activity.append({"ts": now, "actor": "Agent", "actor_role": "system", "action": "auto_approved", "note": "Routine content, auto-approved by agent"})

    doc = {
        "id": sub_id,
        "title": body.title,
        "request_type": body.request_type,
        "content_type": body.request_type,
        "brief": body.brief,
        "content": body.content,
        "deadline": body.deadline,
        "score_result": body.score_result.model_dump(),
        "chosen_tier": body.chosen_tier,
        "reviewer_role": (assignee["role"] if assignee else suggested_role),
        "assigned_user_id": (assignee["id"] if assignee else None),
        "assigned_user_name": (assignee["name"] if assignee else None),
        "assigned_user_email": (assignee.get("email") if assignee else None),
        "assigned_user_designation": (assignee.get("designation", "") if assignee else None),
        "assigned_user_team": (assignee.get("team", "") if assignee else None),
        "status": status_val,
        "submitter_id": user["id"],
        "submitter_name": user["name"],
        "submitter_team": user.get("team", ""),
        "submitter_designation": user.get("designation", ""),
        "created_at": now,
        "updated_at": now,
        "stage_entered_at": now,
        "stage_durations": {},
        "activity": activity,
        "attachments": [a.model_dump() for a in body.attachments],
        "timeline": body.timeline.model_dump(),
        "timeline_agreed": False,
        "approval_chain": [],
    }
    await db.submissions.insert_one(doc)

    if status_val == "pending_acceptance" and assignee:
        await create_notification(
            assignee["id"], sub_id, "assigned",
            f"New submission needs acceptance: {body.title}",
            f"From {user['name']} · accept by {body.timeline.accept_by}",
        )

    doc.pop("_id", None)
    return doc


@router.get("/submissions")
async def list_submissions(user: dict = Depends(get_current_user), status_filter: Optional[str] = None):
    query = {}
    if status_filter:
        query["status"] = status_filter
    items = await db.submissions.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [_annotate(it) for it in items]


@router.get("/submissions/{sub_id}")
async def get_submission(sub_id: str, user: dict = Depends(get_current_user)):
    item = await db.submissions.find_one({"id": sub_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Submission not found")
    return _annotate(item)


@router.post("/submissions/{sub_id}/accept")
async def accept_assignment(sub_id: str, body: AcceptIn, user: dict = Depends(get_current_user)):
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    if item["status"] != "pending_acceptance":
        raise HTTPException(status_code=400, detail=f"Cannot accept from status '{item['status']}'")
    assignee_id = item.get("assigned_user_id")
    if assignee_id and user["id"] != assignee_id:
        raise HTTPException(status_code=403, detail=f"Only the assigned user ({item.get('assigned_user_name')}) can accept this")
    if not assignee_id and user["role"] != item.get("reviewer_role"):
        raise HTTPException(status_code=403, detail=f"Only {item.get('reviewer_role')} can accept this")

    set_fields = {}
    note = body.note or "Assignment accepted"
    if body.timeline:
        set_fields["timeline"] = body.timeline.model_dump()
        set_fields["timeline_agreed"] = True
        note += " · timeline updated"
    else:
        set_fields["timeline_agreed"] = True

    activity_entry = {"ts": now_iso(), "actor": user["name"], "actor_role": user["role"], "action": "accepted", "note": note}
    activity = item.get("activity", []) + [activity_entry]
    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(item["stage_entered_at"])).total_seconds()
    durations = item.get("stage_durations", {}) or {}
    durations[item["status"]] = durations.get(item["status"], 0) + elapsed
    set_fields.update({
        "status": "in_progress",
        "stage_entered_at": now_iso(),
        "stage_durations": durations,
        "activity": activity,
        "updated_at": now_iso(),
        "accepted_at": now_iso(),
    })

    await db.submissions.update_one({"id": sub_id}, {"$set": set_fields})
    await create_notification(item["submitter_id"], sub_id, "accepted",
                              f"{user['name']} accepted '{item['title']}'", "Review is now in progress.")
    return await db.submissions.find_one({"id": sub_id}, {"_id": 0})


@router.post("/submissions/{sub_id}/propose-timeline")
async def propose_timeline(sub_id: str, body: TimelineProposal, user: dict = Depends(get_current_user)):
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    is_submitter = user["id"] == item["submitter_id"]
    is_reviewer = user["id"] == item.get("assigned_user_id") or (not item.get("assigned_user_id") and user["role"] == item.get("reviewer_role"))
    if not (is_submitter or is_reviewer):
        raise HTTPException(status_code=403, detail="Only submitter or assigned reviewer can propose timeline")

    proposal = {
        "accept_by": body.accept_by, "review_by": body.review_by, "approve_by": body.approve_by,
        "proposed_by": user["id"], "proposed_by_name": user["name"], "proposed_by_role": user["role"],
        "proposed_at": now_iso(), "note": body.note or "",
    }
    activity_entry = {"ts": now_iso(), "actor": user["name"], "actor_role": user["role"], "action": "timeline_proposed", "note": body.note or "New timeline proposed"}
    activity = item.get("activity", []) + [activity_entry]
    await db.submissions.update_one(
        {"id": sub_id},
        {"$set": {"pending_timeline_proposal": proposal, "activity": activity, "updated_at": now_iso()}},
    )
    if is_reviewer:
        await create_notification(item["submitter_id"], sub_id, "timeline_proposed", f"Timeline change proposed for '{item['title']}'", f"By {user['name']}")
    elif is_submitter and item.get("assigned_user_id"):
        await create_notification(item["assigned_user_id"], sub_id, "timeline_proposed", f"Timeline change proposed for '{item['title']}'", f"By {user['name']}")
    return await db.submissions.find_one({"id": sub_id}, {"_id": 0})


@router.post("/submissions/{sub_id}/agree-timeline")
async def agree_timeline(sub_id: str, body: ActionIn, user: dict = Depends(get_current_user)):
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    proposal = item.get("pending_timeline_proposal")
    if not proposal:
        raise HTTPException(status_code=400, detail="No pending timeline proposal")
    is_submitter = user["id"] == item["submitter_id"]
    is_reviewer = user["id"] == item.get("assigned_user_id") or (not item.get("assigned_user_id") and user["role"] == item.get("reviewer_role"))
    if proposal["proposed_by"] == user["id"] or not (is_submitter or is_reviewer):
        raise HTTPException(status_code=403, detail="Other party must agree to the proposal")

    new_timeline = {"accept_by": proposal["accept_by"], "review_by": proposal["review_by"], "approve_by": proposal["approve_by"]}
    activity_entry = {"ts": now_iso(), "actor": user["name"], "actor_role": user["role"], "action": "timeline_agreed", "note": body.note or "Agreed to new timeline"}
    activity = item.get("activity", []) + [activity_entry]
    await db.submissions.update_one(
        {"id": sub_id},
        {"$set": {"timeline": new_timeline, "timeline_agreed": True, "activity": activity, "updated_at": now_iso()},
         "$unset": {"pending_timeline_proposal": ""}},
    )
    await create_notification(proposal["proposed_by"], sub_id, "timeline_agreed",
                              f"Timeline accepted for '{item['title']}'", f"By {user['name']}")
    return await db.submissions.find_one({"id": sub_id}, {"_id": 0})


@router.post("/submissions/{sub_id}/forward-to-ceo")
async def forward_to_ceo(sub_id: str, body: EscalateIn, user: dict = Depends(get_current_user)):
    if user["role"] != "vp":
        raise HTTPException(status_code=403, detail="Only VPs can forward to CEO")
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    if item.get("assigned_user_id") and user["id"] != item["assigned_user_id"]:
        raise HTTPException(status_code=403, detail=f"Only {item.get('assigned_user_name')} (the assigned VP) can forward this")
    if item["status"] not in ("in_progress", "pending_acceptance"):
        raise HTTPException(status_code=400, detail="Can only forward in_progress or pending submissions")

    if body.assigned_user_id:
        target = await db.users.find_one({"id": body.assigned_user_id, "role": "ceo"}, {"_id": 0, "password_hash": 0})
        if not target:
            raise HTTPException(status_code=400, detail="Target user not found or not a CEO")
    else:
        target = await _pick_next_assignee(item, "ceo")
    if not target:
        raise HTTPException(status_code=400, detail="No CEO user available to forward to")

    activity_entry = {"ts": now_iso(), "actor": user["name"], "actor_role": user["role"], "action": "forwarded_to_ceo",
                      "note": body.note or f"Forwarded to CEO ({target['name']}) by VP"}
    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(item["stage_entered_at"])).total_seconds()
    durations = item.get("stage_durations", {}) or {}
    durations[item["status"]] = durations.get(item["status"], 0) + elapsed

    await db.submissions.update_one(
        {"id": sub_id},
        {"$set": {
            "reviewer_role": "ceo",
            "assigned_user_id": target["id"], "assigned_user_name": target["name"],
            "assigned_user_email": target.get("email"), "assigned_user_designation": target.get("designation", ""),
            "assigned_user_team": target.get("team", ""),
            "status": "pending_acceptance", "stage_entered_at": now_iso(),
            "stage_durations": durations, "activity": item.get("activity", []) + [activity_entry],
            "updated_at": now_iso(),
        }},
    )
    await create_notification(target["id"], sub_id, "forwarded_to_ceo", f"Submission forwarded to you: {item['title']}", f"From VP {user['name']}")
    await create_notification(item["submitter_id"], sub_id, "forwarded_to_ceo", f"'{item['title']}' forwarded to CEO", f"VP {user['name']} forwarded to {target['name']}")
    return await db.submissions.find_one({"id": sub_id}, {"_id": 0})


@router.post("/submissions/{sub_id}/approve")
async def approve(sub_id: str, body: ActionIn, user: dict = Depends(get_current_user)):
    if user["role"] not in ("reviewer", "marketing_lead", "vp", "ceo"):
        raise HTTPException(status_code=403, detail="Not authorized to approve")
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    if item["status"] not in DECISION_ALLOWED_FROM:
        raise HTTPException(status_code=400, detail=f"Cannot approve from status '{item['status']}'")
    if item.get("assigned_user_id") and user["id"] != item["assigned_user_id"]:
        raise HTTPException(status_code=403, detail=f"Only {item.get('assigned_user_name')} can approve this")

    chain = item.get("approval_chain", []) or []
    chain.append({
        "approver_id": user["id"], "approver_name": user["name"],
        "approver_role": user["role"], "approver_designation": user.get("designation", ""),
        "ts": now_iso(), "note": body.note or "",
        "step_timeline": item.get("timeline"),
        "closed": True,
    })
    await db.submissions.update_one({"id": sub_id}, {"$set": {"approval_chain": chain}})
    result = await _transition(sub_id, "approved", user, "approved", body.note or "Approved and chain closed")
    await create_notification(item["submitter_id"], sub_id, "approved",
                              f"'{item['title']}' approved", f"By {user['name']} — chain closed")
    return result


@router.post("/submissions/{sub_id}/approve-and-forward")
async def approve_and_forward(sub_id: str, body: ApproveForwardIn, user: dict = Depends(get_current_user)):
    if user["role"] not in ("reviewer", "marketing_lead", "vp", "ceo"):
        raise HTTPException(status_code=403, detail="Not authorized")
    if user["role"] == "ceo":
        raise HTTPException(status_code=400, detail="CEO approval is terminal — use /approve instead")
    if not body.assigned_user_id:
        raise HTTPException(status_code=400, detail="assigned_user_id required to forward")
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    if item["status"] not in DECISION_ALLOWED_FROM:
        raise HTTPException(status_code=400, detail=f"Cannot approve-and-forward from '{item['status']}'")
    if item.get("assigned_user_id") and user["id"] != item["assigned_user_id"]:
        raise HTTPException(status_code=403, detail=f"Only {item.get('assigned_user_name')} can act on this")

    chain = item.get("approval_chain", []) or []
    if len(chain) >= MAX_CHAIN_DEPTH:
        raise HTTPException(status_code=400, detail=f"Approval chain depth limit reached ({MAX_CHAIN_DEPTH})")

    target = await db.users.find_one({"id": body.assigned_user_id}, {"_id": 0, "password_hash": 0})
    if not target:
        raise HTTPException(status_code=400, detail="Target user not found")
    if target["role"] == "submitter":
        raise HTTPException(status_code=400, detail="Cannot forward to a submitter — pick a reviewer/lead/VP/CEO")
    if target["id"] == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot forward to yourself")

    chain.append({
        "approver_id": user["id"], "approver_name": user["name"],
        "approver_role": user["role"], "approver_designation": user.get("designation", ""),
        "ts": now_iso(), "note": body.note or "",
        "step_timeline": item.get("timeline"),
        "forwarded_to_id": target["id"], "forwarded_to_name": target["name"],
        "closed": False,
    })

    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(item["stage_entered_at"])).total_seconds()
    durations = item.get("stage_durations", {}) or {}
    durations[item["status"]] = durations.get(item["status"], 0) + elapsed

    activity = item.get("activity", []) + [{
        "ts": now_iso(), "actor": user["name"], "actor_role": user["role"],
        "action": "approved_and_forwarded",
        "note": f"Approved → forwarded to {target['name']}" + (f" · {body.note}" if body.note else ""),
    }]

    set_fields = {
        "approval_chain": chain,
        "status": "pending_acceptance",
        "reviewer_role": target["role"],
        "assigned_user_id": target["id"], "assigned_user_name": target["name"],
        "assigned_user_email": target.get("email"), "assigned_user_designation": target.get("designation", ""),
        "assigned_user_team": target.get("team", ""),
        "stage_entered_at": now_iso(), "stage_durations": durations,
        "activity": activity, "timeline_agreed": False, "updated_at": now_iso(),
        "auto_nudges_sent": {},
    }
    if body.timeline:
        set_fields["timeline"] = body.timeline.model_dump()

    await db.submissions.update_one({"id": sub_id}, {"$set": set_fields})
    next_tl = set_fields.get("timeline") or item.get("timeline") or {}
    await create_notification(target["id"], sub_id, "assigned",
                              f"Forwarded for your review: {item['title']}",
                              f"From {user['name']} · accept by {next_tl.get('accept_by', 'TBD')}")
    # Distinct notification kind for intermediate approvals
    await create_notification(item["submitter_id"], sub_id, "forwarded",
                              f"'{item['title']}' approved & forwarded by {user['name']}",
                              f"Next reviewer: {target['name']}" + (f" · {target.get('designation', '')}" if target.get('designation') else ""))
    return await db.submissions.find_one({"id": sub_id}, {"_id": 0})


@router.post("/submissions/{sub_id}/request-revision")
async def request_revision(sub_id: str, body: RevisionIn, user: dict = Depends(get_current_user)):
    if user["role"] not in ("reviewer", "marketing_lead", "vp", "ceo"):
        raise HTTPException(status_code=403, detail="Not authorized")
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    if item["status"] not in DECISION_ALLOWED_FROM:
        raise HTTPException(status_code=400, detail=f"Cannot request revision from status '{item['status']}'")
    if item.get("assigned_user_id") and user["id"] != item["assigned_user_id"]:
        raise HTTPException(status_code=403, detail=f"Only {item.get('assigned_user_name')} can request revision")
    result = await _transition(sub_id, "revision_requested", user, "requested_revision", body.note)
    await create_notification(item["submitter_id"], sub_id, "revision", f"Revision requested on '{item['title']}'", body.note)
    return result


@router.post("/submissions/{sub_id}/escalate")
async def escalate(sub_id: str, body: EscalateIn, user: dict = Depends(get_current_user)):
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    next_role_map = {"reviewer": "marketing_lead", "marketing_lead": "vp"}
    if user["role"] not in next_role_map:
        raise HTTPException(status_code=403, detail="This role cannot escalate further (use forward-to-ceo if VP)")
    if item.get("assigned_user_id") and user["id"] != item["assigned_user_id"]:
        raise HTTPException(status_code=403, detail=f"Only {item.get('assigned_user_name')} can escalate this")
    new_role = next_role_map[user["role"]]

    if body.assigned_user_id:
        target = await db.users.find_one({"id": body.assigned_user_id, "role": new_role}, {"_id": 0, "password_hash": 0})
        if not target:
            raise HTTPException(status_code=400, detail=f"Target user not found or not a {new_role}")
    else:
        target = await _pick_next_assignee(item, new_role)
    if not target:
        raise HTTPException(status_code=400, detail=f"No {new_role} user available")

    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(item["stage_entered_at"])).total_seconds()
    durations = item.get("stage_durations", {}) or {}
    durations[item["status"]] = durations.get(item["status"], 0) + elapsed
    activity_entry = {"ts": now_iso(), "actor": user["name"], "actor_role": user["role"], "action": "escalated",
                      "note": body.note or f"Escalated to {target['name']} ({new_role})"}
    await db.submissions.update_one(
        {"id": sub_id},
        {"$set": {
            "status": "escalated", "reviewer_role": new_role,
            "assigned_user_id": target["id"], "assigned_user_name": target["name"],
            "assigned_user_email": target.get("email"), "assigned_user_designation": target.get("designation", ""),
            "assigned_user_team": target.get("team", ""),
            "stage_entered_at": now_iso(), "stage_durations": durations,
            "activity": item.get("activity", []) + [activity_entry], "updated_at": now_iso(),
        }},
    )
    await create_notification(target["id"], sub_id, "escalation", f"Escalated to you: {item['title']}", f"From {user['name']}")
    await create_notification(item["submitter_id"], sub_id, "escalation", f"'{item['title']}' escalated", f"{user['name']} → {target['name']}")
    return await db.submissions.find_one({"id": sub_id}, {"_id": 0})


@router.post("/submissions/{sub_id}/mark-live")
async def mark_live(sub_id: str, body: ActionIn, user: dict = Depends(get_current_user)):
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    if item["status"] != "approved":
        raise HTTPException(status_code=400, detail="Can only mark approved items as live")
    result = await _transition(sub_id, "live", user, "marked_live", body.note or "Published live")
    await create_notification(item["submitter_id"], sub_id, "live", f"'{item['title']}' is live", "")
    return result


@router.post("/submissions/{sub_id}/nudge")
async def nudge(sub_id: str, body: ActionIn, user: dict = Depends(get_current_user)):
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    activity = item.get("activity", []) + [{
        "ts": now_iso(), "actor": user["name"], "actor_role": user["role"],
        "action": "nudged", "note": body.note or "Reviewer nudged",
    }]
    await db.submissions.update_one({"id": sub_id}, {"$set": {"activity": activity, "updated_at": now_iso()}})
    if item.get("assigned_user_id"):
        await create_notification(item["assigned_user_id"], sub_id, "nudge_manual", f"Nudged: {item['title']}", body.note or f"From {user['name']}")
    else:
        await notify_role(item.get("reviewer_role", ""), sub_id, "nudge_manual", f"Nudged: {item['title']}", body.note or f"From {user['name']}")
    return await db.submissions.find_one({"id": sub_id}, {"_id": 0})
