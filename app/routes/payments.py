from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator

from app.dependencies import get_current_user
from app.models import UserProfile
from app.rate_limit import limiter
from app.services import aws_store

router = APIRouter(prefix="/api/payments", tags=["payments"])


class PaymentLogRequest(BaseModel):
    amount: float = Field(..., gt=0)
    currency: str = "SGD"

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        code = (value or "SGD").strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise ValueError("currency must be a 3-letter code")
        return code


@router.post("/log")
@limiter.limit("20/minute")
async def log_payment(
    request: Request,
    body: PaymentLogRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    amount = round(float(body.amount), 2)
    payment_id = await aws_store.save_payment_log(
        {
            "user_key": current_user.user_key,
            "payer_name": current_user.name or "",
            "payer_email": current_user.email or "",
            "amount": amount,
            "currency": body.currency,
            "source": "paynow-support",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"status": "logged", "payment_id": payment_id}
