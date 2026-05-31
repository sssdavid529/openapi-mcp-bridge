"""Version-agnostic data model for parsed API specifications.

Both OpenAPI 3.x and Swagger 2.0 documents are normalised into the dataclasses
defined here. Everything downstream (tool generation, HTTP proxying) operates on
these models only, so the version-specific quirks stay contained in
:mod:`openapi_mcp_bridge.tool_generator`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ParameterLocation = Literal["path", "query", "header", "cookie"]


@dataclass
class Parameter:
    """A single operation parameter living in the path, query, or headers."""

    name: str
    location: ParameterLocation
    required: bool = False
    schema: dict[str, Any] = field(default_factory=dict)
    description: str | None = None


@dataclass
class SecurityScheme:
    """A normalised security scheme.

    ``type`` is one of ``"http"``, ``"apiKey"`` or ``"oauth2"``. For ``http`` the
    ``scheme`` field carries ``"bearer"`` or ``"basic"``; for ``apiKey`` the
    ``name``/``location`` fields carry the parameter name and where it goes
    (``"header"``, ``"query"`` or ``"cookie"``).
    """

    type: str
    scheme: str | None = None
    name: str | None = None
    location: str | None = None


@dataclass
class Operation:
    """A single HTTP operation derived from one path + method."""

    operation_id: str
    method: str  # upper-case HTTP method, e.g. "GET"
    path: str  # templated path, e.g. "/pets/{petId}"
    parameters: tuple[Parameter, ...] = ()
    request_body_schema: dict[str, Any] | None = None
    request_body_required: bool = False
    request_body_content_type: str = "application/json"
    summary: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()


@dataclass
class ParsedSpec:
    """The fully normalised result of parsing a specification document."""

    title: str | None
    base_url: str | None
    operations: list[Operation]
    security_schemes: dict[str, SecurityScheme] = field(default_factory=dict)
    spec_version: str = "openapi-3"


@dataclass
class ToolDef:
    """An MCP tool definition together with the operation that backs it.

    ``input_schema`` is a plain JSON Schema dict (so this module stays free of
    any MCP SDK import); :mod:`openapi_mcp_bridge.server` wraps it into the SDK's
    ``types.Tool`` and uses ``operation`` to proxy the call.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    operation: Operation
