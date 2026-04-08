import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from jose import jwt

# Set test env vars before importing app settings/app
os.environ.setdefault("AWS_S3_BUCKET", "test-bucket")
os.environ.setdefault("AWS_DDB_TABLE", "test-table")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-long-enough-32chars")
os.environ.setdefault("APP_BASE_URL", "http://localhost:8000")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5174")
os.environ.setdefault("GITHUB_CLIENT_ID", "test-client-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-client-secret")

_tmpdir = tempfile.mkdtemp(prefix="portfolio-template-")
with open(os.path.join(_tmpdir, "index.html"), "w", encoding="utf-8") as f:
    f.write("<html><body>template</body></html>")
os.environ.setdefault("PORTFOLIO_TEMPLATE_DIR", _tmpdir)

from app.config import settings
from app.main import app
from app.services.jwt_service import create_token


client = TestClient(app, raise_server_exceptions=False)


def _auth_headers(user_key: str, email: str = "test@example.com", name: str = "Test User") -> dict:
    token = create_token(user_key, email, name)
    return {"Authorization": f"Bearer {token}"}


def _expired_headers(user_key: str) -> dict:
    payload = {
        "sub": user_key,
        "email": "expired@example.com",
        "name": "Expired User",
        "avatar_url": "",
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return {"Authorization": f"Bearer {token}"}


@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_get_resume_requires_auth(_mock_ensure_tables):
    response = client.get("/api/resume")
    assert response.status_code == 401


@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_get_resume_with_invalid_token(_mock_ensure_tables):
    response = client.get("/api/resume", headers={"Authorization": "Bearer bad.token.value"})
    assert response.status_code == 401


@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_get_resume_with_expired_token(_mock_ensure_tables):
    response = client.get("/api/resume", headers=_expired_headers("github_100"))
    assert response.status_code == 401


@patch("app.routes.resume.aws_store.read_resume_json", new_callable=AsyncMock)
@patch("app.routes.resume.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.dependencies.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_user_cannot_read_other_users_slug(
    _mock_ensure_tables,
    mock_dep_meta,
    mock_route_meta,
    mock_read_resume,
):
    def _meta_by_user_key(user_key: str):
        if user_key == "github_100":
            return {"resume_key": "portfolio-builder/users/github_100/resume.json"}
        return {}

    mock_dep_meta.side_effect = _meta_by_user_key
    mock_route_meta.side_effect = _meta_by_user_key
    mock_read_resume.return_value = {"basics": {"name": "User 1"}}

    user2_headers = _auth_headers("github_200", "user2@example.com", "User Two")
    response = client.get("/api/resume", headers=user2_headers)

    assert response.status_code == 404


@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_set_slug_requires_auth(_mock_ensure_tables):
    response = client.put("/api/portfolio/slug", json={"slug": "alice"})
    assert response.status_code == 401


@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_put_resume_json_requires_auth(_mock_ensure_tables):
    response = client.put("/api/resume/json", json={"resume_json": {"basics": {"name": "A"}}})
    assert response.status_code == 401


@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_upload_resume_requires_auth(_mock_ensure_tables):
    response = client.post("/api/resume/upload", json={"text": "Some resume text"})
    assert response.status_code == 401


@patch("app.services.slug_store.get_slug_entry", new_callable=AsyncMock)
@patch("app.services.slug_store.aws_store.save_slug_entry", new_callable=AsyncMock)
@patch("app.routes.portfolio.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.dependencies.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_user_a_cannot_claim_user_b_slug(
    _mock_ensure_tables,
    mock_dep_meta,
    mock_route_meta,
    mock_save_slug_entry,
    mock_get_slug_entry,
):
    def _meta_by_user_key(user_key: str):
        if user_key == "github_100":
            return {"slug": "alice", "resume_key": "portfolio-builder/users/github_100/resume.json"}
        if user_key == "github_200":
            return {"resume_key": "portfolio-builder/users/github_200/resume.json"}
        return {}

    async def _save_slug_side_effect(slug: str, entry: dict, user_key: str):
        if user_key == "github_200" and slug == "alice":
            raise ValueError("Slug is already taken")
        return None

    mock_dep_meta.side_effect = _meta_by_user_key
    mock_route_meta.side_effect = _meta_by_user_key
    mock_get_slug_entry.return_value = None
    mock_save_slug_entry.side_effect = _save_slug_side_effect

    user2_headers = _auth_headers("github_200", "user2@example.com", "User Two")
    response = client.put("/api/portfolio/slug", json={"slug": "alice"}, headers=user2_headers)

    assert response.status_code == 409
