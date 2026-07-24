import importlib

import pytest

from src.core import config


def test_database_url_can_be_overridden_for_isolated_runtime_checks(
    monkeypatch,
    tmp_path,
):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'slice9.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    reloaded_config = importlib.reload(config)

    assert reloaded_config.DATABASE_URL == database_url

    monkeypatch.delenv("DATABASE_URL")
    importlib.reload(config)


def test_redis_settings_allow_disabled_redis_without_url(monkeypatch):
    monkeypatch.setattr(config, "REDIS_ENABLED", False)
    monkeypatch.setattr(config, "REDIS_URL", None)

    config.validate_redis_settings()


def test_redis_settings_reject_enabled_redis_without_url(monkeypatch):
    monkeypatch.setattr(config, "REDIS_ENABLED", True)
    monkeypatch.setattr(config, "REDIS_URL", None)

    with pytest.raises(RuntimeError, match="REDIS_URL is missing"):
        config.validate_redis_settings()


def test_redis_settings_reject_invalid_url_scheme(monkeypatch):
    monkeypatch.setattr(config, "REDIS_ENABLED", True)
    monkeypatch.setattr(config, "REDIS_URL", "http://localhost:6379")

    with pytest.raises(RuntimeError, match="REDIS_URL must start"):
        config.validate_redis_settings()


@pytest.mark.parametrize(
    "url",
    [
        "redis://localhost:6379/0",
        "rediss://redis.example.com:6379/0",
        "unix:///run/redis/redis.sock",
    ],
)
def test_redis_settings_accept_supported_url_schemes(monkeypatch, url):
    monkeypatch.setattr(config, "REDIS_ENABLED", True)
    monkeypatch.setattr(config, "REDIS_URL", url)

    config.validate_redis_settings()


def test_fake_analyzer_does_not_require_openrouter_key(monkeypatch):
    monkeypatch.setattr(config, "ANALYZER_PROVIDER", "fake")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", None)
    monkeypatch.setattr(config, "OPENROUTER_TIMEOUT_SECONDS", 20)

    config.validate_analyzer_settings()


def test_openrouter_analyzer_requires_key(monkeypatch):
    monkeypatch.setattr(config, "ANALYZER_PROVIDER", "openrouter")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", None)
    monkeypatch.setattr(config, "OPENROUTER_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setattr(config, "OPENROUTER_TIMEOUT_SECONDS", 20)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY is required"):
        config.validate_analyzer_settings()


@pytest.mark.parametrize("provider", ["", "local", "OPENROUTER"])
def test_analyzer_rejects_unsupported_normalized_provider(monkeypatch, provider):
    monkeypatch.setattr(config, "ANALYZER_PROVIDER", provider)

    with pytest.raises(RuntimeError, match="must be fake or openrouter"):
        config.validate_analyzer_settings()


def test_analyzer_rejects_nonpositive_timeout(monkeypatch):
    monkeypatch.setattr(config, "ANALYZER_PROVIDER", "fake")
    monkeypatch.setattr(config, "OPENROUTER_TIMEOUT_SECONDS", 0)

    with pytest.raises(RuntimeError, match="must be greater than zero"):
        config.validate_analyzer_settings()
