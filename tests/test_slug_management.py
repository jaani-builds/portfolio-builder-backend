import os
import tempfile
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

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

from app.main import app
from app.services.jwt_service import create_token


client = TestClient(app, raise_server_exceptions=False)


def _auth_headers(user_key: str = "github_100") -> dict:
    token = create_token(user_key, "test@example.com", "Test User")
    return {"Authorization": f"Bearer {token}"}


@patch("app.routes.portfolio.slug_store.claim_slug", new_callable=AsyncMock)
@patch("app.routes.portfolio.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.dependencies.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_set_slug_valid(_mock_ensure_tables, mock_dep_meta, mock_route_meta, mock_claim_slug):
    mock_dep_meta.return_value = {"resume_key": "portfolio-builder/users/test/resume.json"}
    mock_route_meta.return_value = {"resume_key": "portfolio-builder/users/test/resume.json"}
    mock_claim_slug.return_value = None

    response = client.put("/api/portfolio/slug", json={"slug": "myname"}, headers=_auth_headers())

    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "myname"
    assert data["url"] == "/myname/"


@patch("app.dependencies.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_set_slug_invalid_format(_mock_ensure_tables, mock_dep_meta):
    mock_dep_meta.return_value = {}
    response = client.put("/api/portfolio/slug", json={"slug": "hello world"}, headers=_auth_headers())
    assert response.status_code == 422


@patch("app.dependencies.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_set_slug_too_short(_mock_ensure_tables, mock_dep_meta):
    mock_dep_meta.return_value = {}
    response = client.put("/api/portfolio/slug", json={"slug": "ab"}, headers=_auth_headers())
    assert response.status_code == 422


@patch("app.dependencies.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_set_slug_reserved(_mock_ensure_tables, mock_dep_meta):
    mock_dep_meta.return_value = {}
    response = client.put("/api/portfolio/slug", json={"slug": "api"}, headers=_auth_headers())
    assert response.status_code == 422


@patch("app.routes.portfolio.slug_store.claim_slug", new_callable=AsyncMock)
@patch("app.routes.portfolio.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.dependencies.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_set_slug_conflict_no_autosuffix(_mock_ensure_tables, mock_dep_meta, mock_route_meta, mock_claim_slug):
    mock_dep_meta.return_value = {"resume_key": "portfolio-builder/users/test/resume.json"}
    mock_route_meta.return_value = {"resume_key": "portfolio-builder/users/test/resume.json"}
    mock_claim_slug.side_effect = ValueError("Slug is already taken")

    response = client.put("/api/portfolio/slug", json={"slug": "myslug"}, headers=_auth_headers())
    assert response.status_code == 409


@patch("app.routes.portfolio.slug_store.get_slug_entry", new_callable=AsyncMock)
@patch("app.routes.portfolio.slug_store.claim_slug", new_callable=AsyncMock)
@patch("app.routes.portfolio.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.dependencies.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_set_slug_conflict_with_autosuffix(
    _mock_ensure_tables,
    mock_dep_meta,
    mock_route_meta,
    mock_claim_slug,
    mock_get_slug_entry,
):
    mock_dep_meta.return_value = {"resume_key": "portfolio-builder/users/test/resume.json"}
    mock_route_meta.return_value = {"resume_key": "portfolio-builder/users/test/resume.json"}
    mock_claim_slug.side_effect = [ValueError("Slug is already taken"), None]
    mock_get_slug_entry.return_value = None

    response = client.put(
        "/api/portfolio/slug",
        json={"slug": "myslug", "auto_suffix_on_conflict": True},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "myslug-2"
    assert data["auto_suffixed"] is True


@patch("app.routes.portfolio.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.dependencies.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_set_slug_requires_resume(_mock_ensure_tables, mock_dep_meta, mock_route_meta):
    mock_dep_meta.return_value = {}
    mock_route_meta.return_value = {}

    response = client.put("/api/portfolio/slug", json={"slug": "myname"}, headers=_auth_headers())
    assert response.status_code == 400


@patch("app.routes.portfolio.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.dependencies.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_get_slug(_mock_ensure_tables, mock_dep_meta, mock_route_meta):
    mock_dep_meta.return_value = {"slug": "myname", "resume_key": "portfolio-builder/users/test/resume.json"}
    mock_route_meta.return_value = {"slug": "myname", "resume_key": "portfolio-builder/users/test/resume.json"}

    response = client.get("/api/portfolio/slug", headers=_auth_headers())
    assert response.status_code == 200
    assert response.json().get("slug") == "myname"


@patch("app.routes.portfolio.slug_store.get_slug_entry", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_slug_suggestions_valid(_mock_ensure_tables, mock_get_slug_entry):
    mock_get_slug_entry.return_value = None

    response = client.get("/api/portfolio/slug/suggestions?slug=myname")
    assert response.status_code == 200
    assert isinstance(response.json().get("suggestions"), list)


@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_slug_suggestions_invalid(_mock_ensure_tables):
    response = client.get("/api/portfolio/slug/suggestions?slug=API")
    assert response.status_code == 400


@patch("app.routes.portfolio.slug_store.get_slug_entry", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_public_portfolio_404_unknown_slug(_mock_ensure_tables, mock_get_slug_entry):
    mock_get_slug_entry.return_value = None

    response = client.get("/unknown-slug/")
    assert response.status_code == 404
