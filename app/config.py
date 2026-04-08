from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_SECRET = "change-me-in-production-use-a-long-random-string"

_RESERVED = [
    "api", "auth", "static", "app", "admin", "health",
    "login", "logout", "signup", "docs", "openapi",
    "robots.txt", "favicon.ico", "sitemap.xml", "callback",
    "p", "assets", "data", "exchange",
]


class Settings(BaseSettings):
    JWT_SECRET: str = _DEFAULT_SECRET
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_DAYS: int = 1  # Short-lived for security

    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""

    AWS_REGION: str = "us-east-1"
    AWS_S3_BUCKET: str = ""
    AWS_DDB_TABLE: str = ""
    AWS_S3_PREFIX: str = "portfolio-builder"
    AWS_ENDPOINT_URL: str = ""  # For LocalStack: http://localhost:4566
    AWS_PUBLIC_BASE_URL: str = ""

    # Base URL of this app (used to build OAuth redirect URIs)
    APP_BASE_URL: str = "http://localhost:8000"

    # URL of the management frontend (for post-auth redirect)
    FRONTEND_URL: str = "http://localhost:5174"

    # Path to the jaani-builds.github.io portfolio template directory
    PORTFOLIO_TEMPLATE_DIR: str = "../../jaani-builds.github.io"

    RESERVED_SLUGS: list[str] = _RESERVED

    # Local data directory for slug/user meta storage
    LOCAL_DATA_DIR: str = "./data"

    # Local-only escape hatch for environments with intercepted TLS cert chains.
    # Keep this False in production.
    AWS_INSECURE_SSL: bool = False

    @model_validator(mode="after")
    def check_production_safety(self) -> "Settings":
        is_local = any(
            h in self.APP_BASE_URL for h in ("localhost", "127.0.0.1", "0.0.0.0")
        )
        if not is_local:
            if self.JWT_SECRET == _DEFAULT_SECRET:
                raise ValueError(
                    "JWT_SECRET must be changed from the default before deploying to production."
                )
            if len(self.JWT_SECRET) < 32:
                raise ValueError("JWT_SECRET must be at least 32 characters in production.")

            if not self.GITHUB_CLIENT_ID:
                raise ValueError("GITHUB_CLIENT_ID is required")
            if not self.GITHUB_CLIENT_SECRET:
                raise ValueError("GITHUB_CLIENT_SECRET is required")
        else:
            # For local development, allow empty GitHub credentials  
            self.GITHUB_CLIENT_ID = self.GITHUB_CLIENT_ID or "local-dev"
            self.GITHUB_CLIENT_SECRET = self.GITHUB_CLIENT_SECRET or "local-dev"

        if not self.AWS_S3_BUCKET:
            raise ValueError("AWS_S3_BUCKET is required")
        if not self.AWS_DDB_TABLE:
            raise ValueError("AWS_DDB_TABLE is required")
        return self


    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )



settings = Settings()
