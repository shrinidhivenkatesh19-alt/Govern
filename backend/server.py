from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, UploadFile, File, Header, Query, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import json
import re
import uuid
import bcrypt
import jwt
import requests
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr, model_validator
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta

import asyncio
from emergentintegrations.llm.chat import LlmChat, UserMessage

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_DAYS = int(os.environ.get("JWT_EXPIRE_DAYS", "7"))
EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]

# Object storage
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
APP_NAME = "govern-approval"
storage_key: Optional[str] = None

MIME_TYPES = {
    "pdf": "application/pdf",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "txt": "text/plain",
    "csv": "text/csv",
    "md": "text/markdown",
}
ALLOWED_EXT = set(MIME_TYPES.keys())
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


def init_storage() -> str:
    global storage_key
    if storage_key:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_LLM_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key


def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def get_object(path: str) -> tuple:
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")


app = FastAPI(title="Content Approval Agent")
api_router = APIRouter(prefix="/api")
security = HTTPBearer()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


# ---------- Helpers ----------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(pwd: str) -> str:
    return bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()


def verify_password(pwd: str, hashed: str) -> bool:
    return bcrypt.checkpw(pwd.encode(), hashed.encode())


def make_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


async def get_current_user(creds: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ---------- Models ----------
Role = Literal["submitter", "reviewer", "marketing_lead", "vp", "ceo"]
SubmissionStatus = Literal["scored", "pending_acceptance", "in_progress", "under_review", "approved", "revision_requested", "escalated", "live"]
Tier = Literal["auto_approve", "product_only", "ceo_required"]


class Timeline(BaseModel):
    accept_by: str  # ISO date — reviewer must accept by this
    review_by: str  # ISO date — review/decision by this
    approve_by: str  # ISO date — final approval by this


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: Role = "submitter"
    team: Optional[str] = ""
    designation: Optional[str] = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ScoreIn(BaseModel):
    title: str
    request_type: str  # Free-text — replaces the legacy fixed content_type dropdown
    brief: str
    content: str


class ScoreResult(BaseModel):
    brand_alignment_score: int  # 0-100
    completeness_score: int  # 0-100
    content_classification: Literal["routine", "innovation"]
    risk_flags: List[str]  # e.g. ["pricing", "legal"]
    overall_score: int  # 0-100
    recommended_tier: Tier
    reasoning: str
    questions_to_resolve: List[str]


class Attachment(BaseModel):
    id: str
    original_filename: str
    content_type: str
    size: int
    storage_path: str


class SubmissionCreate(BaseModel):
    title: str
    request_type: str  # Free-text replaces the old content_type dropdown
    brief: str
    content: str
    deadline: str  # ISO date
    score_result: ScoreResult
    chosen_tier: Tier  # may differ from recommended (human override)
    attachments: List[Attachment] = Field(default_factory=list)
    timeline: Timeline
    assigned_user_id: Optional[str] = None  # required for non-auto_approve tiers

    @model_validator(mode="after")
    def _require_assignee_for_non_auto(self):
        if self.chosen_tier != "auto_approve" and not (self.assigned_user_id or "").strip():
            raise ValueError("assigned_user_id is required for non auto_approve tiers")
        return self


class TimelineProposal(BaseModel):
    accept_by: str
    review_by: str
    approve_by: str
    note: Optional[str] = ""


class AcceptIn(BaseModel):
    note: Optional[str] = ""
    timeline: Optional[Timeline] = None  # reviewer may propose updated timeline at acceptance


class ActionIn(BaseModel):
    note: Optional[str] = ""


class RevisionIn(BaseModel):
    note: str


class EscalateIn(BaseModel):
    note: Optional[str] = ""
    assigned_user_id: Optional[str] = None  # if set, escalate to this specific user (must be in the next role)


# ---------- Auth Routes ----------
@api_router.post("/auth/register")
async def register(body: RegisterIn):
    existing = await db.users.find_one({"email": body.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = str(uuid.uuid4())
    doc = {
        "id": user_id,
        "email": body.email.lower(),
        "name": body.name,
        "role": body.role,
        "team": body.team or "",
        "designation": body.designation or "",
        "password_hash": hash_password(body.password),
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    token = make_token(user_id, body.email.lower(), body.role)
    return {"token": token, "user": {"id": user_id, "email": body.email.lower(), "name": body.name, "role": body.role, "team": doc["team"], "designation": doc["designation"]}}


@api_router.post("/auth/login")
async def login(body: LoginIn):
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = make_token(user["id"], user["email"], user["role"])
    return {"token": token, "user": {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "team": user.get("team", ""),
        "designation": user.get("designation", ""),
    }}


@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@api_router.get("/users")
async def list_users(user: dict = Depends(get_current_user)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(500)
    return users


# ---------- Scoring ----------
SYSTEM_PROMPT = """You are a senior marketing governance agent. Evaluate marketing content briefs and return STRICT JSON only.

Scoring criteria:
1. brand_alignment_score (0-100): tone, voice, professional polish, messaging coherence.
2. completeness_score (0-100): does the brief have enough context (audience, goal, CTA, channel)? Is content ready to review or will it bounce back?
3. content_classification: "routine" (recurring social, blog, email) OR "innovation" (launches, new positioning, partnerships, pricing changes).
4. risk_flags: list any of ["pricing", "legal", "partnership", "announcement", "competitor_claim", "regulatory"] that apply. Empty list if none.
5. overall_score (0-100): weighted average reflecting readiness.
6. recommended_tier:
   - "auto_approve" if routine, no risk flags, completeness >= 80, brand >= 80.
   - "ceo_required" if any of: risk_flags non-empty (esp. pricing/legal/partnership/announcement) OR classification is "innovation".
   - "product_only" otherwise.
7. reasoning: 2-3 sentence explanation.
8. questions_to_resolve: list of specific questions if completeness < 80, else [].

Return ONLY valid JSON. No markdown, no preface."""


def extract_json(text: str) -> dict:
    text = text.strip()
    # Remove markdown fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("No JSON found in LLM response")


@api_router.post("/score", response_model=ScoreResult)
async def score_content(body: ScoreIn, user: dict = Depends(get_current_user)):
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"score-{uuid.uuid4()}",
        system_message=SYSTEM_PROMPT,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")

    user_text = f"""Title: {body.title}
Request Type: {body.request_type}

Brief:
{body.brief}

Content:
{body.content}

Return JSON with keys: brand_alignment_score, completeness_score, content_classification, risk_flags, overall_score, recommended_tier, reasoning, questions_to_resolve."""

    response = await chat.send_message(UserMessage(text=user_text))

    try:
        data = extract_json(response if isinstance(response, str) else str(response))
        # Coerce types defensively
        data["brand_alignment_score"] = int(data.get("brand_alignment_score", 0))
        data["completeness_score"] = int(data.get("completeness_score", 0))
        data["overall_score"] = int(data.get("overall_score", 0))
        data["risk_flags"] = list(data.get("risk_flags", []) or [])
        data["questions_to_resolve"] = list(data.get("questions_to_resolve", []) or [])
        return ScoreResult(**data)
    except Exception as e:
        logger.error(f"Score parse failed: {e}; raw={response}")
        raise HTTPException(status_code=502, detail=f"Scoring failed: {e}")


# ---------- Notifications helper ----------
async def create_notification(user_id: str, submission_id: str, kind: str, title: str, body: str):
    doc = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "submission_id": submission_id,
        "kind": kind,  # e.g. "nudge_accept", "nudge_review", "escalation", "assigned", "approved", "revision"
        "title": title,
        "body": body,
        "read": False,
        "created_at": now_iso(),
    }
    await db.notifications.insert_one(doc)


async def notify_role(role: str, submission_id: str, kind: str, title: str, body: str, exclude_user_id: Optional[str] = None):
    users = await db.users.find({"role": role}).to_list(200)
    for u in users:
        if exclude_user_id and u["id"] == exclude_user_id:
            continue
        await create_notification(u["id"], submission_id, kind, title, body)


# ---------- Submissions ----------
def initial_status_for_tier(tier: Tier) -> SubmissionStatus:
    if tier == "auto_approve":
        return "approved"
    return "pending_acceptance"


def reviewer_role_for_tier(tier: Tier) -> str:
    # CEO-required items funnel through VPs first — team members cannot push to CEO
    return {"auto_approve": "system", "product_only": "reviewer", "ceo_required": "vp"}[tier]


@api_router.post("/submissions")
async def create_submission(body: SubmissionCreate, user: dict = Depends(get_current_user)):
    sub_id = str(uuid.uuid4())
    status_val = initial_status_for_tier(body.chosen_tier)
    suggested_role = reviewer_role_for_tier(body.chosen_tier)
    now = now_iso()

    # Look up the assigned user
    assignee = await db.users.find_one({"id": body.assigned_user_id}, {"_id": 0, "password_hash": 0})
    if not assignee and status_val != "approved":
        raise HTTPException(status_code=400, detail="Assigned user not found")

    activity = [
        {"ts": now, "actor": user["name"], "actor_role": user["role"], "action": "submitted",
         "note": f"Submitted as {body.chosen_tier}" + (f"; assigned to {assignee['name']}" if assignee else "; auto-approved")},
    ]
    if status_val == "approved":
        activity.append({"ts": now, "actor": "Agent", "actor_role": "system", "action": "auto_approved", "note": "Routine content, auto-approved by agent"})

    doc = {
        "id": sub_id,
        "title": body.title,
        "request_type": body.request_type,
        "content_type": body.request_type,  # back-compat for analytics aggregations
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
    }
    await db.submissions.insert_one(doc)

    if status_val == "pending_acceptance" and assignee:
        await create_notification(
            assignee["id"],
            sub_id,
            "assigned",
            f"New submission needs acceptance: {body.title}",
            f"From {user['name']} · accept by {body.timeline.accept_by}",
        )

    doc.pop("_id", None)
    return doc


def _annotate(item: dict) -> dict:
    """Compute live SLA / idle / timeline-breach flags on a submission."""
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
            overdue["approve"] = item["status"] in ("in_progress", "pending_acceptance", "under_review", "escalated") and tl.get("approve_by") and today > tl["approve_by"]
        except Exception:
            overdue = {}
    item["timeline_overdue"] = overdue
    item["any_overdue"] = bool(overdue.get("accept") or overdue.get("review") or overdue.get("approve"))

    # Hard escalation when >= 80% of created→deadline elapsed without final decision
    try:
        created = datetime.fromisoformat(item["created_at"])
        deadline_dt = datetime.fromisoformat(item["deadline"] + "T23:59:59+00:00") if "T" not in item["deadline"] else datetime.fromisoformat(item["deadline"])
        total = (deadline_dt - created).total_seconds()
        elapsed = (now - created).total_seconds()
        item["deadline_progress"] = round(min(max(elapsed / total, 0), 1), 3) if total > 0 else 1.0
    except Exception:
        item["deadline_progress"] = 0.0

    item["needs_nudge"] = item["any_overdue"] and item["status"] in ("pending_acceptance", "in_progress", "under_review", "escalated")
    item["needs_escalation"] = item["deadline_progress"] >= 0.8 and item["status"] in ("pending_acceptance", "in_progress", "under_review")
    return item


@api_router.get("/submissions")
async def list_submissions(user: dict = Depends(get_current_user), status_filter: Optional[str] = None):
    query = {}
    if status_filter:
        query["status"] = status_filter
    items = await db.submissions.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return [_annotate(it) for it in items]


@api_router.get("/submissions/{sub_id}")
async def get_submission(sub_id: str, user: dict = Depends(get_current_user)):
    item = await db.submissions.find_one({"id": sub_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Submission not found")
    return _annotate(item)


async def _transition(sub_id: str, new_status: SubmissionStatus, actor: dict, action: str, note: str):
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


@api_router.post("/submissions/{sub_id}/accept")
async def accept_assignment(sub_id: str, body: AcceptIn, user: dict = Depends(get_current_user)):
    """Assigned user accepts the assignment, optionally proposing updated timeline."""
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
        note += f" · timeline updated"
    else:
        set_fields["timeline_agreed"] = True

    activity_entry = {
        "ts": now_iso(),
        "actor": user["name"],
        "actor_role": user["role"],
        "action": "accepted",
        "note": note,
    }
    activity = item.get("activity", []) + [activity_entry]
    set_fields.update({
        "status": "in_progress",
        "stage_entered_at": now_iso(),
        "activity": activity,
        "updated_at": now_iso(),
        "accepted_at": now_iso(),
    })
    # Roll up time spent in pending_acceptance
    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(item["stage_entered_at"])).total_seconds()
    durations = item.get("stage_durations", {}) or {}
    durations[item["status"]] = durations.get(item["status"], 0) + elapsed
    set_fields["stage_durations"] = durations

    await db.submissions.update_one({"id": sub_id}, {"$set": set_fields})
    await create_notification(
        item["submitter_id"], sub_id, "accepted",
        f"{user['name']} accepted '{item['title']}'",
        "Review is now in progress.",
    )
    return await db.submissions.find_one({"id": sub_id}, {"_id": 0})


@api_router.post("/submissions/{sub_id}/propose-timeline")
async def propose_timeline(sub_id: str, body: TimelineProposal, user: dict = Depends(get_current_user)):
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    is_submitter = user["id"] == item["submitter_id"]
    is_reviewer = user["id"] == item.get("assigned_user_id") or (not item.get("assigned_user_id") and user["role"] == item.get("reviewer_role"))
    if not (is_submitter or is_reviewer):
        raise HTTPException(status_code=403, detail="Only submitter or assigned reviewer can propose timeline")

    proposal = {
        "accept_by": body.accept_by,
        "review_by": body.review_by,
        "approve_by": body.approve_by,
        "proposed_by": user["id"],
        "proposed_by_name": user["name"],
        "proposed_by_role": user["role"],
        "proposed_at": now_iso(),
        "note": body.note or "",
    }
    activity_entry = {
        "ts": now_iso(),
        "actor": user["name"],
        "actor_role": user["role"],
        "action": "timeline_proposed",
        "note": body.note or "New timeline proposed",
    }
    activity = item.get("activity", []) + [activity_entry]
    await db.submissions.update_one(
        {"id": sub_id},
        {"$set": {
            "pending_timeline_proposal": proposal,
            "activity": activity,
            "updated_at": now_iso(),
        }},
    )
    # Notify the other party (specific user when possible)
    if is_reviewer:
        await create_notification(item["submitter_id"], sub_id, "timeline_proposed", f"Timeline change proposed for '{item['title']}'", f"By {user['name']}")
    elif is_submitter and item.get("assigned_user_id"):
        await create_notification(item["assigned_user_id"], sub_id, "timeline_proposed", f"Timeline change proposed for '{item['title']}'", f"By {user['name']}")
    return await db.submissions.find_one({"id": sub_id}, {"_id": 0})


@api_router.post("/submissions/{sub_id}/agree-timeline")
async def agree_timeline(sub_id: str, body: ActionIn, user: dict = Depends(get_current_user)):
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    proposal = item.get("pending_timeline_proposal")
    if not proposal:
        raise HTTPException(status_code=400, detail="No pending timeline proposal")
    is_submitter = user["id"] == item["submitter_id"]
    is_reviewer = user["id"] == item.get("assigned_user_id") or (not item.get("assigned_user_id") and user["role"] == item.get("reviewer_role"))
    # The one who didn't propose must agree
    if proposal["proposed_by"] == user["id"] or not (is_submitter or is_reviewer):
        raise HTTPException(status_code=403, detail="Other party must agree to the proposal")

    new_timeline = {"accept_by": proposal["accept_by"], "review_by": proposal["review_by"], "approve_by": proposal["approve_by"]}
    activity_entry = {
        "ts": now_iso(),
        "actor": user["name"],
        "actor_role": user["role"],
        "action": "timeline_agreed",
        "note": body.note or "Agreed to new timeline",
    }
    activity = item.get("activity", []) + [activity_entry]
    await db.submissions.update_one(
        {"id": sub_id},
        {"$set": {"timeline": new_timeline, "timeline_agreed": True, "activity": activity, "updated_at": now_iso()},
         "$unset": {"pending_timeline_proposal": ""}},
    )
    await create_notification(
        proposal["proposed_by"], sub_id, "timeline_agreed",
        f"Timeline accepted for '{item['title']}'",
        f"By {user['name']}",
    )
    return await db.submissions.find_one({"id": sub_id}, {"_id": 0})


@api_router.post("/submissions/{sub_id}/forward-to-ceo")
async def forward_to_ceo(sub_id: str, body: EscalateIn, user: dict = Depends(get_current_user)):
    """VP-only action: forward to a specific CEO user (or auto-pick one)."""
    if user["role"] != "vp":
        raise HTTPException(status_code=403, detail="Only VPs can forward to CEO")
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    if item.get("assigned_user_id") and user["id"] != item["assigned_user_id"]:
        raise HTTPException(status_code=403, detail=f"Only {item.get('assigned_user_name')} (the assigned VP) can forward this")
    if item["status"] not in ("in_progress", "pending_acceptance"):
        raise HTTPException(status_code=400, detail="Can only forward in_progress or pending submissions")

    # Pick target CEO user
    target = None
    if body.assigned_user_id:
        target = await db.users.find_one({"id": body.assigned_user_id, "role": "ceo"}, {"_id": 0, "password_hash": 0})
        if not target:
            raise HTTPException(status_code=400, detail="Target user not found or not a CEO")
    else:
        target = await _pick_next_assignee(item, "ceo")
    if not target:
        raise HTTPException(status_code=400, detail="No CEO user available to forward to")

    activity_entry = {
        "ts": now_iso(),
        "actor": user["name"],
        "actor_role": user["role"],
        "action": "forwarded_to_ceo",
        "note": body.note or f"Forwarded to CEO ({target['name']}) by VP",
    }
    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(item["stage_entered_at"])).total_seconds()
    durations = item.get("stage_durations", {}) or {}
    durations[item["status"]] = durations.get(item["status"], 0) + elapsed

    await db.submissions.update_one(
        {"id": sub_id},
        {"$set": {
            "reviewer_role": "ceo",
            "assigned_user_id": target["id"],
            "assigned_user_name": target["name"],
            "assigned_user_email": target.get("email"),
            "assigned_user_designation": target.get("designation", ""),
            "assigned_user_team": target.get("team", ""),
            "status": "pending_acceptance",
            "stage_entered_at": now_iso(),
            "stage_durations": durations,
            "activity": item.get("activity", []) + [activity_entry],
            "updated_at": now_iso(),
        }},
    )
    await create_notification(target["id"], sub_id, "forwarded_to_ceo", f"Submission forwarded to you: {item['title']}", f"From VP {user['name']}")
    await create_notification(item["submitter_id"], sub_id, "forwarded_to_ceo", f"'{item['title']}' forwarded to CEO", f"VP {user['name']} forwarded to {target['name']}")
    return await db.submissions.find_one({"id": sub_id}, {"_id": 0})


@api_router.post("/submissions/{sub_id}/approve")
async def approve(sub_id: str, body: ActionIn, user: dict = Depends(get_current_user)):
    if user["role"] not in ("reviewer", "marketing_lead", "vp", "ceo"):
        raise HTTPException(status_code=403, detail="Not authorized to approve")
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    if item.get("assigned_user_id") and user["id"] != item["assigned_user_id"]:
        raise HTTPException(status_code=403, detail=f"Only {item.get('assigned_user_name')} can approve this")
    result = await _transition(sub_id, "approved", user, "approved", body.note or "")
    await create_notification(item["submitter_id"], sub_id, "approved", f"'{item['title']}' approved", f"By {user['name']}")
    return result


@api_router.post("/submissions/{sub_id}/request-revision")
async def request_revision(sub_id: str, body: RevisionIn, user: dict = Depends(get_current_user)):
    if user["role"] not in ("reviewer", "marketing_lead", "vp", "ceo"):
        raise HTTPException(status_code=403, detail="Not authorized")
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    if item.get("assigned_user_id") and user["id"] != item["assigned_user_id"]:
        raise HTTPException(status_code=403, detail=f"Only {item.get('assigned_user_name')} can request revision")
    result = await _transition(sub_id, "revision_requested", user, "requested_revision", body.note)
    await create_notification(item["submitter_id"], sub_id, "revision", f"Revision requested on '{item['title']}'", body.note)
    return result


@api_router.post("/submissions/{sub_id}/escalate")
async def escalate(sub_id: str, body: EscalateIn, user: dict = Depends(get_current_user)):
    """Escalate one level up to a specific user. reviewer → marketing_lead, marketing_lead → vp."""
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    next_role_map = {"reviewer": "marketing_lead", "marketing_lead": "vp"}
    if user["role"] not in next_role_map:
        raise HTTPException(status_code=403, detail="This role cannot escalate further (use forward-to-ceo if VP)")
    if item.get("assigned_user_id") and user["id"] != item["assigned_user_id"]:
        raise HTTPException(status_code=403, detail=f"Only {item.get('assigned_user_name')} can escalate this")
    new_role = next_role_map[user["role"]]

    target = None
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
    activity_entry = {
        "ts": now_iso(),
        "actor": user["name"],
        "actor_role": user["role"],
        "action": "escalated",
        "note": body.note or f"Escalated to {target['name']} ({new_role})",
    }
    await db.submissions.update_one(
        {"id": sub_id},
        {"$set": {
            "status": "escalated",
            "reviewer_role": new_role,
            "assigned_user_id": target["id"],
            "assigned_user_name": target["name"],
            "assigned_user_email": target.get("email"),
            "assigned_user_designation": target.get("designation", ""),
            "assigned_user_team": target.get("team", ""),
            "stage_entered_at": now_iso(),
            "stage_durations": durations,
            "activity": item.get("activity", []) + [activity_entry],
            "updated_at": now_iso(),
        }},
    )
    await create_notification(target["id"], sub_id, "escalation", f"Escalated to you: {item['title']}", f"From {user['name']}")
    await create_notification(item["submitter_id"], sub_id, "escalation", f"'{item['title']}' escalated", f"{user['name']} → {target['name']}")
    return await db.submissions.find_one({"id": sub_id}, {"_id": 0})


@api_router.post("/submissions/{sub_id}/mark-live")
async def mark_live(sub_id: str, body: ActionIn, user: dict = Depends(get_current_user)):
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    if item["status"] != "approved":
        raise HTTPException(status_code=400, detail="Can only mark approved items as live")
    result = await _transition(sub_id, "live", user, "marked_live", body.note or "Published live")
    await create_notification(item["submitter_id"], sub_id, "live", f"'{item['title']}' is live", "")
    return result


@api_router.post("/submissions/{sub_id}/nudge")
async def nudge(sub_id: str, body: ActionIn, user: dict = Depends(get_current_user)):
    item = await db.submissions.find_one({"id": sub_id})
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    activity = item.get("activity", [])
    activity.append({
        "ts": now_iso(),
        "actor": user["name"],
        "actor_role": user["role"],
        "action": "nudged",
        "note": body.note or "Reviewer nudged",
    })
    await db.submissions.update_one({"id": sub_id}, {"$set": {"activity": activity, "updated_at": now_iso()}})
    if item.get("assigned_user_id"):
        await create_notification(item["assigned_user_id"], sub_id, "nudge_manual", f"Nudged: {item['title']}", body.note or f"From {user['name']}")
    else:
        await notify_role(item.get("reviewer_role", ""), sub_id, "nudge_manual", f"Nudged: {item['title']}", body.note or f"From {user['name']}")
    return await db.submissions.find_one({"id": sub_id}, {"_id": 0})


async def _pick_next_assignee(item: dict, next_role: str) -> Optional[dict]:
    """Pick a specific user for the next role. Prefer same team as current assignee, else any user with that role."""
    current_team = (item.get("assigned_user_team") or "").strip()
    candidates = await db.users.find({"role": next_role}).to_list(100)
    if not candidates:
        return None
    if current_team:
        same_team = [c for c in candidates if (c.get("team") or "").strip() == current_team]
        if same_team:
            return same_team[0]
    return candidates[0]


# ---------- Notifications API ----------
@api_router.get("/notifications")
async def list_notifications(user: dict = Depends(get_current_user), unread_only: bool = False):
    query = {"user_id": user["id"]}
    if unread_only:
        query["read"] = False
    items = await db.notifications.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    unread = await db.notifications.count_documents({"user_id": user["id"], "read": False})
    return {"items": items, "unread_count": unread}


@api_router.post("/notifications/{nid}/read")
async def mark_notification_read(nid: str, user: dict = Depends(get_current_user)):
    await db.notifications.update_one({"id": nid, "user_id": user["id"]}, {"$set": {"read": True}})
    return {"ok": True}


@api_router.post("/notifications/read-all")
async def mark_all_read(user: dict = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": user["id"], "read": False}, {"$set": {"read": True}})
    return {"ok": True}


# ---------- Analytics ----------
@api_router.get("/analytics/overview")
async def analytics(user: dict = Depends(get_current_user)):
    items = await db.submissions.find({}, {"_id": 0}).to_list(2000)
    now = datetime.now(timezone.utc)

    total = len(items)
    by_status = {}
    by_tier = {}
    by_type = {}
    idle_count = 0
    idle_breakdown = []
    risk_flag_counts = {}

    # Avg time per stage (seconds)
    stage_seconds = {}
    stage_counts = {}

    bottleneck_reviewers = {}  # reviewer_role -> total wait hours

    for it in items:
        by_status[it["status"]] = by_status.get(it["status"], 0) + 1
        by_tier[it["chosen_tier"]] = by_tier.get(it["chosen_tier"], 0) + 1
        by_type[it["content_type"]] = by_type.get(it["content_type"], 0) + 1

        for flag in (it.get("score_result") or {}).get("risk_flags", []):
            risk_flag_counts[flag] = risk_flag_counts.get(flag, 0) + 1

        entered = datetime.fromisoformat(it["stage_entered_at"])
        idle_hours = (now - entered).total_seconds() / 3600
        if it["status"] in ("under_review", "escalated", "revision_requested") and idle_hours >= 24:
            idle_count += 1
            idle_breakdown.append({
                "id": it["id"],
                "title": it["title"],
                "status": it["status"],
                "idle_hours": round(idle_hours, 1),
                "reviewer_role": it.get("reviewer_role"),
            })

        for stage, secs in (it.get("stage_durations") or {}).items():
            stage_seconds[stage] = stage_seconds.get(stage, 0) + secs
            stage_counts[stage] = stage_counts.get(stage, 0) + 1

        if it["status"] in ("under_review", "escalated"):
            bottleneck_reviewers[it.get("reviewer_role", "unknown")] = bottleneck_reviewers.get(it.get("reviewer_role", "unknown"), 0) + idle_hours

    avg_stage_hours = {k: round(v / max(stage_counts.get(k, 1), 1) / 3600, 2) for k, v in stage_seconds.items()}

    # Average end-to-end approval time for fully approved/live items
    completed = [it for it in items if it["status"] in ("approved", "live")]
    if completed:
        total_secs = 0
        for it in completed:
            created = datetime.fromisoformat(it["created_at"])
            updated = datetime.fromisoformat(it["updated_at"])
            total_secs += (updated - created).total_seconds()
        avg_approval_hours = round(total_secs / len(completed) / 3600, 2)
    else:
        avg_approval_hours = 0

    return {
        "total": total,
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


@api_router.post("/upload")
async def upload_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    filename = file.filename or "file"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type .{ext}. Allowed: {sorted(ALLOWED_EXT)}")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_UPLOAD_BYTES // (1024*1024)}MB)")
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    file_id = str(uuid.uuid4())
    path = f"{APP_NAME}/uploads/{user['id']}/{file_id}.{ext}"
    content_type = file.content_type or MIME_TYPES.get(ext, "application/octet-stream")

    try:
        result = put_object(path, data, content_type)
    except requests.RequestException as e:
        logger.error(f"Storage upload failed: {e}")
        raise HTTPException(status_code=502, detail="File storage upload failed")

    doc = {
        "id": file_id,
        "storage_path": result["path"],
        "original_filename": filename,
        "content_type": content_type,
        "size": result.get("size", len(data)),
        "uploader_id": user["id"],
        "is_deleted": False,
        "created_at": now_iso(),
    }
    await db.files.insert_one(doc)
    return {
        "id": file_id,
        "original_filename": filename,
        "content_type": content_type,
        "size": doc["size"],
        "storage_path": result["path"],
    }


@api_router.get("/files/{file_id}/download")
async def download_file(file_id: str, authorization: Optional[str] = Header(None), auth: Optional[str] = Query(None)):
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif auth:
        token = auth
    if not token:
        raise HTTPException(status_code=401, detail="Auth required")
    try:
        jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    record = await db.files.find_one({"id": file_id, "is_deleted": False}, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        data, ct = get_object(record["storage_path"])
    except requests.RequestException as e:
        logger.error(f"Storage download failed: {e}")
        raise HTTPException(status_code=502, detail="File download failed")

    return Response(
        content=data,
        media_type=record.get("content_type", ct),
        headers={
            "Content-Disposition": f'inline; filename="{record["original_filename"]}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@app.on_event("startup")
async def on_startup():
    try:
        init_storage()
        logger.info("Object storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed at startup: {e}")
    # Start SLA scheduler
    asyncio.create_task(sla_scheduler_loop())
    logger.info("SLA scheduler task scheduled")


async def sla_scheduler_loop():
    """Every 15 min, scan open submissions, fire nudge notifications when SLAs breach,
    and auto-escalate when 80%+ of created→deadline elapsed without a decision."""
    interval = int(os.environ.get("SLA_INTERVAL_SECONDS", "900"))
    await asyncio.sleep(20)  # let app warm up first
    while True:
        try:
            await run_sla_check()
        except Exception as e:
            logger.error(f"SLA loop error: {e}")
        await asyncio.sleep(interval)


async def run_sla_check():
    open_statuses = ["pending_acceptance", "in_progress", "under_review", "escalated"]
    items = await db.submissions.find({"status": {"$in": open_statuses}}).to_list(2000)
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    for item in items:
        sub_id = item["id"]
        tl = item.get("timeline") or {}
        last_nudges = item.get("auto_nudges_sent", {}) or {}
        new_nudges = dict(last_nudges)
        activity_additions = []

        async def fire(kind: str, msg: str):
            if item.get("assigned_user_id"):
                await create_notification(item["assigned_user_id"], sub_id, kind, f"SLA breach: {item['title']}", msg)
            else:
                await notify_role(item.get("reviewer_role", ""), sub_id, kind, f"SLA breach: {item['title']}", msg)
            activity_additions.append({
                "ts": now_iso(),
                "actor": "Agent",
                "actor_role": "system",
                "action": kind,
                "note": msg,
            })

        # Accept SLA breach
        if item["status"] == "pending_acceptance" and tl.get("accept_by") and today > tl["accept_by"]:
            if last_nudges.get("accept") != today:
                await fire("auto_nudge_accept", f"Past accept-by date ({tl['accept_by']}). Reviewer has not accepted.")
                new_nudges["accept"] = today

        # Review SLA breach
        if item["status"] == "in_progress" and tl.get("review_by") and today > tl["review_by"]:
            if last_nudges.get("review") != today:
                await fire("auto_nudge_review", f"Past review-by date ({tl['review_by']}). Decision pending.")
                new_nudges["review"] = today

        # Hard escalation when ≥80% of created→deadline elapsed without final decision
        try:
            created = datetime.fromisoformat(item["created_at"])
            deadline_str = item.get("deadline", "")
            deadline_dt = datetime.fromisoformat(deadline_str + "T23:59:59+00:00") if "T" not in deadline_str else datetime.fromisoformat(deadline_str)
            total = (deadline_dt - created).total_seconds()
            elapsed = (now - created).total_seconds()
            progress = elapsed / total if total > 0 else 1.0
        except Exception:
            progress = 0.0

        if progress >= 0.8 and item["status"] in ("pending_acceptance", "in_progress", "under_review"):
            if not last_nudges.get("hard_escalation"):
                next_role_map = {"reviewer": "marketing_lead", "marketing_lead": "vp", "vp": "vp", "ceo": "ceo"}
                current_role = item["reviewer_role"]
                new_role = next_role_map.get(current_role, current_role)
                elapsed_secs = (now - datetime.fromisoformat(item["stage_entered_at"])).total_seconds()
                durations = item.get("stage_durations", {}) or {}
                durations[item["status"]] = durations.get(item["status"], 0) + elapsed_secs

                if new_role != current_role:
                    target = await _pick_next_assignee(item, new_role)
                    target_name = target["name"] if target else f"any {new_role}"
                    activity_additions.append({
                        "ts": now_iso(),
                        "actor": "Agent",
                        "actor_role": "system",
                        "action": "auto_escalated",
                        "note": f"≥80% of timeline elapsed without decision; routed from {current_role} to {target_name}",
                    })
                    update_set = {
                        "status": "escalated",
                        "reviewer_role": new_role,
                        "stage_entered_at": now_iso(),
                        "stage_durations": durations,
                        "updated_at": now_iso(),
                    }
                    if target:
                        update_set.update({
                            "assigned_user_id": target["id"],
                            "assigned_user_name": target["name"],
                            "assigned_user_email": target.get("email"),
                            "assigned_user_designation": target.get("designation", ""),
                            "assigned_user_team": target.get("team", ""),
                        })
                        await create_notification(target["id"], sub_id, "auto_escalation", f"Auto-escalated to you: {item['title']}", f"Reached deadline threshold; previously with {current_role}")
                    await db.submissions.update_one({"id": sub_id}, {"$set": update_set})
                else:
                    activity_additions.append({
                        "ts": now_iso(),
                        "actor": "Agent",
                        "actor_role": "system",
                        "action": "auto_escalated",
                        "note": f"≥80% of timeline elapsed without decision (no higher role available)",
                    })
                new_nudges["hard_escalation"] = today

        if activity_additions or new_nudges != last_nudges:
            full_activity = item.get("activity", []) + activity_additions
            await db.submissions.update_one(
                {"id": sub_id},
                {"$set": {"activity": full_activity, "auto_nudges_sent": new_nudges, "updated_at": now_iso()}},
            )


@api_router.post("/scheduler/run")
async def manual_run_scheduler(user: dict = Depends(get_current_user)):
    """Manually trigger the SLA scan (useful for testing / admin)."""
    await run_sla_check()
    return {"ok": True}


@api_router.get("/")
async def root():
    return {"service": "Content Approval Agent", "status": "ok"}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
