import logging
import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
logger = logging.getLogger("zephyrscript")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    app_name: str = "ZephyrScript"
    version: str = "1.0"

    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    preview_token_expire_minutes: int = 60

    database_url: str = f"sqlite:///{BASE_DIR / 'zephyrscript.db'}"
    workspace_dir: Path = Path("workspace")

    cors_origins: str = "*"

    allow_registration: bool = True

    max_file_size_kb: int = 1024
    max_files_per_project: int = 5000
    max_terminals_per_user: int = 3
    terminal_shell: str = "/bin/bash"

    rate_limit_default: str = "120/minute"
    rate_limit_auth: str = "10/minute"

    @property
    def workspace_root(self) -> Path:
        root = (BASE_DIR / self.workspace_dir).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    @property
    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if raw == "*" or not raw:
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


settings = Settings()

if not settings.jwt_secret:
    # Fallback dev: secret acak (token tidak valid lagi setelah restart/reload).
    settings.jwt_secret = secrets.token_urlsafe(48)
    logger.warning(
        "JWT_SECRET kosong -> memakai secret acak sementara. "
        "Set JWT_SECRET di .env agar login tidak hilang saat reload."
    )
