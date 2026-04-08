from __future__ import annotations

"""
Resume upload and retrieval routes.

POST /api/resume/upload  – parse text, write to S3
GET  /api/resume         – return stored resume JSON
PUT  /api/resume/json    – overwrite resume JSON (manual edits)
"""

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, field_validator

from app.dependencies import get_current_user
from app.models import UserProfile
from app.rate_limit import limiter
from app.services import aws_store, slug_store
from app.services.resume_parser import parse_resume

router = APIRouter(prefix="/api/resume", tags=["resume"])

_MAX_RESUME_CHARS = 50_000
_MAX_PDF_BYTES = 10 * 1024 * 1024


class UploadRequest(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Resume text must not be empty")
        if len(stripped) > _MAX_RESUME_CHARS:
            raise ValueError(f"Resume text exceeds {_MAX_RESUME_CHARS} character limit")
        return stripped


class ResumeJsonRequest(BaseModel):
    resume_json: dict


async def _write_resume(user: UserProfile, parsed: dict) -> None:
    """Write parsed resume to S3 and sync metadata."""

    meta = await slug_store.get_user_meta(user.user_key)
    resume_key = await aws_store.put_resume_json(
        user_key=user.user_key,
        resume_json=parsed,
    )
    meta["resume_key"] = resume_key
    await slug_store.save_user_meta(user.user_key, meta)

    # Keep public slug mapping in sync with the latest resume location.
    if meta.get("slug"):
        await slug_store.claim_slug(
            slug=meta["slug"],
            user_key=user.user_key,
            resume_key=resume_key,
            old_slug=meta["slug"],
        )


async def _read_resume(user: UserProfile) -> dict:
    meta = await slug_store.get_user_meta(user.user_key)
    resume_key = meta.get("resume_key") or meta.get("resume_url")
    if resume_key:
        data = await aws_store.read_resume_json(resume_key)
        if data is not None:
            return data
    raise HTTPException(status_code=404, detail="No resume uploaded yet")


@router.post("/upload", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def upload_resume(
    request: Request,
    body: UploadRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    parsed = parse_resume(body.text)
    await _write_resume(current_user, parsed)
    return {"parsed": parsed}


@router.get("")
async def get_resume(current_user: UserProfile = Depends(get_current_user)):
    return await _read_resume(current_user)


@router.put("/json", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def update_resume_json(
    request: Request,
    body: ResumeJsonRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    await _write_resume(current_user, body.resume_json)
    return {"status": "updated"}


@router.post("/pdf", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def upload_resume_pdf(
    request: Request,
    file: UploadFile = File(...),
    current_user: UserProfile = Depends(get_current_user),
):
    filename = file.filename or "resume.pdf"
    if not filename.lower().endswith(".pdf") and file.content_type != "application/pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please upload a PDF file")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded PDF is empty")
    if len(content) > _MAX_PDF_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PDF exceeds 10 MB limit")

    pdf_url = await aws_store.put_resume_pdf(
        user_key=current_user.user_key,
        filename=filename,
        content=content,
        content_type=(file.content_type or "application/pdf"),
    )
    return {"pdfUrl": pdf_url}
