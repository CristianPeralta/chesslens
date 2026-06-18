from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

CONFIG_DIR = Path.home() / ".chesslens"
USER_ENV = CONFIG_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CHESSLENS_",
        env_file=[".env", str(USER_ENV)],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    username: str = ""
    model: str = "claude-sonnet-4-6"
    stockfish_path: str = ""
    database_url: str = ""
    reports_dir: Path = Path("./reports")
    jwt_secret: str = ""
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{CONFIG_DIR}/chesslens.db"


def save_user_config(**kwargs: str) -> None:
    """Persist config values to ~/.chesslens/.env"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    existing: dict[str, str] = {}
    if USER_ENV.exists():
        for line in USER_ENV.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                existing[k.strip()] = v.strip()

    for key, value in kwargs.items():
        existing[f"CHESSLENS_{key.upper()}"] = value

    USER_ENV.write_text("\n".join(f"{k}={v}" for k, v in existing.items()) + "\n")


settings = Settings()
