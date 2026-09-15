"""
Central configuration, loaded from environment variables (.env).
No credentials ever get hard-coded here — only read via os.environ.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    data_mode: str = "mock"          # "mock" or "live"

    helius_api_key: str = ""
    bitquery_access_token: str = ""

    database_url: str = "sqlite:///./early_token_prediction.db"

    host: str = "0.0.0.0"
    port: int = 8000

    feature_tick_ms: int = 1000
    feature_window_seconds: int = 600

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()


def credentials_ready() -> dict:
    """Report which providers have credentials configured, without
    ever exposing the credential values themselves."""
    return {
        "helius": bool(settings.helius_api_key),
        "bitquery": bool(settings.bitquery_access_token),
        "mode": settings.data_mode,
    }
