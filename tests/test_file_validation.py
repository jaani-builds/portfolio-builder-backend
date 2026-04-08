import io
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


@patch("app.routes.resume.parse_resume", return_value={"basics": {"name": "Test"}})
@patch("app.routes.resume.slug_store.save_user_meta", new_callable=AsyncMock)
@patch("app.routes.resume.aws_store.put_resume_json", new_callable=AsyncMock)
@patch("app.routes.resume.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.dependencies.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_upload_empty_text(
    _mock_ensure_tables,
    mock_dep_meta,
    mock_route_meta,
    mock_put_resume_json,
    _mock_save_user_meta,
    _mock_parse_resume,
):
    mock_dep_meta.return_value = {"resume_key": "some-key"}
    mock_route_meta.return_value = {"resume_key": "some-key"}
    mock_put_resume_json.return_value = "portfolio-builder/users/test/resume.json"

    response = client.post("/api/resume/upload", json={"text": "   "}, headers=_auth_headers())
    assert response.status_code == 422


@patch("app.routes.resume.parse_resume", return_value={"basics": {"name": "Test"}})
@patch("app.routes.resume.slug_store.save_user_meta", new_callable=AsyncMock)
@patch("app.routes.resume.aws_store.put_resume_json", new_callable=AsyncMock)
@patch("app.routes.resume.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.dependencies.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_upload_text_too_long(
    _mock_ensure_tables,
    mock_dep_meta,
    mock_route_meta,
    mock_put_resume_json,
    _mock_save_user_meta,
    _mock_parse_resume,
):
    mock_dep_meta.return_value = {"resume_key": "some-key"}
    mock_route_meta.return_value = {"resume_key": "some-key"}
    mock_put_resume_json.return_value = "portfolio-builder/users/test/resume.json"

    response = client.post("/api/resume/upload", json={"text": "a" * 50001}, headers=_auth_headers())
    assert response.status_code == 422


@patch("app.routes.resume.parse_resume", return_value={"basics": {"name": "Test"}, "experience": []})
@patch("app.routes.resume.slug_store.save_user_meta", new_callable=AsyncMock)
@patch("app.routes.resume.aws_store.put_resume_json", new_callable=AsyncMock)
@patch("app.routes.resume.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.dependencies.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_upload_valid_text(
    _mock_ensure_tables,
    mock_dep_meta,
    mock_route_meta,
    mock_put_resume_json,
    _mock_save_user_meta,
    _mock_parse_resume,
):
    mock_dep_meta.return_value = {"resume_key": "some-key"}
    mock_route_meta.return_value = {"resume_key": "some-key"}
    mock_put_resume_json.return_value = "portfolio-builder/users/test/resume.json"

    response = client.post(
        "/api/resume/upload",
        json={"text": "Jane Doe\njane@example.com\nExperience: ..."},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert "parsed" in response.json()


@patch("app.dependencies.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_upload_pdf_empty_file(_mock_ensure_tables, mock_dep_meta):
    mock_dep_meta.return_value = {"resume_key": "some-key"}
    files = {"file": ("resume.pdf", io.BytesIO(b""), "application/pdf")}
    response = client.post("/api/resume/pdf", files=files, headers=_auth_headers())
    assert response.status_code == 400


@patch("app.dependencies.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_upload_pdf_too_large(_mock_ensure_tables, mock_dep_meta):
    mock_dep_meta.return_value = {"resume_key": "some-key"}
    files = {"file": ("resume.pdf", io.BytesIO(b"x" * (11 * 1024 * 1024)), "application/pdf")}
    response = client.post("/api/resume/pdf", files=files, headers=_auth_headers())
    assert response.status_code == 400


@patch("app.dependencies.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_upload_pdf_wrong_type(_mock_ensure_tables, mock_dep_meta):
    mock_dep_meta.return_value = {"resume_key": "some-key"}
    files = {"file": ("resume.txt", io.BytesIO(b"not a pdf"), "text/plain")}
    response = client.post("/api/resume/pdf", files=files, headers=_auth_headers())
    assert response.status_code == 400


@patch("app.routes.resume.aws_store.put_resume_pdf", new_callable=AsyncMock)
@patch("app.dependencies.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_upload_pdf_valid(_mock_ensure_tables, mock_dep_meta, mock_put_resume_pdf):
    mock_dep_meta.return_value = {"resume_key": "some-key"}
    mock_put_resume_pdf.return_value = "https://s3.example.com/resume.pdf"

    pdf_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"
    files = {"file": ("resume.pdf", io.BytesIO(pdf_content), "application/pdf")}
    response = client.post("/api/resume/pdf", files=files, headers=_auth_headers())

    assert response.status_code == 200
    assert response.json().get("pdfUrl") == "https://s3.example.com/resume.pdf"


@patch("app.routes.resume.slug_store.claim_slug", new_callable=AsyncMock)
@patch("app.routes.resume.slug_store.save_user_meta", new_callable=AsyncMock)
@patch("app.routes.resume.aws_store.put_resume_json", new_callable=AsyncMock)
@patch("app.routes.resume.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.dependencies.slug_store.get_user_meta", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_update_resume_json_valid(
    _mock_ensure_tables,
    mock_dep_meta,
    mock_route_meta,
    mock_put_resume_json,
    _mock_save_user_meta,
    _mock_claim_slug,
):
    mock_dep_meta.return_value = {"resume_key": "some-key"}
    mock_route_meta.return_value = {"slug": "my-portfolio", "resume_key": "some-key"}
    mock_put_resume_json.return_value = "portfolio-builder/users/test/resume.json"

    payload = {"resume_json": {"basics": {"name": "Jane Doe"}, "experience": []}}
    response = client.put("/api/resume/json", json=payload, headers=_auth_headers())

    assert response.status_code == 200
