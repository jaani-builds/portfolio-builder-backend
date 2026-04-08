"""
Short-lived one-time exchange codes for secure JWT delivery.

After OAuth callback, backend generates a random code (TTL 30 s).
Frontend exchanges it for the JWT via GET /api/auth/exchange?code=<code>.

This prevents the JWT appearing in server access logs or browser history,
as the hash fragment (#/callback?code=...) is never sent to the server.

Codes are persisted in DynamoDB so they survive Lambda cold starts.
"""

from __future__ import annotations

import secrets
from typing import Optional

from app.services import aws_store

_CODE_TTL = 30  # seconds


async def issue(jwt: str) -> str:
    """Generate a one-time exchange code for the given JWT and persist in DynamoDB."""
    code = secrets.token_urlsafe(32)
    await aws_store.save_exchange_code(code, jwt, ttl_seconds=_CODE_TTL)
    return code


async def redeem(code: str) -> Optional[str]:
    """Return JWT and atomically delete the code (one-time use). None if expired or invalid."""
    return await aws_store.get_and_delete_exchange_code(code)
