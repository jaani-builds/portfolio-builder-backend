from __future__ import annotations

"""
Portfolio slug management and live portfolio serving.

GET  /api/portfolio/slug       – get current user's slug
PUT  /api/portfolio/slug       – set / update slug
GET  /{slug}/                  – serve portfolio HTML (template)
GET  /{slug}/assets/{path}     – serve template static assets
GET  /{slug}/data/resume.json  – serve resume JSON from S3
"""

import re
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, field_validator

from app.config import settings
from app.dependencies import get_current_user
from app.models import UserProfile
from app.rate_limit import limiter
from app.services import aws_store, slug_store

router = APIRouter(tags=["portfolio"])

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,48}[a-z0-9]$")


def _template_dir() -> Path:
    return Path(settings.PORTFOLIO_TEMPLATE_DIR).resolve()


def _live_example_json_path() -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "resume.daniel-kim.json"


class SlugRequest(BaseModel):
    slug: str
    auto_suffix_on_conflict: bool = False

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        v = v.strip().lower()
        # Auto-convert spaces to hyphens
        v = re.sub(r'\s+', '-', v)
        # Collapse multiple consecutive hyphens into one
        v = re.sub(r'-+', '-', v)
        # Strip leading/trailing hyphens
        v = v.strip('-')
        if not _SLUG_RE.match(v):
            raise ValueError(
                "Slug must be 3–50 lowercase alphanumeric characters or hyphens, "
                "starting and ending with a letter or digit."
            )
        if v in settings.RESERVED_SLUGS:
            raise ValueError(f"'{v}' is a reserved slug name")
        return v


def _slug_candidates(base: str, limit: int = 5) -> list[str]:
    candidates: list[str] = []
    for i in range(2, 100):
        cand = f"{base}-{i}"
        if len(cand) <= 50:
            candidates.append(cand)
        if len(candidates) >= limit:
            break
    return candidates


async def _first_available_slug(base: str) -> str | None:
    for cand in _slug_candidates(base, limit=40):
        existing = await slug_store.get_slug_entry(cand)
        if not existing:
            return cand
    return None


# ── Slug management ──────────────────────────────────────────────────────────


@router.get("/api/portfolio/slug")
async def get_slug(current_user: UserProfile = Depends(get_current_user)):
    meta = await slug_store.get_user_meta(current_user.user_key)
    return {"slug": meta.get("slug")}


@router.put("/api/portfolio/slug")
async def set_slug(
    body: SlugRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    meta = await slug_store.get_user_meta(current_user.user_key)
    resume_key = meta.get("resume_key") or meta.get("resume_url", "")
    old_slug = meta.get("slug")

    if not resume_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload your resume before choosing a public slug",
        )

    try:
        await slug_store.claim_slug(
            slug=body.slug,
            user_key=current_user.user_key,
            resume_key=resume_key,
            old_slug=old_slug,
        )
    except ValueError:
        if body.auto_suffix_on_conflict:
            resolved = await _first_available_slug(body.slug)
            if not resolved:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="That slug is already taken",
                )
            await slug_store.claim_slug(
                slug=resolved,
                user_key=current_user.user_key,
                resume_key=resume_key,
                old_slug=old_slug,
            )
            return {
                "slug": resolved,
                "url": f"/{resolved}/",
                "requested_slug": body.slug,
                "auto_suffixed": True,
            }
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That slug is already taken")

    return {"slug": body.slug, "url": f"/{body.slug}/"}


@router.get("/api/portfolio/slug/suggestions")
@limiter.limit("30/minute")
async def slug_suggestions(request: Request, slug: str):
    base = slug.strip().lower()
    if not _SLUG_RE.match(base) or base in settings.RESERVED_SLUGS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid slug")

    suggestions: list[str] = []
    for cand in _slug_candidates(base, limit=8):
        if await slug_store.get_slug_entry(cand) is None:
            suggestions.append(cand)
        if len(suggestions) >= 5:
            break

    return {"base": base, "suggestions": suggestions}


# ── Portfolio data lookup ────────────────────────────────────────────────────


async def _get_resume_for_slug(slug: str) -> dict:
    """Fetch resume data for a public slug. Raises 404 if not found."""
    entry = await slug_store.get_slug_entry(slug)
    if not entry:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    resume_key = entry.get("resume_url") or entry.get("resume_key")
    if resume_key:
        data = await aws_store.read_resume_json(resume_key)
        if data is not None:
            return data

    raise HTTPException(status_code=404, detail="Portfolio has no data yet")


# ── Public portfolio serving ─────────────────────────────────────────────────


@router.get("/live-example/data/resume.json")
async def serve_live_example_resume_json():
    source = _live_example_json_path()
    if not source.exists():
        raise HTTPException(status_code=404, detail="Live example data not found")

    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(status_code=500, detail="Live example data is invalid")

    data["publicUrl"] = "/live-example/"
    return JSONResponse(content=data)


@router.get("/live-example/assets/{asset_path:path}")
async def serve_live_example_asset(asset_path: str):
    template_dir = _template_dir()
    target = (template_dir / "assets" / asset_path).resolve()
    if not target.is_relative_to(template_dir):
        raise HTTPException(status_code=400, detail="Invalid asset path")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(target)


@router.get("/live-example/", response_class=HTMLResponse)
@router.get("/live-example", response_class=HTMLResponse)
async def serve_live_example_portfolio():
    # Verify example data exists before serving template shell
    if not _live_example_json_path().exists():
        raise HTTPException(status_code=404, detail="Live example data not found")

    template_dir = _template_dir()
    index_path = template_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=503, detail="Portfolio template not found — check PORTFOLIO_TEMPLATE_DIR")

    html = index_path.read_text(encoding="utf-8")
    html = html.replace('href="assets/', 'href="/live-example/assets/')
    html = html.replace("href='assets/", "href='/live-example/assets/")
    html = html.replace('src="assets/', 'src="/live-example/assets/')
    html = html.replace("src='assets/", "src='/live-example/assets/")

    return HTMLResponse(content=html)


@router.get("/{slug}/data/resume.json")
async def serve_resume_json(slug: str):
    data = await _get_resume_for_slug(slug)
    data["publicUrl"] = f"/{slug}/"
    return JSONResponse(content=data)


@router.get("/{slug}/assets/{asset_path:path}")
async def serve_template_asset(slug: str, asset_path: str):
    template_dir = _template_dir()
    target = (template_dir / "assets" / asset_path).resolve()
    # Prevent path traversal
    if not target.is_relative_to(template_dir):
        raise HTTPException(status_code=400, detail="Invalid asset path")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(target)


@router.get("/{slug}/", response_class=HTMLResponse)
@router.get("/{slug}", response_class=HTMLResponse)
async def serve_portfolio(slug: str):
    # Verify slug exists (raises 404 otherwise)
    await _get_resume_for_slug(slug)

    template_dir = _template_dir()
    index_path = template_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=503, detail="Portfolio template not found — check PORTFOLIO_TEMPLATE_DIR")

    html = index_path.read_text(encoding="utf-8")
    html = html.replace('href="assets/', f'href="/{slug}/assets/')
    html = html.replace("href='assets/", f"href='/{slug}/assets/")
    html = html.replace('src="assets/', f'src="/{slug}/assets/')
    html = html.replace("src='assets/", f"src='/{slug}/assets/")

    return HTMLResponse(content=html)
