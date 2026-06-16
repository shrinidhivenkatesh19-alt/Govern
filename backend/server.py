from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
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
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal
from datetime import datetime, timezone, timedelta

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
Role = Literal["submitter", "reviewer", "marketing_lead", "ceo"]
SubmissionStatus = Literal["scored", "under_review", "approved", "revision_requested", "escalated", "live"]
ContentType = Literal["social_post", "blog_article", "email_campaign", "press_release", "product_announcement", "partnership", "pricing_update", "ad_creative"]
Tier = Literal["auto_approve", "product_only", "ceo_required"]


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: Role = "submitter"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ScoreIn(BaseModel):
    title: str
    content_type: ContentType
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


class SubmissionCreate(BaseModel):
    title: str
    content_type: ContentType
    brief: str
    content: str
    deadline: str  # ISO date
    score_result: ScoreResult
    chosen_tier: Tier  # may differ from recommended (human override)


class ActionIn(BaseModel):
    note: Optional[str] = ""


class RevisionIn(BaseModel):
    note: str


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
        "password_hash": hash_password(body.password),
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    token = make_token(user_id, body.email.lower(), body.role)
    return {"token": token, "user": {"id": user_id, "email": body.email.lower(), "name": body.name, "role": body.role}}


@api_router.post("/auth/login")
async def login(body: LoginIn):
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = make_token(user["id"], user["email"], user["role"])
    return {"token": token, "user": {"id": user["id"], "email": user["email"], "name": user["name"], "role": user["role"]}}


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
Content Type: {body.content_type}

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


# ---------- Submissions ----------
def tier_to_status(tier: Tier) -> SubmissionStatus:
    if tier == "auto_approve":
        return "approved"
    return "under_review"


def tier_to_reviewer_role(tier: Tier) -> str:
    return {"auto_approve": "system", "product_only": "reviewer", "ceo_required": "ceo"}[tier]


@api_router.post("/submissions")
async def create_submission(body: SubmissionCreate, user: dict = Depends(get_current_user)):
    sub_id = str(uuid.uuid4())
    status_val = tier_to_status(body.chosen_tier)
    reviewer_role = tier_to_reviewer_role(body.chosen_tier)
    now = now_iso()

    activity = [
        {"ts": now, "actor": user["name"], "actor_role": user["role"], "action": "submitted", "note": f"Submitted as {body.chosen_tier}"},
    ]
    if status_val == "approved":
        activity.append({"ts": now, "actor": "Agent", "actor_role": "system", "action": "auto_approved", "note": "Routine content, auto-approved by agent"})

    doc = {
        "id": sub_id,
        "title": body.title,
        "content_type": body.content_type,
        "brief": body.brief,
        "content": body.content,
        "deadline": body.deadline,
        "score_result": body.score_result.model_dump(),
        "chosen_tier": body.chosen_tier,
        "reviewer_role": reviewer_role,
        "status": status_val,
        "submitter_id": user["id"],
        "submitter_name": user["name"],
        "created_at": now,
        "updated_at": now,
        "stage_entered_at": now,
        "stage_durations": {},  # status -> seconds spent
        "activity": activity,
    }
    await db.submissions.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.get("/submissions")
async def list_submissions(user: dict = Depends(get_current_user), status_filter: Optional[str] = None):
    query = {}
    if status_filter:
        query["status"] = status_filter
    items = await db.submissions.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    # Compute idle days
    now = datetime.now(timezone.utc)
    for it in items:
        entered = datetime.fromisoformat(it["stage_entered_at"])
        it["idle_hours"] = round((now - entered).total_seconds() / 3600, 1)
        it["idle_days"] = round(it["idle_hours"] / 24, 2)
        it["needs_nudge"] = it["idle_hours"] >= 48 and it["status"] in ("under_review", "escalated")
        it["needs_escalation"] = it["idle_hours"] >= 72 and it["status"] == "under_review"
    return items


@api_router.get("/submissions/{sub_id}")
async def get_submission(sub_id: str, user: dict = Depends(get_current_user)):
    item = await db.submissions.find_one({"id": sub_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Submission not found")
    now = datetime.now(timezone.utc)
    entered = datetime.fromisoformat(item["stage_entered_at"])
    item["idle_hours"] = round((now - entered).total_seconds() / 3600, 1)
    item["idle_days"] = round(item["idle_hours"] / 24, 2)
    return item


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


@api_router.post("/submissions/{sub_id}/approve")
async def approve(sub_id: str, body: ActionIn, user: dict = Depends(get_current_user)):
    if user["role"] not in ("reviewer", "marketing_lead", "ceo"):
        raise HTTPException(status_code=403, detail="Not authorized to approve")
    return await _transition(sub_id, "approved", user, "approved", body.note or "")


@api_router.post("/submissions/{sub_id}/request-revision")
async def request_revision(sub_id: str, body: RevisionIn, user: dict = Depends(get_current_user)):
    if user["role"] not in ("reviewer", "marketing_lead", "ceo"):
        raise HTTPException(status_code=403, detail="Not authorized")
    return await _transition(sub_id, "revision_requested", user, "requested_revision", body.note)


@api_router.post("/submissions/{sub_id}/escalate")
async def escalate(sub_id: str, body: ActionIn, user: dict = Depends(get_current_user)):
    return await _transition(sub_id, "escalated", user, "escalated", body.note or "Escalated to CEO")


@api_router.post("/submissions/{sub_id}/mark-live")
async def mark_live(sub_id: str, body: ActionIn, user: dict = Depends(get_current_user)):
    return await _transition(sub_id, "live", user, "marked_live", body.note or "Published live")


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
    return await db.submissions.find_one({"id": sub_id}, {"_id": 0})


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
