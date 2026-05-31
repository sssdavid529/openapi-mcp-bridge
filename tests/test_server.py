"""End-to-end tests for the assembled MCP server."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import httpx
import mcp.types as types
import pytest

from openapi_mcp_bridge.config import Config
from openapi_mcp_bridge.http_client import ApiProxy
from openapi_mcp_bridge.server import BridgeServer, build_server
from openapi_mcp_bridge.spec_loader import resolve_refs
from openapi_mcp_bridge.tool_generator import generate_tool_defs, parse_spec

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
async def server_factory(petstore_doc: dict) -> AsyncIterator[Callable[..., BridgeServer]]:
    """Build a BridgeServer wired to a mock HTTP transport; close clients on teardown."""
    clients: list[httpx.AsyncClient] = []

    def _make(handler: Handler, config: Config | None = None) -> BridgeServer:
        spec = parse_spec(
            resolve_refs(petstore_doc), source_ref="https://api.petstore.example/openapi.json"
        )
        tool_defs = generate_tool_defs(spec)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        clients.append(client)
        proxy = ApiProxy(spec, config or Config(), client=client)
        return build_server(spec.title or "test", tool_defs, proxy)

    yield _make

    for client in clients:
        await client.aclose()


def _ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"id": "123", "name": "Rex"})


async def test_list_tools_exposes_every_operation(server_factory) -> None:
    server = server_factory(_ok)
    tools = await server.list_tools()
    assert all(isinstance(tool, types.Tool) for tool in tools)
    assert {tool.name for tool in tools} == {"listPets", "createPet", "getPet"}


async def test_call_tool_success(server_factory) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"id": "123", "name": "Rex"})

    server = server_factory(handler)
    result = await server.call_tool("getPet", {"petId": "123"})

    assert isinstance(result, types.CallToolResult)
    assert result.isError is False
    assert captured["url"] == "https://api.petstore.example/v1/pets/123"
    assert "HTTP 200" in result.content[0].text
    assert "Rex" in result.content[0].text


async def test_call_unknown_tool_is_error(server_factory) -> None:
    server = server_factory(_ok)
    result = await server.call_tool("nope", {})
    assert result.isError is True
    assert "Unknown tool" in result.content[0].text


async def test_call_tool_validates_required_args(server_factory) -> None:
    server = server_factory(_ok)
    result = await server.call_tool("getPet", {})  # missing required petId
    assert result.isError is True
    assert "Invalid arguments" in result.content[0].text


async def test_call_tool_surfaces_proxy_errors(server_factory) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    server = server_factory(boom)
    result = await server.call_tool("getPet", {"petId": "123"})
    assert result.isError is True
    assert "Error" in result.content[0].text


async def test_post_tool_sends_body(server_factory) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["content"] = request.content
        return httpx.Response(201, json={"id": "1"})

    server = server_factory(handler)
    result = await server.call_tool("createPet", {"body": {"name": "Rex"}})
    assert result.isError is False
    import json

    assert json.loads(captured["content"]) == {"name": "Rex"}
