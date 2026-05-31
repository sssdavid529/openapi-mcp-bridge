"""Tests for the HTTP proxy: request construction, auth injection, errors."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from openapi_mcp_bridge.config import Config
from openapi_mcp_bridge.errors import ToolInvocationError
from openapi_mcp_bridge.http_client import ApiProxy
from openapi_mcp_bridge.models import Operation, Parameter, ParsedSpec, SecurityScheme

BASE_URL = "https://api.example.com/v1"


def _spec(base_url: str | None = BASE_URL, security: dict | None = None) -> ParsedSpec:
    return ParsedSpec(
        title="Test",
        base_url=base_url,
        operations=[],
        security_schemes=security or {},
    )


def _proxy(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    config: Config | None = None,
    spec: ParsedSpec | None = None,
) -> ApiProxy:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ApiProxy(spec or _spec(), config or Config(), client=client)


def _capture() -> tuple[dict, Callable[[httpx.Request], httpx.Response]]:
    box: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        box["request"] = request
        return httpx.Response(200, json={"ok": True})

    return box, handler


async def test_get_with_path_and_query() -> None:
    box, handler = _capture()
    proxy = _proxy(handler)
    op = Operation(
        operation_id="getPet",
        method="GET",
        path="/pets/{petId}",
        parameters=(
            Parameter("petId", "path", required=True, schema={"type": "string"}),
            Parameter("limit", "query", schema={"type": "integer"}),
        ),
    )
    result = await proxy.call(op, {"petId": "a b", "limit": 5})
    request = box["request"]
    assert request.method == "GET"
    assert str(request.url) == "https://api.example.com/v1/pets/a%20b?limit=5"
    assert "HTTP 200" in result


async def test_post_json_body() -> None:
    box, handler = _capture()
    proxy = _proxy(handler)
    op = Operation(
        operation_id="createPet",
        method="POST",
        path="/pets",
        request_body_schema={"type": "object"},
        request_body_required=True,
        request_body_content_type="application/json",
    )
    await proxy.call(op, {"body": {"name": "Rex", "tag": "dog"}})
    request = box["request"]
    assert request.method == "POST"
    assert json.loads(request.content) == {"name": "Rex", "tag": "dog"}
    assert request.headers["content-type"].startswith("application/json")


async def test_header_param_is_sent() -> None:
    box, handler = _capture()
    proxy = _proxy(handler)
    op = Operation(
        operation_id="op",
        method="GET",
        path="/x",
        parameters=(Parameter("X-Trace", "header", schema={"type": "string"}),),
    )
    await proxy.call(op, {"X-Trace": "abc123"})
    assert box["request"].headers["X-Trace"] == "abc123"


async def test_bearer_token_header() -> None:
    box, handler = _capture()
    proxy = _proxy(handler, config=Config(bearer_token="secret-token"))
    op = Operation(operation_id="op", method="GET", path="/x")
    await proxy.call(op, {})
    assert box["request"].headers["Authorization"] == "Bearer secret-token"


async def test_basic_auth_header() -> None:
    box, handler = _capture()
    proxy = _proxy(handler, config=Config(basic_username="user", basic_password="pass"))
    op = Operation(operation_id="op", method="GET", path="/x")
    await proxy.call(op, {})
    # base64("user:pass") == "dXNlcjpwYXNz"
    assert box["request"].headers["Authorization"] == "Basic dXNlcjpwYXNz"


async def test_api_key_in_header() -> None:
    box, handler = _capture()
    spec = _spec(security={"k": SecurityScheme(type="apiKey", name="X-Api-Key", location="header")})
    proxy = _proxy(handler, config=Config(api_key="key-123"), spec=spec)
    op = Operation(operation_id="op", method="GET", path="/x")
    await proxy.call(op, {})
    assert box["request"].headers["X-Api-Key"] == "key-123"


async def test_api_key_in_query() -> None:
    box, handler = _capture()
    spec = _spec(security={"k": SecurityScheme(type="apiKey", name="api_key", location="query")})
    proxy = _proxy(handler, config=Config(api_key="key-123"), spec=spec)
    op = Operation(operation_id="op", method="GET", path="/x")
    await proxy.call(op, {})
    assert box["request"].url.params["api_key"] == "key-123"


async def test_extra_headers_override_auth() -> None:
    box, handler = _capture()
    spec = _spec(security={"k": SecurityScheme(type="apiKey", name="X-Api-Key", location="header")})
    config = Config(api_key="key-123", extra_headers={"X-Api-Key": "override"})
    proxy = _proxy(handler, config=config, spec=spec)
    op = Operation(operation_id="op", method="GET", path="/x")
    await proxy.call(op, {})
    assert box["request"].headers["X-Api-Key"] == "override"


async def test_missing_base_url_raises() -> None:
    _, handler = _capture()
    proxy = _proxy(handler, spec=_spec(base_url=None))
    op = Operation(operation_id="op", method="GET", path="/x")
    with pytest.raises(ToolInvocationError, match="base URL"):
        await proxy.call(op, {})


async def test_missing_path_param_raises() -> None:
    _, handler = _capture()
    proxy = _proxy(handler)
    op = Operation(
        operation_id="getPet",
        method="GET",
        path="/pets/{petId}",
        parameters=(Parameter("petId", "path", required=True),),
    )
    with pytest.raises(ToolInvocationError, match="path parameter"):
        await proxy.call(op, {})


async def test_non_2xx_is_returned_not_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    proxy = _proxy(handler)
    op = Operation(operation_id="op", method="GET", path="/x")
    result = await proxy.call(op, {})
    assert "HTTP 404" in result
    assert "not found" in result


async def test_network_error_raises_tool_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    proxy = _proxy(handler)
    op = Operation(operation_id="op", method="GET", path="/x")
    with pytest.raises(ToolInvocationError, match="failed"):
        await proxy.call(op, {})


async def test_timeout_raises_tool_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow")

    proxy = _proxy(handler)
    op = Operation(operation_id="op", method="GET", path="/x")
    with pytest.raises(ToolInvocationError, match="timed out"):
        await proxy.call(op, {})


async def test_large_body_is_truncated() -> None:
    big = "x" * 250_000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=big)

    proxy = _proxy(handler)
    op = Operation(operation_id="op", method="GET", path="/x")
    result = await proxy.call(op, {})
    assert "[truncated" in result
    assert len(result) < len(big)
