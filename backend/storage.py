"""Object storage helpers + file upload/download router."""
import uuid
from typing import Optional

import jwt
import requests
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Header, Query, Response

from core import db, now_iso, get_current_user, EMERGENT_LLM_KEY, JWT_SECRET, JWT_ALG, logger

router = APIRouter()

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
APP_NAME = "govern-approval"
_storage_key: Optional[str] = None

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
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def init_storage() -> str:
    global _storage_key
    if _storage_key:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_LLM_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


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
    path = f"{APP_NAME}/uploads/{user['id']}/{file_id}.{ext}"
    content_type = file.content_type or MIME_TYPES.get(ext, "application/octet-stream")

    result: dict = {}
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
    data: bytes = b""
    ct: str = "application/octet-stream"
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
