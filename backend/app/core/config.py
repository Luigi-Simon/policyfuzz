"""Environment-backed application configuration with safe diagnostics."""

from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated process settings; dotenv loading is intentionally opt-in only."""

    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        hide_input_in_errors=True,
        populate_by_name=True,
        validate_default=True,
    )

    app_mode: Literal["live", "cached"] = Field(
        default="cached", validation_alias="APP_MODE"
    )
    run_ttl_seconds: Annotated[int, Field(ge=1, le=3600)] = Field(
        default=3600, validation_alias="RUN_TTL_SECONDS"
    )
    max_policy_chars: Annotated[int, Field(ge=1, le=50_000)] = Field(
        default=50_000, validation_alias="MAX_POLICY_CHARS"
    )
    llm_provider: Literal["openai"] = Field(
        default="openai", validation_alias="LLM_PROVIDER"
    )
    llm_model: str | None = Field(default=None, validation_alias="LLM_MODEL")
    llm_base_url: str | None = Field(default=None, validation_alias="LLM_BASE_URL")
    openai_api_key: SecretStr | None = Field(
        default=None, validation_alias="OPENAI_API_KEY", repr=False
    )
    llm_timeout_seconds: Annotated[float, Field(gt=0, le=120, allow_inf_nan=False)] = (
        Field(default=30.0, validation_alias="LLM_TIMEOUT_SECONDS")
    )

    @field_validator("llm_model", mode="before")
    @classmethod
    def normalize_optional_model(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def normalize_optional_key(cls, value: object) -> object:
        if isinstance(value, SecretStr):
            return value if value.get_secret_value().strip() else None
        if isinstance(value, str):
            return value if value.strip() else None
        return value


__all__ = ["Settings"]
