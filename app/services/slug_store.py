"""DynamoDB-backed slug and user metadata helpers."""

from __future__ import annotations

from typing import Optional

from botocore.exceptions import ClientError

from app.services import aws_store


# ── Slug operations ───────────────────────────────────────────────────────────

async def get_slug_entry(slug: str) -> Optional[dict]:
    return await aws_store.get_slug_entry(slug)


async def claim_slug(
    slug: str,
    user_key: str,
    resume_key: str = "",
    old_slug: Optional[str] = None,
) -> None:
    """Claim slug for a user, allowing overwrite only by the same user."""
    existing = await get_slug_entry(slug)
    if existing and existing["user_key"] != user_key:
        raise ValueError("Slug is already taken")

    payload = {"user_key": user_key}
    if resume_key:
        payload["resume_key"] = resume_key
    try:
        await aws_store.save_slug_entry(slug, payload, user_key)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise ValueError("Slug is already taken")
        raise

    # Remove old slug record if slug changed
    if old_slug and old_slug != slug:
        await aws_store.delete_slug_entry(old_slug)

    # Update user meta
    meta = await get_user_meta(user_key)
    meta["slug"] = slug
    if resume_key:
        meta["resume_key"] = resume_key
    await save_user_meta(user_key, meta)


# ── User meta operations ──────────────────────────────────────────────────────

async def get_user_meta(user_key: str) -> dict:
    return await aws_store.get_user_meta(user_key)


async def save_user_meta(user_key: str, meta: dict) -> None:
    await aws_store.save_user_meta(user_key, meta)
