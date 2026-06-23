"""Object storage helpers + file upload/download router (MongoDB GridFS — no external storage account needed)."""
import uuid
from typing import Optional

import jwt
from bson import ObjectId
from gridfs.errors import NoFile
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Header, Query, Response

from core import db, now_iso, get_current_user, JWT_SECRET, JWT_ALG, logger

router = APIRouter()
def init_storage():
    """No-op: GridFS needs no setup step, connects lazily via get_bucket()."""
    pass
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
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # kept smaller than before — free Atlas tier is 512MB total

_bucket = None


def get_bucket() -> AsyncIOMotorGridFSBucket:
    global _bucket
    if _bucket is None:
        _bucket = AsyncIOMotorGridFSBucket(db, bucket_name="uploads")
    return _bucket


@router.post("/upload")
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
    content_type = file.content_type or MIME_TYPES.get(ext, "application/octet-stream")
    bucket = get_bucket()

    try:
        grid_id = await bucket.upload_from_stream(
            filename,
            data,
            metadata={"content_type": content_type, "uploader_id": user["id"], "file_id": file_id},
        )
    except Exception as e:
        logger.error(f"GridFS upload failed: {e}")
        raise HTTPException(status_code=502, detail="File storage upload failed")

    doc = {
        "id": file_id,
        "grid_id": str(grid_id),
        "original_filename": filename,
        "content_type": content_type,
        "size": len(data),
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
    }


@router.get("/files/{file_id}/download")
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

    bucket = get_bucket()
    try:
        stream = await bucket.open_download_stream(ObjectId(record["grid_id"]))
        data = await stream.read()
    except NoFile:
        raise HTTPException(status_code=404, detail="File content missing")
    except Exception as e:
        logger.error(f"GridFS download failed: {e}")
        raise HTTPException(status_code=502, detail="File download failed")

    return Response(
        content=data,
        media_type=record.get("content_type", "application/octet-stream"),
        headers={
            "Content-Disposition": f'inline; filename="{record["original_filename"]}"',
            "Cache-Control": "private, max-age=3600",
        },
    )