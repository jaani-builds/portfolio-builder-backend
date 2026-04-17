from __future__ import annotations

import hashlib
import hmac
from datetime import date, datetime, timedelta, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr

from app.config import settings
from app.services import aws_store


_SUPPORTED_EVENTS = {
    "portfolio_view",
    "pdf_click",
    "linkedin_click",
    "github_click",
    "contact_click",
}


def _today_str() -> str:
    return date.today().isoformat()


def _counter_pk(slug: str, day: str) -> str:
    return f"ANALYTICS#{slug}#{day}"


def _unique_pk(slug: str, day: str, visitor_hash: str) -> str:
    return f"ANALYTICS_UV#{slug}#{day}#{visitor_hash}"


def _event_counter_field(event_type: str) -> str:
    return f"event_{event_type}"


def _visitor_hash(ip: str, user_agent: str, day: str) -> str:
    raw = f"{ip}|{user_agent}|{day}".encode("utf-8")
    return hmac.new(settings.JWT_SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()[:24]


def _extract_ip(request_ip: str, x_forwarded_for: str | None) -> str:
    if x_forwarded_for:
        first = x_forwarded_for.split(",", 1)[0].strip()
        if first:
            return first
    return request_ip or "unknown"


async def record_event(
    slug: str,
    event_type: str,
    request_ip: str,
    user_agent: str,
    x_forwarded_for: str | None = None,
) -> dict[str, Any]:
    if event_type not in _SUPPORTED_EVENTS:
        raise ValueError("Unsupported analytics event type")

    day = _today_str()
    now_iso = datetime.now(timezone.utc).isoformat()
    ip = _extract_ip(request_ip, x_forwarded_for)
    unique_increment = 0

    if event_type == "portfolio_view":
        vh = _visitor_hash(ip, user_agent or "", day)
        try:
            # Keep unique markers short-lived and privacy-safe.
            ttl = int((datetime.now(timezone.utc) + timedelta(days=120)).timestamp())
            aws_store._table.put_item(
                Item={
                    "pk": _unique_pk(slug, day, vh),
                    "slug": slug,
                    "day": day,
                    "ttl": ttl,
                },
                ConditionExpression="attribute_not_exists(pk)",
            )
            unique_increment = 1
        except Exception:
            unique_increment = 0

    event_field = _event_counter_field(event_type)
    expr_vals: dict[str, Any] = {
        ":v": 1,
        ":slug": slug,
        ":day": day,
        ":now": now_iso,
    }

    add_fields = ["#evt :v"]
    if event_type == "portfolio_view":
        add_fields.insert(0, "views :v")
    add_expr = ", ".join(add_fields)
    if unique_increment:
        add_expr += ", unique_visitors :u"
        expr_vals[":u"] = unique_increment

    aws_store._table.update_item(
        Key={"pk": _counter_pk(slug, day)},
        UpdateExpression=f"ADD {add_expr} SET updated_at = :now, slug = :slug, day = :day",
        ExpressionAttributeValues=expr_vals,
        ExpressionAttributeNames={"#evt": event_field},
    )

    return {"status": "ok", "unique_increment": unique_increment}


async def get_analytics(slug: str, days: int = 30) -> dict[str, Any]:
    days = max(1, min(90, int(days)))
    cutoff = date.today() - timedelta(days=days - 1)
    prefix = f"ANALYTICS#{slug}#"

    rows: list[dict[str, Any]] = []
    scan_kwargs: dict[str, Any] = {
        "FilterExpression": Attr("pk").begins_with(prefix),
    }
    while True:
        resp = aws_store._table.scan(**scan_kwargs)
        rows.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        scan_kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    daily: list[dict[str, Any]] = []
    totals = {
        "views": 0,
        "unique_visitors": 0,
        "pdf_click": 0,
        "linkedin_click": 0,
        "github_click": 0,
        "contact_click": 0,
    }

    for item in rows:
        day = str(item.get("day") or "")
        try:
            day_obj = date.fromisoformat(day)
        except ValueError:
            continue
        if day_obj < cutoff:
            continue

        views = int(item.get("views", 0) or 0)
        unique_visitors = int(item.get("unique_visitors", 0) or 0)
        pdf_click = int(item.get("event_pdf_click", 0) or 0)
        linkedin_click = int(item.get("event_linkedin_click", 0) or 0)
        github_click = int(item.get("event_github_click", 0) or 0)
        contact_click = int(item.get("event_contact_click", 0) or 0)

        totals["views"] += views
        totals["unique_visitors"] += unique_visitors
        totals["pdf_click"] += pdf_click
        totals["linkedin_click"] += linkedin_click
        totals["github_click"] += github_click
        totals["contact_click"] += contact_click

        daily.append(
            {
                "date": day,
                "views": views,
                "unique_visitors": unique_visitors,
                "pdf_click": pdf_click,
                "linkedin_click": linkedin_click,
                "github_click": github_click,
                "contact_click": contact_click,
            }
        )

    daily.sort(key=lambda x: x["date"])
    return {
        "slug": slug,
        "range_days": days,
        "totals": totals,
        "daily": daily,
    }
