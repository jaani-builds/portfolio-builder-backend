from __future__ import annotations

import json
import uuid
from typing import Any, Optional

import boto3
from botocore.client import Config

from app.config import settings


# Build boto3 kwargs with LocalStack endpoint if provided
_boto3_kwargs = {
    "region_name": settings.AWS_REGION,
}
if settings.AWS_ENDPOINT_URL:
    _boto3_kwargs["endpoint_url"] = settings.AWS_ENDPOINT_URL

_s3 = boto3.client(
    "s3",
    config=Config(signature_version="s3v4"),
    verify=(False if settings.AWS_INSECURE_SSL else True),
    **_boto3_kwargs,
)
_ddb = boto3.resource("dynamodb", **_boto3_kwargs)
_table = _ddb.Table(settings.AWS_DDB_TABLE)


async def ensure_s3_bucket() -> None:
    """Ensure S3 bucket exists, creating it if necessary (for local development)."""
    try:
        _s3.head_bucket(Bucket=settings.AWS_S3_BUCKET)
    except Exception as e:
        # Bucket doesn't exist, create it (for local/dev environments)
        error_str = str(e)
        if "404" in error_str or "NotFound" in error_str:
            _s3.create_bucket(Bucket=settings.AWS_S3_BUCKET)
        else:
            raise


async def ensure_tables() -> None:
    """Ensure DynamoDB table exists, creating it if necessary (for local development)."""
    try:
        _table.load()
    except Exception as e:
        # Table doesn't exist, create it (for local/dev environments)
        error_str = str(e)
        if "ResourceNotFoundException" in error_str or "does not exist" in error_str:
            _ddb.create_table(
                TableName=settings.AWS_DDB_TABLE,
                KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
            # Wait for table to be active
            waiter = _ddb.meta.client.get_waiter("table_exists")
            waiter.wait(TableName=settings.AWS_DDB_TABLE)
        else:
            raise
    # Ensure S3 bucket exists
    await ensure_s3_bucket()


def resume_object_key(user_key: str) -> str:
    return f"{settings.AWS_S3_PREFIX}/users/{user_key}/resume.json"


def pdf_object_key(user_key: str, filename: str = "resume.pdf") -> str:
    safe = filename if filename.lower().endswith(".pdf") else "resume.pdf"
    return f"{settings.AWS_S3_PREFIX}/users/{user_key}/{safe}"


def public_object_url(key: str) -> str:
    if settings.AWS_PUBLIC_BASE_URL:
        base = settings.AWS_PUBLIC_BASE_URL.rstrip("/")
        return f"{base}/{key}"
    return f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"


def normalize_public_url(url: str) -> str:
    """Rewrite legacy AWS S3 URLs to configured public base URL when available."""
    if not url or not settings.AWS_PUBLIC_BASE_URL:
        return url

    expected_prefix = f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/"
    if url.startswith(expected_prefix):
        key = url[len(expected_prefix):].lstrip("/")
        return public_object_url(key)
    return url


async def put_resume_json(user_key: str, resume_json: dict) -> str:
    key = resume_object_key(user_key)
    _s3.put_object(
        Bucket=settings.AWS_S3_BUCKET,
        Key=key,
        Body=json.dumps(resume_json, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )
    return key


async def read_resume_json(key: str) -> Optional[dict]:
    try:
        resp = _s3.get_object(Bucket=settings.AWS_S3_BUCKET, Key=key)
    except _s3.exceptions.NoSuchKey:
        return None
    body = resp["Body"].read()
    data = json.loads(body)
    if isinstance(data, dict) and isinstance(data.get("pdfUrl"), str):
        data["pdfUrl"] = normalize_public_url(data["pdfUrl"])
    return data


async def put_resume_pdf(user_key: str, filename: str, content: bytes, content_type: str) -> str:
    key = pdf_object_key(user_key, filename)
    _s3.put_object(
        Bucket=settings.AWS_S3_BUCKET,
        Key=key,
        Body=content,
        ContentType=(content_type or "application/pdf"),
    )
    return public_object_url(key)


def user_pk(user_key: str) -> str:
    return f"USER#{user_key}"


def slug_pk(slug: str) -> str:
    return f"SLUG#{slug}"


async def get_user_meta(user_key: str) -> dict[str, Any]:
    resp = _table.get_item(Key={"pk": user_pk(user_key)})
    item = resp.get("Item")
    if not item:
        return {}
    item.pop("pk", None)
    return item


async def save_user_meta(user_key: str, meta: dict[str, Any]) -> None:
    item = {"pk": user_pk(user_key), **meta}
    _table.put_item(Item=item)


async def get_slug_entry(slug: str) -> Optional[dict[str, Any]]:
    resp = _table.get_item(Key={"pk": slug_pk(slug)})
    item = resp.get("Item")
    if not item:
        return None
    item.pop("pk", None)
    return item


async def save_slug_entry(slug: str, entry: dict[str, Any], user_key: str) -> None:
    _table.put_item(
        Item={"pk": slug_pk(slug), **entry, "user_key": user_key},
        ConditionExpression="attribute_not_exists(pk) OR user_key = :u",
        ExpressionAttributeValues={":u": user_key},
    )


async def delete_slug_entry(slug: str) -> None:
    _table.delete_item(Key={"pk": slug_pk(slug)})


def exchange_code_pk(code: str) -> str:
    return f"EXCHANGE#{code}"


async def save_exchange_code(code: str, jwt: str, ttl_seconds: int = 30) -> None:
    """Persist a one-time exchange code with TTL expiry (stored in epoch seconds)."""
    import time as _time
    _table.put_item(
        Item={
            "pk": exchange_code_pk(code),
            "jwt": jwt,
            "ttl": int(_time.time()) + ttl_seconds,
        }
    )


async def get_and_delete_exchange_code(code: str) -> Optional[str]:
    """Atomically retrieve and delete an exchange code. Returns JWT or None if expired/missing."""
    import time as _time
    try:
        resp = _table.delete_item(
            Key={"pk": exchange_code_pk(code)},
            ReturnValues="ALL_OLD",
        )
    except Exception:
        return None
    item = resp.get("Attributes")
    if not item:
        return None
    if int(_time.time()) >= item.get("ttl", 0):
        return None
    return item.get("jwt")


def payment_pk(payment_id: str) -> str:
    return f"PAYMENT#{payment_id}"


async def save_payment_log(entry: dict[str, Any]) -> str:
    payment_id = str(uuid.uuid4())
    _table.put_item(Item={"pk": payment_pk(payment_id), **entry})
    return payment_id
