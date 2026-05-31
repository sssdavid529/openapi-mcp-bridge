"""openapi-mcp-bridge: expose any OpenAPI/Swagger API as MCP tools over stdio."""

from __future__ import annotations

from .config import Config
from .errors import BridgeError, ConfigError, SpecError, ToolInvocationError
from .http_client import ApiProxy
from .models import Operation, Parameter, ParsedSpec, SecurityScheme, ToolDef
from .server import BridgeServer, build_server
from .spec_loader import detect_version, load_spec, resolve_refs
from .tool_generator import generate_tool_defs, parse_spec

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "ApiProxy",
    "BridgeError",
    "BridgeServer",
    "Config",
    "ConfigError",
    "Operation",
    "Parameter",
    "ParsedSpec",
    "SecurityScheme",
    "SpecError",
    "ToolDef",
    "ToolInvocationError",
    "build_server",
    "detect_version",
    "generate_tool_defs",
    "load_spec",
    "parse_spec",
    "resolve_refs",
]
