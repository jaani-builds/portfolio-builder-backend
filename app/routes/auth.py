from __future__ import annotations

"""Authentication routes using GitHub OAuth."""

from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from app.config import settings
from app.dependencies import get_current_user
from app.models import UserProfile
from app.rate_limit import limiter
from app.services import exchange_store
from app.services.jwt_service import create_token
from app.services.oauth_service import generate_state, verify_state

router = APIRouter(prefix="/api/auth", tags=["auth"])

_GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
_GITHUB_USER = "https://api.github.com/user"
_GITHUB_EMAILS = "https://api.github.com/user/emails"


def _callback_uri() -> str:
    return f"{settings.APP_BASE_URL}/api/auth/callback/github"


def _user_key(github_id: int) -> str:
    return f"github_{github_id}"


async def _redirect_with_code(jwt: str) -> RedirectResponse:
    """
    Issue a one-time exchange code and redirect browser to frontend.
    Hash fragment (#/callback?code=…) is never sent to any server,
    keeping the code out of access logs and Referer headers.
    """
    code = await exchange_store.issue(jwt)
    return RedirectResponse(f"{settings.FRONTEND_URL}/#/callback?code={code}")


# ── GitHub OAuth ─────────────────────────────────────────────────────────────

@router.get("/github")
@limiter.limit("10/minute")
async def login_github(request: Request):
    if not settings.GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub OAuth is not configured: missing GITHUB_CLIENT_ID",
        )

    state = generate_state("github")
    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": _callback_uri(),
        "scope": "read:user user:email",
        "state": state,
    }
    return RedirectResponse(f"{_GITHUB_AUTHORIZE}?{urlencode(params)}")


@router.get("/callback/github")
@limiter.limit("10/minute")
async def callback_github(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
):
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub OAuth is not configured: missing client credentials",
        )

    if not verify_state(state, "github"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")

    try:
        async with httpx.AsyncClient(verify=(False if settings.AWS_INSECURE_SSL else True)) as client:
            token_resp = await client.post(
                _GITHUB_TOKEN,
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": _callback_uri(),
                },
            )
            if token_resp.status_code != 200:
                raise HTTPException(status_code=502, detail="Failed to exchange OAuth token")

            access_token = token_resp.json().get("access_token")
            if not access_token:
                raise HTTPException(status_code=502, detail="No access token in GitHub response")

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            user_resp = await client.get(_GITHUB_USER, headers=headers)
            if user_resp.status_code != 200:
                raise HTTPException(status_code=502, detail="Failed to fetch user profile")
            profile = user_resp.json()

            emails_resp = await client.get(_GITHUB_EMAILS, headers=headers)
            emails = emails_resp.json() if emails_resp.status_code == 200 else []
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"GitHub connectivity error: {exc}") from exc

    github_id = profile.get("id")
    if not github_id:
        raise HTTPException(status_code=502, detail="GitHub profile missing id")

    email = profile.get("email")
    if not email and isinstance(emails, list):
        primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
        email = primary.get("email") if primary else None

    user_key = _user_key(github_id)
    name = profile.get("name") or profile.get("login") or ""
    avatar_url = profile.get("avatar_url")

    jwt = create_token(user_key, email, name, avatar_url=avatar_url)
    return await _redirect_with_code(jwt)


# ── Exchange code → JWT ───────────────────────────────────────────────────────

@router.get("/exchange")
@limiter.limit("10/minute")
async def exchange_code(request: Request, code: str = Query(...)):
    """Redeem a one-time 30-second exchange code for a session JWT."""
    jwt = await exchange_store.redeem(code)
    if jwt is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired exchange code",
        )
    return {"token": jwt}


# ── Logout ───────────────────────────────────────────────────────────────────

@router.post("/logout")
async def logout(current_user: UserProfile = Depends(get_current_user)):
    """Client-side JWT logout."""
    return {"status": "logged out"}


# ── Me ───────────────────────────────────────────────────────────────────────

@router.get("/me")
async def me(current_user: UserProfile = Depends(get_current_user)):
    return {
        "user_key": current_user.user_key,
        "email": current_user.email,
        "name": current_user.name,
        "avatar_url": current_user.avatar_url,
        "provider": current_user.provider,
        "slug": current_user.slug,
    }
