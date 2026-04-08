from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class UserProfile:
    """In-memory representation of an authenticated user (no database required)."""
    user_key: str           # "github_<id>"
    provider: str           # "github"
    provider_user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    slug: Optional[str] = None

