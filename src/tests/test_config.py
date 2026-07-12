import pytest

from src.core import config


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
