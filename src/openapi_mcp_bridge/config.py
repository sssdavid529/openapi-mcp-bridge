"""Runtime configuration sourced exclusively from environment variables.

No credential is ever hard-coded. Every secret is read from an ``OPENAPI_MCP_*``
environment variable, and secret-bearing fields are declared with ``repr=False``
so they cannot leak into logs or tracebacks via a stray ``repr()``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .errors import ConfigError

ENV_PREFIX = "OPENAPI_MCP_"
DEFAULT_TIMEOUT = 30.0

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _env(name: str) -> str | None:
    """Return a stripped, non-empty environment value for ``OPENAPI_MCP_<name>``."""
    raw = os.environ.get(ENV_PREFIX + name)
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    lowered = value.strip().lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    raise ConfigError(f"{ENV_PREFIX}VERIFY_TLS must be a boolean, got {value!r}")


@dataclass
class Config:
    """Resolved runtime configuration.

    Attributes:
        base_url: Overrides the server URL declared in the spec when set.
        timeout: Per-request timeout in seconds.
        verify_tls: Whether to verify TLS certificates on outgoing requests.
        extra_headers: Arbitrary headers merged into every request (escape hatch
            for custom auth); these take precedence over derived auth headers.
        bearer_token: Value for ``Authorization: Bearer ...``.
        api_key: Secret injected for an ``apiKey`` security scheme.
        basic_username / basic_password: Credentials for HTTP Basic auth.
    """

    base_url: str | None = None
    timeout: float = DEFAULT_TIMEOUT
    verify_tls: bool = True
    extra_headers: dict[str, str] = field(default_factory=dict)
    bearer_token: str | None = field(default=None, repr=False)
    api_key: str | None = field(default=None, repr=False)
    basic_username: str | None = field(default=None, repr=False)
    basic_password: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> Config:
        """Build a :class:`Config` from the current process environment.

        Raises:
            ConfigError: If a variable is present but malformed.
        """
        timeout = DEFAULT_TIMEOUT
        raw_timeout = _env("TIMEOUT")
        if raw_timeout is not None:
            try:
                timeout = float(raw_timeout)
            except ValueError as exc:
                raise ConfigError(
                    f"{ENV_PREFIX}TIMEOUT must be a number, got {raw_timeout!r}"
                ) from exc
            if timeout <= 0:
                raise ConfigError(f"{ENV_PREFIX}TIMEOUT must be positive, got {timeout}")

        extra_headers: dict[str, str] = {}
        raw_headers = _env("EXTRA_HEADERS")
        if raw_headers is not None:
            try:
                parsed = json.loads(raw_headers)
            except json.JSONDecodeError as exc:
                raise ConfigError(f"{ENV_PREFIX}EXTRA_HEADERS must be valid JSON") from exc
            if not isinstance(parsed, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()
            ):
                raise ConfigError(
                    f"{ENV_PREFIX}EXTRA_HEADERS must be a JSON object mapping string to string"
                )
            extra_headers = parsed

        return cls(
            base_url=_env("BASE_URL"),
            timeout=timeout,
            verify_tls=_parse_bool(_env("VERIFY_TLS"), default=True),
            extra_headers=extra_headers,
            bearer_token=_env("TOKEN"),
            api_key=_env("API_KEY"),
            basic_username=_env("BASIC_USERNAME"),
            basic_password=_env("BASIC_PASSWORD"),
        )

    @property
    def has_basic_auth(self) -> bool:
        return self.basic_username is not None or self.basic_password is not None
