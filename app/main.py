from __future__ import annotations

from contextlib import asynccontextmanager
import logging as _logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.rate_limit import limiter
from app.routes.auth import router as auth_router
from app.routes.portfolio import router as portfolio_router
from app.routes.resume import router as resume_router
from app.services import aws_store

_logger = _logging.getLogger(__name__)


def _is_local_env() -> bool:
    return any(h in settings.APP_BASE_URL for h in ("localhost", "127.0.0.1", "0.0.0.0"))


def _cors_origins() -> list[str]:
    origins = {settings.FRONTEND_URL, settings.APP_BASE_URL}

    # Local development may run frontend/backends on different localhost ports.
    if _is_local_env():
        origins.update(
            {
                "http://localhost:5173",
                "http://localhost:5174",
                "http://127.0.0.1:5173",
                "http://127.0.0.1:5174",
                "http://localhost:8000",
                "http://127.0.0.1:8000",
                "http://0.0.0.0:5173",
                "http://0.0.0.0:5174",
                "http://0.0.0.0:8000",
            }
        )

    return sorted(origins)


def _cors_origin_regex() -> str | None:
    if not _is_local_env():
        return None

    # Allow local-network browser origins in dev (localhost, loopback, RFC1918 IPs).
    return (
        r"^https?://("
        r"localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}"
        r")(?:\:\d{1,5})?$"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.LOCAL_DATA_DIR).mkdir(parents=True, exist_ok=True)

    # Validate portfolio template directory exists on startup (fail fast)
    template_dir = Path(settings.PORTFOLIO_TEMPLATE_DIR).resolve()
    if not template_dir.exists():
        raise RuntimeError(
            f"Portfolio template directory not found: {template_dir}. "
            "Set PORTFOLIO_TEMPLATE_DIR env var to the jaani-builds.github.io checkout path."
        )
    if not (template_dir / "index.html").exists():
        raise RuntimeError(
            f"Portfolio template index.html not found in: {template_dir}. "
            "Ensure the portfolio template directory is complete."
        )

    await aws_store.ensure_tables()
    yield


app = FastAPI(title="Portfolio Builder API", version="2.0.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=_cors_origin_regex(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(resume_router)
app.include_router(portfolio_router)

try:
    app.mount("/", StaticFiles(directory="static", html=True), name="static")
except RuntimeError:
    _logger.debug("Static files directory not present - skipping static mount (expected in Lambda)")
