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
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, field_validator

from app.config import settings
from app.dependencies import get_current_user
from app.models import UserProfile
from app.rate_limit import limiter
from app.services import aws_store, slug_store
from app.services import analytics_store
from app.services.portfolio_insights import evaluate_portfolio_insights

router = APIRouter(tags=["portfolio"])

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,48}[a-z0-9]$")


def _template_dir() -> Path:
    return Path(settings.PORTFOLIO_TEMPLATE_DIR).resolve()


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


class AnalyticsEventRequest(BaseModel):
    slug: str
    event_type: Literal[
        "portfolio_view",
        "pdf_click",
        "linkedin_click",
        "github_click",
        "contact_click",
    ]

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        v = v.strip().lower()
        if not _SLUG_RE.match(v):
            raise ValueError("Invalid slug")
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


@router.get("/api/portfolio/insights")
async def get_portfolio_insights(current_user: UserProfile = Depends(get_current_user)):
    meta = await slug_store.get_user_meta(current_user.user_key)
    resume_key = meta.get("resume_key") or meta.get("resume_url")
    if not resume_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No resume uploaded yet")

    resume = await aws_store.read_resume_json(resume_key)
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No resume uploaded yet")

    insights = evaluate_portfolio_insights(resume, meta)
    slug = meta.get("slug")
    analytics = {
        "slug": slug,
        "range_days": 30,
        "totals": {
            "views": 0,
            "unique_visitors": 0,
            "pdf_click": 0,
            "linkedin_click": 0,
            "github_click": 0,
            "contact_click": 0,
        },
        "daily": [],
    }
    if slug:
        analytics = await analytics_store.get_analytics(slug, days=30)

    return {"insights": insights, "analytics": analytics}


@router.post("/api/portfolio/analytics/event")
@limiter.limit("120/minute")
async def record_analytics_event(request: Request, body: AnalyticsEventRequest):
    entry = await slug_store.get_slug_entry(body.slug)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found")

    user_agent = request.headers.get("user-agent", "")
    xff = request.headers.get("x-forwarded-for")
    client_ip = request.client.host if request.client else "unknown"
    await analytics_store.record_event(
        slug=body.slug,
        event_type=body.event_type,
        request_ip=client_ip,
        user_agent=user_agent,
        x_forwarded_for=xff,
    )
    return {"status": "ok"}


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

    analytics_script = f"""
<script>
(function() {{
    var slug = {slug!r};
    var endpoint = '/api/portfolio/analytics/event';
    function track(eventType) {{
        try {{
            fetch(endpoint, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                keepalive: true,
                body: JSON.stringify({{ slug: slug, event_type: eventType }})
            }});
        }} catch (e) {{}}
    }}

    track('portfolio_view');

    document.addEventListener('click', function(e) {{
        var node = e.target;
        while (node && node.tagName !== 'A') node = node.parentElement;
        if (!node || !node.getAttribute) return;
        var href = (node.getAttribute('href') || '').toLowerCase();
        if (!href) return;
        if (href.endsWith('.pdf')) return track('pdf_click');
        if (href.indexOf('linkedin.com') !== -1) return track('linkedin_click');
        if (href.indexOf('github.com') !== -1) return track('github_click');
        if (href.indexOf('mailto:') === 0) return track('contact_click');
    }}, true);
}})();
</script>
"""

    if "</body>" in html:
        html = html.replace("</body>", analytics_script + "\n</body>")
    else:
        html = html + analytics_script

    return HTMLResponse(content=html)
