from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model_name: str = "gpt-4o-mini"
    llm_mock: bool = False
    llm_timeout_seconds: float = 90.0

    data_dir: Path = Field(default=Path("./data"))
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000"

    scenario_designer: str = ""
    evaluator: str = ""

    max_swarm_agents: int = 50
    mirofish_live_agents: int = 12
    mirofish_use_llm_profiles: bool = False

    mirofish_base_url: str = ""
    mirofish_auto_launch: bool = False
    mirofish_auto_swarm: bool = False
    mirofish_timeout_seconds: float = 120.0
    mirofish_swarm_timeout_seconds: float = 900.0
    mirofish_poll_seconds: float = 5.0
    mirofish_max_rounds: int = 2
    mirofish_platform: str = "twitter"

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [item.strip() for item in self.cors_origins.split(",") if item.strip()]
        return origins or ["*"]

    @property
    def use_llm(self) -> bool:
        return bool(self.llm_api_key) and not self.llm_mock


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "runs").mkdir(parents=True, exist_ok=True)
    return settings
