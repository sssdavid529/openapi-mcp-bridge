"""Tests for environment-based configuration."""

from __future__ import annotations

import pytest

from openapi_mcp_bridge.config import Config
from openapi_mcp_bridge.errors import ConfigError

_ALL_VARS = [
    "OPENAPI_MCP_BASE_URL",
    "OPENAPI_MCP_TIMEOUT",
    "OPENAPI_MCP_VERIFY_TLS",
    "OPENAPI_MCP_EXTRA_HEADERS",
    "OPENAPI_MCP_TOKEN",
    "OPENAPI_MCP_API_KEY",
    "OPENAPI_MCP_BASIC_USERNAME",
    "OPENAPI_MCP_BASIC_PASSWORD",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _ALL_VARS:
        monkeypatch.delenv(var, raising=False)


def test_defaults() -> None:
    config = Config.from_env()
    assert config.base_url is None
    assert config.timeout == 30.0
    assert config.verify_tls is True
    assert config.extra_headers == {}
    assert config.bearer_token is None


def test_reads_all_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAPI_MCP_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("OPENAPI_MCP_TIMEOUT", "12.5")
    monkeypatch.setenv("OPENAPI_MCP_TOKEN", "tok")
    monkeypatch.setenv("OPENAPI_MCP_API_KEY", "key")
    monkeypatch.setenv("OPENAPI_MCP_BASIC_USERNAME", "u")
    monkeypatch.setenv("OPENAPI_MCP_BASIC_PASSWORD", "p")
    monkeypatch.setenv("OPENAPI_MCP_EXTRA_HEADERS", '{"X-Trace": "1"}')

    config = Config.from_env()
    assert config.base_url == "https://api.example.com"
    assert config.timeout == 12.5
    assert config.bearer_token == "tok"
    assert config.api_key == "key"
    assert config.has_basic_auth
    assert config.extra_headers == {"X-Trace": "1"}


def test_blank_values_treated_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAPI_MCP_TOKEN", "   ")
    assert Config.from_env().bearer_token is None


@pytest.mark.parametrize("value", ["false", "0", "no", "off", "FALSE"])
def test_verify_tls_false(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("OPENAPI_MCP_VERIFY_TLS", value)
    assert Config.from_env().verify_tls is False


def test_invalid_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAPI_MCP_TIMEOUT", "not-a-number")
    with pytest.raises(ConfigError, match="TIMEOUT"):
        Config.from_env()


def test_non_positive_timeout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAPI_MCP_TIMEOUT", "0")
    with pytest.raises(ConfigError, match="positive"):
        Config.from_env()


def test_invalid_extra_headers_json_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAPI_MCP_EXTRA_HEADERS", "{not json")
    with pytest.raises(ConfigError, match="valid JSON"):
        Config.from_env()


def test_extra_headers_must_be_object_of_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAPI_MCP_EXTRA_HEADERS", '{"x": 1}')
    with pytest.raises(ConfigError, match="string to string"):
        Config.from_env()


def test_invalid_verify_tls_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAPI_MCP_VERIFY_TLS", "maybe")
    with pytest.raises(ConfigError, match="boolean"):
        Config.from_env()


def test_secrets_not_in_repr() -> None:
    config = Config(
        bearer_token="TOKEN_SECRET_VALUE",
        api_key="APIKEY_SECRET_VALUE",
        basic_username="USERNAME_SECRET",
        basic_password="PASSWORD_SECRET",
    )
    rendered = repr(config)
    assert "TOKEN_SECRET_VALUE" not in rendered
    assert "APIKEY_SECRET_VALUE" not in rendered
    assert "PASSWORD_SECRET" not in rendered
    assert "USERNAME_SECRET" not in rendered
