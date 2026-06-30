"""Notification helpers + endpoints."""
import uuid
from typing import Optional, get_args

import httpx
from fastapi import APIRouter, Depends

from core import db, now_iso, get_current_user, TEAMS_WEBHOOK_URL, logger
from models import NotificationKind

router = APIRouter()

_VALID_KINDS = set(get_args(NotificationKind))


async def notify_teams(title: str, body: str):
    """Posts a notification to a Slack channel via Incoming Webhook, if configured."""
    if not TEAMS_WEBHOOK_URL:
        return
    payload = {"text": f"*{title}*\n{body}"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(TEAMS_WEBHOOK_URL, json=payload)
    except Exception as e:
        logger.warning(f"Slack notification failed: {e}")


async def create_notification(user_id: str, submission_id: str, kind: str, title: str, body: str):
    if kind not in _VALID_KINDS:
        # Soft-warn rather than crash — keeps behaviour permissive while flagging typos.
        logger.warning(f"Unknown notification kind '{kind}' — not in NotificationKind enum")
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "submission_id": submission_id,
        "kind": kind,
        "title": title,
        "body": body,
        "read": False,
        "created_at": now_iso(),
    }
    await db.notifications.insert_one(doc)
    await notify_teams(title, body)


async def notify_role(role: str, submission_id: str, kind: str, title: str, body: str,
                      exclude_user_id: Optional[str] = None):
    """Broadcast in-app notification to every user with `role`. Avoid for nudges — use a single assignee instead."""
    users = await db.users.find({"role": role}).to_list(200)
    for u in users:
        if exclude_user_id and u["id"] == exclude_user_id:
            continue
        await create_notification(u["id"], submission_id, kind, title, body)


@router.get("/notifications")
async def list_notifications(user: dict = Depends(get_current_user), unread_only: bool = False):
    query = {"user_id": user["id"]}
    if unread_only:
        query["read"] = False
    items = await db.notifications.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    unread = await db.notifications.count_documents({"user_id": user["id"], "read": False})
    return {"items": items, "unread_count": unread}


@router.post("/notifications/{nid}/read")
async def mark_notification_read(nid: str, user: dict = Depends(get_current_user)):
    await db.notifications.update_one({"id": nid, "user_id": user["id"]}, {"$set": {"read": True}})
    return {"ok": True}


@router.post("/notifications/read-all")
async def mark_all_read(user: dict = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": user["id"], "read": False}, {"$set": {"read": True}})
    return {"ok": True}