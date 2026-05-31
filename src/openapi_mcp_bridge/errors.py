"""Exception hierarchy for :mod:`openapi_mcp_bridge`.

A small, explicit set of exceptions keeps error handling readable across the
package: configuration problems, spec problems, and runtime call problems are
distinguishable by type while all deriving from a single base.
"""

from __future__ import annotations


class BridgeError(Exception):
    """Base class for every error raised by this package."""


class ConfigError(BridgeError):
    """Raised when environment-based configuration is invalid."""


class SpecError(BridgeError):
    """Raised when an OpenAPI/Swagger document cannot be loaded or parsed."""


class ToolInvocationError(BridgeError):
    """Raised when the HTTP call backing a tool invocation cannot be made."""
