"""Shared core: env, db client, JWT, auth dependency, helpers."""
import os
import certifi
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
try:
    from motor.motor_asyncio import AsyncIOMotorClient
    _motor_available = True
except Exception:
    _motor_available = False

_use_mock = not _motor_available
if _use_mock:
    try:
        import mongomock_motor
    except ImportError:
        raise RuntimeError("motor is unavailable and mongomock_motor is not installed")

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_DAYS = int(os.environ.get("JWT_EXPIRE_DAYS", "7"))
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL")  # Slack webhook URL, despite the name

if _use_mock:
    client = mongomock_motor.AsyncMongoMockClient()  # local dev only, no persistence
else:
    client = AsyncIOMotorClient(MONGO_URL, tlsCAFile=certifi.where())
db = client[DB_NAME]

security = HTTPBearer()
logger = logging.getLogger("govern")

# Domain constants
DECISION_ALLOWED_FROM = {"pending_acceptance", "in_progress", "under_review", "escalated"}
MAX_CHAIN_DEPTH = 10


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
