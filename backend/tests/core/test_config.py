from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_defaults_are_cached_and_do_not_require_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "APP_MODE",
        "RUN_TTL_SECONDS",
        "MAX_POLICY_CHARS",
        "LLM_PROVIDER",
        "LLM_MODEL",
        "OPENAI_API_KEY",
        "LLM_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings()

    assert settings.app_mode == "cached"
    assert settings.run_ttl_seconds == 3600
    assert settings.max_policy_chars == 50_000
    assert settings.llm_provider == "openai"
    assert settings.llm_model is None
    assert settings.openai_api_key is None
    assert settings.llm_timeout_seconds == 30


def test_settings_use_documented_environment_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_MODE", "live")
    monkeypatch.setenv("RUN_TTL_SECONDS", "120")
    monkeypatch.setenv("MAX_POLICY_CHARS", "4000")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "synthetic-model")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-secret")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "12.5")

    settings = Settings()

    assert settings.app_mode == "live"
    assert settings.run_ttl_seconds == 120
    assert settings.max_policy_chars == 4000
    assert settings.llm_model == "synthetic-model"
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "synthetic-secret"
    assert settings.llm_timeout_seconds == 12.5
    assert "synthetic-secret" not in repr(settings)


def test_blank_optional_provider_values_normalize_to_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MODEL", "   ")
    monkeypatch.setenv("OPENAI_API_KEY", "   ")

    settings = Settings()

    assert settings.llm_model is None
    assert settings.openai_api_key is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("app_mode", "unknown"),
        ("run_ttl_seconds", 0),
        ("run_ttl_seconds", 3601),
        ("max_policy_chars", 0),
        ("max_policy_chars", 50_001),
        ("llm_provider", "other"),
        ("llm_timeout_seconds", 0),
        ("llm_timeout_seconds", 121),
    ],
)
def test_settings_reject_values_outside_fixed_bounds(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_settings_validation_does_not_expose_secret_input() -> None:
    canary = "private-secret-that-must-not-appear"

    with pytest.raises(ValidationError) as raised:
        Settings(openai_api_key={"invalid": canary})

    assert canary not in str(raised.value)


def test_settings_never_reads_dotenv_implicitly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APP_MODE", raising=False)
    (tmp_path / ".env").write_text("APP_MODE=live\n", encoding="utf-8")

    assert Settings().app_mode == "cached"
