"""
Database Initializer — creates all collections + indexes for GOVERN.
Run once on first deploy, or safely re-run anytime (idempotent).
"""
import asyncio
import os
from pathlib import Path

import certifi
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ.get("MONGO_URL", "")
DB_NAME   = os.environ.get("DB_NAME", "govern")

if not MONGO_URL:
    raise RuntimeError("MONGO_URL not set — check your .env file")

async def init_db():
    print(f"Connecting to MongoDB... (db={DB_NAME})")
    client = AsyncIOMotorClient(MONGO_URL, tlsCAFile=certifi.where())
    db = client[DB_NAME]

    await client.admin.command("ping")
    print("✅ Connected to MongoDB Atlas")

    existing = await db.list_collection_names()
    print(f"   Existing collections: {existing or '(none yet)'}")

    # users
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.users.create_index("role")
    print("✅ users — indexes ready")

    # submissions
    await db.submissions.create_index("id", unique=True)
    await db.submissions.create_index("status")
    await db.submissions.create_index("submitter_id")
    await db.submissions.create_index("assigned_user_id")
    await db.submissions.create_index("reviewer_role")
    await db.submissions.create_index("created_at")
    await db.submissions.create_index([("status", 1), ("created_at", -1)])
    print("✅ submissions — indexes ready")

    # notifications
    await db.notifications.create_index("id", unique=True)
    await db.notifications.create_index("user_id")
    await db.notifications.create_index("submission_id")
    await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
    print("✅ notifications — indexes ready")

    # files
    await db.files.create_index("id", unique=True)
    await db.files.create_index("uploader_id")
    print("✅ files — indexes ready")

    final = await db.list_collection_names()
    print(f"\n🎉 Done! Collections: {sorted(final)}")
    client.close()

if __name__ == "__main__":
    asyncio.run(init_db())