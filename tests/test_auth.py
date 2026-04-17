import os
import tempfile
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

from app.main import app
from app.config import settings
from app.services.oauth_service import generate_state


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


client = TestClient(app, raise_server_exceptions=False)


@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_login_github_redirects(_mock_ensure_tables):
    response = client.get("/api/auth/github", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].startswith("https://github.com/login/oauth/authorize?")


@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_login_github_state_in_redirect(_mock_ensure_tables):
    response = client.get("/api/auth/github", follow_redirects=False)
    location = response.headers["location"]
    assert response.status_code == 307
    assert "state=" in location
    assert "client_id=" in location


@patch("app.services.exchange_store.issue", return_value="exchange-code-123")
@patch("app.services.aws_store.get_user_meta", new_callable=AsyncMock, return_value={})
@patch("app.services.aws_store.save_user_meta", new_callable=AsyncMock, return_value=None)
@patch("httpx.AsyncClient.post", new_callable=AsyncMock)
@patch("httpx.AsyncClient.get", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_callback_valid(
    _mock_ensure_tables,
    mock_get,
    mock_post,
    _mock_save_user_meta,
    _mock_get_user_meta,
    _mock_issue,
):
    valid_state = generate_state("github")

    mock_post.return_value = _FakeResponse(200, {"access_token": "gho_test_token"})
    mock_get.side_effect = [
        _FakeResponse(200, {"id": 12345, "login": "octocat", "name": "The Octocat", "email": None}),
        _FakeResponse(200, [{"email": "octo@example.com", "primary": True, "verified": True}]),
    ]

    response = client.get(
        f"/api/auth/callback/github?code=oauth-code&state={valid_state}",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"].startswith("http://localhost:5174/#/callback?code=exchange-code-123")


@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_callback_invalid_state(_mock_ensure_tables):
    response = client.get(
        "/api/auth/callback/github?code=oauth-code&state=invalid-state",
        follow_redirects=False,
    )
    assert response.status_code == 400


@patch("httpx.AsyncClient.post", new_callable=AsyncMock)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_callback_github_token_error(_mock_ensure_tables, mock_post):
    valid_state = generate_state("github")
    mock_post.return_value = _FakeResponse(500, {"error": "bad_verification_code"})

    response = client.get(
        f"/api/auth/callback/github?code=oauth-code&state={valid_state}",
        follow_redirects=False,
    )

    assert response.status_code in (400, 502)


@patch("app.services.exchange_store.redeem", return_value="jwt-token-abc")
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_exchange_valid_code(_mock_ensure_tables, _mock_redeem):
    response = client.get("/api/auth/exchange?code=valid-code")
    assert response.status_code == 200
    assert response.json() == {"token": "jwt-token-abc"}
    assert settings.SESSION_COOKIE_NAME in response.cookies


@patch("app.services.exchange_store.redeem", return_value="jwt-token-abc")
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_exchange_sets_http_only_cookie(_mock_ensure_tables, _mock_redeem):
    response = client.get("/api/auth/exchange?code=valid-code")
    set_cookie = response.headers.get("set-cookie", "")
    assert f"{settings.SESSION_COOKIE_NAME}=" in set_cookie
    assert "HttpOnly" in set_cookie


@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_logout_clears_cookie(_mock_ensure_tables):
    token = jwt.encode(
        {
            "sub": "github_123",
            "email": "test@example.com",
            "name": "Tester",
            "avatar_url": "",
            "iss": (settings.JWT_ISSUER or settings.APP_BASE_URL).rstrip("/"),
            "aud": settings.JWT_AUDIENCE,
            "exp": 4102444800,
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    response = client.post(
        "/api/auth/logout",
        cookies={settings.SESSION_COOKIE_NAME: token},
    )
    assert response.status_code == 200
    assert "Max-Age=0" in response.headers.get("set-cookie", "") or "expires=" in response.headers.get("set-cookie", "").lower()


@patch("app.services.exchange_store.redeem", return_value=None)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_exchange_invalid_code(_mock_ensure_tables, _mock_redeem):
    response = client.get("/api/auth/exchange?code=bad")
    assert response.status_code == 400


@patch("app.services.exchange_store.redeem", return_value=None)
@patch("app.main.aws_store.ensure_tables", new_callable=AsyncMock)
def test_exchange_expired_code(_mock_ensure_tables, _mock_redeem):
    response = client.get("/api/auth/exchange?code=expired")
    assert response.status_code == 400
