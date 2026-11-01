"""Configuration settings for the FlairGuard AI API and platform services."""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings with environment variable override support."""
    app_name: str = "FlairGuard AI Platform"
    app_version: str = "0.4.0"
    environment: str = "production"
    debug: bool = False
    
    # Base paths
    root_dir: Path = ROOT
    data_dir: Path = ROOT / "data" / "raw"
    artifacts_dir: Path = ROOT / "artifacts"
    db_path: Path = ROOT / "data" / "flairguard_platform.db"
    
    # Specific model artifact locations
    fd001_bundle_path: Path = ROOT / "artifacts" / "phase_a" / "fd001-v1-run002" / "models" / "bundle.joblib"
    fd002_bundle_path: Path = ROOT / "artifacts" / "phase_b" / "fd002-v1-run002" / "models" / "bundle.joblib"
    
    mlflow_required: bool = True
    mlflow_tracking_uri: str = ""
    api_key: str = ""

    # Server configuration & Security hardening
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ]

    model_config = SettingsConfigDict(
        env_prefix="FLAIRGUARD_",
        arbitrary_types_allowed=True,
    )


settings = Settings()
