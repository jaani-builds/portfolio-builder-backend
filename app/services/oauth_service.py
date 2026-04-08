"""
OAuth helpers: state generation/verification and token exchange.
"""

import hashlib
import hmac
import json
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode

from app.config import settings


# ── Stateless CSRF state token ───────────────────────────────────────────────

def _sign(payload: bytes) -> str:
    return hmac.new(
        settings.JWT_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()


def generate_state(provider: str) -> str:
    payload = json.dumps({"provider": provider, "exp": int(time.time()) + 300}).encode()
    b64 = urlsafe_b64encode(payload).decode().rstrip("=")
    sig = _sign(payload)[:32]
    return f"{b64}.{sig}"


def verify_state(state: str, expected_provider: str) -> bool:
    try:
        b64, sig = state.rsplit(".", 1)
        # Restore padding
        padding = "=" * (-len(b64) % 4)
        payload = urlsafe_b64decode(b64 + padding)
        expected_sig = _sign(payload)[:32]
        if not hmac.compare_digest(sig, expected_sig):
            return False
        data = json.loads(payload)
        if data.get("provider") != expected_provider:
            return False
        if data.get("exp", 0) < int(time.time()):
            return False
        return True
    except (ValueError, json.JSONDecodeError, TypeError, AttributeError):
        return False
