from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App settings, read from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Roster SaaS"
    # Local dev uses SQLite; in Azure this becomes a PostgreSQL URL.
    database_url: str = "sqlite:///./roster.db"
    # MUST be overridden in any real environment (Key Vault in Azure).
    jwt_secret: str = "dev-only-change-me-please-32-bytes-min"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60


settings = Settings()
