"""Application configuration — the single trust root.

Every secret and tunable enters the app here, sourced from the environment
(and `.env` in development). No secret is ever hardcoded in source. In a
production/staging environment the app refuses to boot if a required secret
is missing or left at an insecure default (fail-fast).

`DATABASE_URL` and `REDIS_URL` are derived from their component vars when not
set explicitly, so the same config works locally (`localhost`) and under
docker-compose (service-name hosts) — fixing the prior bug where containers
pointed at `localhost`.
"""

from __future__ import annotations

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Values that must never appear in a production deployment.
_INSECURE_SENTINELS = {
    "",
    "dev-only-insecure-key-change-me",
    "super-secret-key-change-this",
    "change-me-in-production",
    "changeme",
    "postgres",
}


class Settings(BaseSettings):
    # ---- Application ----
    APP_NAME: str = "LeadPulse"
    APP_ENV: str = "development"  # development | staging | production
    APP_PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # ---- Database (components are the source of truth) ----
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "leadpulse"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None  # derived from components when unset

    # ---- Redis ----
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: str | None = None  # derived from components when unset

    # ---- Security ----
    JWT_SECRET_KEY: str = "dev-only-insecure-key-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    # ---- CORS (comma-separated origins) ----
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # ---- LLM provider ----
    GROQ_API_KEY: str = ""
    LLM_MODEL: str = "llama3-70b-8192"

    # ---- Email (SMTP) ----
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@leadpulse.example"

    # ---- Outbound webhook ----
    WEBHOOK_URL: str = ""

    # ---- Rate limiting ----
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 10
    RATE_LIMIT_INGEST_PER_MINUTE: int = 60

    # ---- Observability ----
    SENTRY_DSN: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=True,
    )

    # ---- Derived helpers ----
    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() in {"production", "prod", "staging"}

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def _assemble_and_validate(self) -> "Settings":
        # Derive connection URLs from components when not explicitly provided.
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        if not self.REDIS_URL:
            self.REDIS_URL = (
                f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
            )

        # Fail fast on insecure defaults in production-like environments.
        if self.is_production:
            problems: list[str] = []
            if self.JWT_SECRET_KEY in _INSECURE_SENTINELS:
                problems.append("JWT_SECRET_KEY")
            if self.POSTGRES_PASSWORD in _INSECURE_SENTINELS:
                problems.append("POSTGRES_PASSWORD")
            if not self.GROQ_API_KEY:
                problems.append("GROQ_API_KEY")
            if problems:
                raise ValueError(
                    "Refusing to start: insecure or missing required secrets "
                    f"{problems} for APP_ENV={self.APP_ENV!r}. "
                    "Provide them via environment variables or a secret manager."
                )
        return self


settings = Settings()
