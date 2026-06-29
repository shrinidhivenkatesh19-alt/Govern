"""Auth router."""
import uuid

from fastapi import APIRouter, HTTPException, Depends

from core import db, now_iso, hash_password, verify_password, make_token, get_current_user, logger
from models import RegisterIn, LoginIn
from email_service import send_onboarding

router = APIRouter()


@router.post("/auth/register")
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
    user_payload = {
        "id": user_id, "email": body.email.lower(), "name": body.name,
        "role": body.role, "team": doc["team"], "designation": doc["designation"],
    }
    # Introduction email — must await on serverless (background tasks are dropped after response)
    logger.info(f"Sending onboarding email to {user_payload['email']}")
    try:
        eid = await send_onboarding(user_payload)
        if eid:
            logger.info(f"Onboarding email sent id={eid}")
        else:
            logger.warning(f"Onboarding email not sent for {user_payload['email']} — check RESEND_API_KEY / SENDER_EMAIL")
    except Exception as e:
        logger.error(f"Onboarding email failed for {user_payload['email']}: {e!r}")
    return {"token": token, "user": user_payload}


@router.post("/auth/login")
async def login(body: LoginIn):
    user = await db.users.find_one({"email": body.email.lower()})
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = make_token(user["id"], user["email"], user["role"])
    return {
        "token": token,
        "user": {
            "id": user["id"], "email": user["email"], "name": user["name"],
            "role": user["role"], "team": user.get("team", ""),
            "designation": user.get("designation", ""),
        },
    }


@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@router.get("/users")
async def list_users(user: dict = Depends(get_current_user)):
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(500)
    return users
