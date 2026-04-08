"""
JWT helpers for issuing and verifying user session tokens.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

from app.config import settings


def create_token(
    user_key: str,
    email: Optional[str],
    name: Optional[str],
    avatar_url: Optional[str] = None,
) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=settings.JWT_EXPIRY_DAYS)
    payload = {
        "sub": user_key,
        "email": email or "",
        "name": name or "",
        "avatar_url": avatar_url or "",
        "exp": exp,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Raises JWTError on invalid / expired token."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
