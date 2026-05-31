"""Assemble the MCP server: expose generated tools and route calls to the proxy.

Uses the official MCP SDK's low-level :class:`mcp.server.lowlevel.Server` because
tools are produced dynamically from a spec at runtime, which does not fit the
decorator-per-function model of ``FastMCP``.

Supports two transports:

* **stdio** (``serve_stdio``) — the default, for local MCP clients.
* **SSE** (``serve_sse``) — HTTP + Server-Sent Events via Starlette/uvicorn,
  for remote MCP clients and browser-based AI tools.
"""

from __future__ import annotations

import logging
from typing import Any

import jsonschema
import mcp.types as types
import uvicorn
from mcp.server.lowlevel import Server
from mcp.server.sse import SseServerTransport
from mcp.server.stdio import stdio_server
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from .http_client import ApiProxy
from .models import ToolDef

logger = logging.getLogger(__name__)

_SSE_ENDPOINT = "/messages/"


class BridgeServer:
    """An MCP server exposing one tool per operation of a parsed specification."""

    def __init__(self, name: str, tool_defs: list[ToolDef], proxy: ApiProxy) -> None:
        self.name = name
        self._proxy = proxy
        self._tools_by_name: dict[str, ToolDef] = {td.name: td for td in tool_defs}
        self._tools: list[types.Tool] = [
            types.Tool(name=td.name, description=td.description, inputSchema=td.input_schema)
            for td in tool_defs
        ]
        self.server: Server = Server(name)
        self._register_handlers()

    def _register_handlers(self) -> None:
        # Input validation is done in ``call_tool`` (see ``validate_input=False``)
        # so behaviour is identical whether reached via the SDK or called directly.
        # mypy: the mcp SDK decorators are untyped; ignore decorator-call
        # and untyped-context diagnostics on these two registration lines.
        @self.server.list_tools()  # type: ignore[untyped-decorator, no-untyped-call]
        async def _list_tools() -> Any:
            return await self.list_tools()

        @self.server.call_tool(validate_input=False)  # type: ignore[untyped-decorator]
        async def _call_tool(name: str, arguments: dict[str, Any] | None) -> Any:
            return await self.call_tool(name, arguments or {})

    async def list_tools(self) -> list[types.Tool]:
        """Return all tools generated from the specification."""
        return list(self._tools)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        """Validate arguments and proxy the call, never raising to the transport."""
        tool = self._tools_by_name.get(name)
        if tool is None:
            return _error_result(f"Unknown tool: {name!r}")

        try:
            jsonschema.validate(arguments, tool.input_schema)
        except jsonschema.ValidationError as exc:
            return _error_result(f"Invalid arguments for {name!r}: {exc.message}")

        try:
            text = await self._proxy.call(tool.operation, arguments)
        except Exception as exc:  # noqa: BLE001 - a failing tool must not kill the session
            logger.warning("Tool %r failed: %s", name, exc)
            return _error_result(str(exc))

        return types.CallToolResult(content=[types.TextContent(type="text", text=text)])

    async def serve_stdio(self) -> None:
        """Run the server over stdio until the client disconnects."""
        async with (
            self._proxy,
            stdio_server() as (read_stream, write_stream),
        ):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )

    async def serve_sse(self, *, host: str = "127.0.0.1", port: int = 8000) -> None:
        """Run the server over SSE (HTTP + Server-Sent Events).

        Starts a Starlette + uvicorn HTTP server. Each GET on ``/sse``
        establishes an SSE stream for server-to-client messages; the client
        sends JSON-RPC requests via POST to ``/messages/``.
        """
        sse = SseServerTransport(_SSE_ENDPOINT)

        async def handle_sse(request: Request) -> Response:
            init_options = self.server.create_initialization_options()
            async with sse.connect_sse(request.scope, request.receive, request._send) as (
                read_stream,
                write_stream,
            ):
                await self.server.run(read_stream, write_stream, init_options, stateless=True)
            return Response()

        async def handle_messages(request: Request) -> Response:
            await sse.handle_post_message(request.scope, request.receive, request._send)
            return Response()

        async with self._proxy:
            app = Starlette(
                routes=[
                    Route("/sse", endpoint=handle_sse),
                    Route(_SSE_ENDPOINT, endpoint=handle_messages, methods=["POST"]),
                ],
            )
            config = uvicorn.Config(app, host=host, port=port, log_level="warning")
            server = uvicorn.Server(config)
            await server.serve()


def _error_result(message: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=f"Error: {message}")],
        isError=True,
    )


def build_server(name: str, tool_defs: list[ToolDef], proxy: ApiProxy) -> BridgeServer:
    """Construct a :class:`BridgeServer` (functional-style convenience wrapper)."""
    return BridgeServer(name=name, tool_defs=tool_defs, proxy=proxy)
