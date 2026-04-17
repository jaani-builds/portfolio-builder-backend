from __future__ import annotations

"""
FastAPI dependency: resolve current authenticated user from Bearer token.
No database needed — user identity is carried in the JWT, metadata from local storage.
"""

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.models import UserProfile
from app.config import settings
from app.services import slug_store
from app.services.jwt_service import decode_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session_cookie: str | None = Cookie(default=None, alias=settings.SESSION_COOKIE_NAME),
) -> UserProfile:
    try:
        token = credentials.credentials if credentials else session_cookie
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )
        payload = decode_token(token)
        user_key: str = payload["sub"]
    except (JWTError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # Derive provider / provider_user_id from user_key convention: "{provider}_{id}"
    parts = user_key.split("_", 1)
    provider = parts[0] if len(parts) == 2 else "unknown"
    provider_user_id = parts[1] if len(parts) == 2 else user_key

    meta = await slug_store.get_user_meta(user_key)

    return UserProfile(
        user_key=user_key,
        provider=provider,
        provider_user_id=provider_user_id,
        email=payload.get("email"),
        name=payload.get("name"),
        avatar_url=payload.get("avatar_url") or None,
        slug=meta.get("slug"),
    )

