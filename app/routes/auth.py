from __future__ import annotations

"""Authentication routes using OAuth providers (GitHub, Google, LinkedIn)."""

from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
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

_GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"

_LINKEDIN_AUTHORIZE = "https://www.linkedin.com/oauth/v2/authorization"
_LINKEDIN_TOKEN = "https://www.linkedin.com/oauth/v2/accessToken"
_LINKEDIN_USERINFO = "https://api.linkedin.com/v2/userinfo"


def _cookie_secure() -> bool:
    return settings.SESSION_COOKIE_SECURE or settings.APP_BASE_URL.startswith("https://")


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_cookie_secure(),
        samesite=settings.SESSION_COOKIE_SAMESITE,
        max_age=settings.JWT_EXPIRY_DAYS * 24 * 60 * 60,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        httponly=True,
        secure=_cookie_secure(),
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path="/",
    )


def _callback_uri(provider: str) -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/api/auth/callback/{provider}"


def _user_key(provider: str, provider_user_id: str) -> str:
    return f"{provider}_{provider_user_id}"


def _provider_client_id(provider: str) -> str:
    if provider == "github":
        return settings.GITHUB_CLIENT_ID
    if provider == "google":
        return settings.GOOGLE_CLIENT_ID
    if provider == "linkedin":
        return settings.LINKEDIN_CLIENT_ID
    return ""


def _provider_client_secret(provider: str) -> str:
    if provider == "github":
        return settings.GITHUB_CLIENT_SECRET
    if provider == "google":
        return settings.GOOGLE_CLIENT_SECRET
    if provider == "linkedin":
        return settings.LINKEDIN_CLIENT_SECRET
    return ""


async def _redirect_with_code(jwt: str) -> RedirectResponse:
    """Issue one-time exchange code and redirect browser to frontend callback hash."""
    code = await exchange_store.issue(jwt)
    return RedirectResponse(f"{settings.FRONTEND_URL}/#/callback?code={code}")


def _require_provider_creds(provider: str) -> tuple[str, str]:
    client_id = _provider_client_id(provider)
    client_secret = _provider_client_secret(provider)
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{provider.title()} OAuth is not configured: missing client credentials",
        )
    return client_id, client_secret


@router.get("/github")
@limiter.limit("10/minute")
async def login_github(request: Request):
    client_id = _provider_client_id("github")
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub OAuth is not configured: missing GITHUB_CLIENT_ID",
        )

    state = generate_state("github")
    params = {
        "client_id": client_id,
        "redirect_uri": _callback_uri("github"),
        "scope": "read:user user:email",
        "state": state,
    }
    return RedirectResponse(f"{_GITHUB_AUTHORIZE}?{urlencode(params)}")


@router.get("/google")
@limiter.limit("10/minute")
async def login_google(request: Request):
    client_id = _provider_client_id("google")
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured: missing GOOGLE_CLIENT_ID",
        )

    state = generate_state("google")
    params = {
        "client_id": client_id,
        "redirect_uri": _callback_uri("google"),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }
    return RedirectResponse(f"{_GOOGLE_AUTHORIZE}?{urlencode(params)}")


@router.get("/linkedin")
@limiter.limit("10/minute")
async def login_linkedin(request: Request):
    client_id = _provider_client_id("linkedin")
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LinkedIn OAuth is not configured: missing LINKEDIN_CLIENT_ID",
        )

    state = generate_state("linkedin")
    params = {
        "client_id": client_id,
        "redirect_uri": _callback_uri("linkedin"),
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
    }
    return RedirectResponse(f"{_LINKEDIN_AUTHORIZE}?{urlencode(params)}")


@router.get("/callback/github")
@limiter.limit("10/minute")
async def callback_github(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
):
    client_id, client_secret = _require_provider_creds("github")
    if not verify_state(state, "github"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")

    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                _GITHUB_TOKEN,
                headers={"Accept": "application/json"},
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": _callback_uri("github"),
                },
            )
            if token_resp.status_code != 200:
                raise HTTPException(status_code=502, detail="Failed to exchange GitHub token")

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
                raise HTTPException(status_code=502, detail="Failed to fetch GitHub profile")
            profile = user_resp.json()

            emails_resp = await client.get(_GITHUB_EMAILS, headers=headers)
            emails = emails_resp.json() if emails_resp.status_code == 200 else []
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"GitHub connectivity error: {exc}") from exc

    provider_user_id = profile.get("id")
    if not provider_user_id:
        raise HTTPException(status_code=502, detail="GitHub profile missing id")

    email = profile.get("email")
    if not email and isinstance(emails, list):
        primary = next((e for e in emails if e.get("primary") and e.get("verified")), None)
        email = primary.get("email") if primary else None

    user_key = _user_key("github", str(provider_user_id))
    name = profile.get("name") or profile.get("login") or ""
    avatar_url = profile.get("avatar_url")

    jwt = create_token(user_key, email, name, avatar_url=avatar_url)
    return await _redirect_with_code(jwt)


@router.get("/callback/google")
@limiter.limit("10/minute")
async def callback_google(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
):
    client_id, client_secret = _require_provider_creds("google")
    if not verify_state(state, "google"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")

    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                _GOOGLE_TOKEN,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": _callback_uri("google"),
                    "grant_type": "authorization_code",
                },
            )
            if token_resp.status_code != 200:
                raise HTTPException(status_code=502, detail="Failed to exchange Google token")

            access_token = token_resp.json().get("access_token")
            if not access_token:
                raise HTTPException(status_code=502, detail="No access token in Google response")

            user_resp = await client.get(
                _GOOGLE_USERINFO,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if user_resp.status_code != 200:
                raise HTTPException(status_code=502, detail="Failed to fetch Google profile")
            profile = user_resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Google connectivity error: {exc}") from exc

    provider_user_id = profile.get("sub")
    if not provider_user_id:
        raise HTTPException(status_code=502, detail="Google profile missing subject")

    user_key = _user_key("google", str(provider_user_id))
    email = profile.get("email")
    name = profile.get("name") or profile.get("given_name") or ""
    avatar_url = profile.get("picture")

    jwt = create_token(user_key, email, name, avatar_url=avatar_url)
    return await _redirect_with_code(jwt)


@router.get("/callback/linkedin")
@limiter.limit("10/minute")
async def callback_linkedin(
    request: Request,
    code: str | None = Query(None),
    state: str = Query(...),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
):
    if error:
        detail = f"LinkedIn OAuth error: {error}"
        if error_description:
            detail = f"{detail} ({error_description})"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LinkedIn OAuth callback missing authorization code",
        )

    client_id, client_secret = _require_provider_creds("linkedin")
    if not verify_state(state, "linkedin"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")

    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                _LINKEDIN_TOKEN,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": _callback_uri("linkedin"),
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            if token_resp.status_code != 200:
                raise HTTPException(status_code=502, detail="Failed to exchange LinkedIn token")

            access_token = token_resp.json().get("access_token")
            if not access_token:
                raise HTTPException(status_code=502, detail="No access token in LinkedIn response")

            user_resp = await client.get(
                _LINKEDIN_USERINFO,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            if user_resp.status_code != 200:
                raise HTTPException(status_code=502, detail="Failed to fetch LinkedIn profile")
            profile = user_resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"LinkedIn connectivity error: {exc}") from exc

    provider_user_id = profile.get("sub")
    if not provider_user_id:
        raise HTTPException(status_code=502, detail="LinkedIn profile missing subject")

    user_key = _user_key("linkedin", str(provider_user_id))
    email = profile.get("email")
    name = profile.get("name") or profile.get("given_name") or ""
    avatar = profile.get("picture")
    avatar_url = avatar if isinstance(avatar, str) else None

    jwt = create_token(user_key, email, name, avatar_url=avatar_url)
    return await _redirect_with_code(jwt)


# ── Exchange code → JWT ───────────────────────────────────────────────────────

@router.get("/exchange")
@limiter.limit("10/minute")
async def exchange_code(request: Request, response: Response, code: str = Query(...)):
    """Redeem a one-time 30-second exchange code for a session JWT."""
    jwt = await exchange_store.redeem(code)
    if jwt is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired exchange code",
        )
    _set_session_cookie(response, jwt)
    response.headers["Cache-Control"] = "no-store"
    return {"token": jwt}


# ── Logout ───────────────────────────────────────────────────────────────────

@router.post("/logout")
async def logout(response: Response, current_user: UserProfile = Depends(get_current_user)):
    """Client-side JWT logout."""
    _clear_session_cookie(response)
    response.headers["Cache-Control"] = "no-store"
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
