"""Command-line entry point.

Parses arguments, loads configuration from the environment, builds the bridge,
and serves it over stdio (default) or SSE (``--transport sse``). All diagnostics
go to **stderr**: stdout is reserved for the MCP protocol stream.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from . import __version__
from .config import Config
from .errors import BridgeError
from .http_client import ApiProxy
from .models import ParsedSpec, ToolDef
from .server import build_server
from .spec_loader import load_spec, resolve_refs
from .tool_generator import generate_tool_defs, parse_spec

logger = logging.getLogger("openapi_mcp_bridge")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openapi-mcp-bridge",
        description=(
            "Expose every endpoint of an OpenAPI/Swagger specification as an MCP "
            "tool, served over stdio or SSE."
        ),
    )
    parser.add_argument(
        "--spec",
        required=True,
        help="OpenAPI/Swagger spec to load: an http(s) URL or a file path.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Override the API server base URL from the spec.",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="MCP server name (defaults to the spec's info.title).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Per-request HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Print the generated tools and exit without starting the server.",
    )
    # --- Tag filtering ---
    parser.add_argument(
        "--include-tags",
        nargs="+",
        default=None,
        metavar="TAG",
        help="Only expose endpoints whose tags include at least one of these values.",
    )
    parser.add_argument(
        "--exclude-tags",
        nargs="+",
        default=None,
        metavar="TAG",
        help="Exclude endpoints whose tags include any of these values.",
    )
    # --- Transport ---
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse"),
        default="stdio",
        help="MCP transport to use (default: stdio).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind when --transport sse (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on when --transport sse (default: 8000).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def _load(
    spec_ref: str,
    config: Config,
    *,
    include_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
) -> tuple[ParsedSpec, list[ToolDef]]:
    document = load_spec(spec_ref, timeout=config.timeout)
    document = resolve_refs(document)
    spec = parse_spec(document, source_ref=spec_ref, base_url_override=config.base_url)
    tool_defs = generate_tool_defs(spec, include_tags=include_tags, exclude_tags=exclude_tags)
    return spec, tool_defs


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    args = build_arg_parser().parse_args(argv)

    try:
        config = Config.from_env()
    except BridgeError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    if args.base_url:
        config.base_url = args.base_url
    if args.timeout is not None:
        config.timeout = args.timeout

    try:
        spec, tool_defs = _load(
            args.spec,
            config,
            include_tags=args.include_tags,
            exclude_tags=args.exclude_tags,
        )
    except BridgeError as exc:
        print(f"Failed to load spec: {exc}", file=sys.stderr)
        return 1

    if not tool_defs:
        print("Warning: no operations were found in the specification.", file=sys.stderr)

    server_name = args.name or spec.title or "openapi-mcp-bridge"

    if args.list_tools:
        for tool in tool_defs:
            extra = ""
            if tool.operation.tags:
                extra = f"\t[{', '.join(tool.operation.tags)}]"
            print(f"{tool.name}\t{tool.operation.method} {tool.operation.path}{extra}")
        return 0

    if args.transport == "sse" and not (config.base_url or spec.base_url):
        print(
            "Error: could not determine the API base URL. "
            "Set OPENAPI_MCP_BASE_URL or pass --base-url.",
            file=sys.stderr,
        )
        return 1

    proxy = ApiProxy(spec, config)
    server = build_server(server_name, tool_defs, proxy)

    if args.transport == "sse":
        logger.info(
            "Serving %d tool(s) as MCP server %r over SSE on %s:%d",
            len(tool_defs),
            server_name,
            args.host,
            args.port,
        )
        try:
            asyncio.run(server.serve_sse(host=args.host, port=args.port))
        except KeyboardInterrupt:  # pragma: no cover
            return 130
    else:
        logger.info("Serving %d tool(s) as MCP server %r over stdio", len(tool_defs), server_name)
        try:
            asyncio.run(server.serve_stdio())
        except KeyboardInterrupt:  # pragma: no cover
            return 130
    return 0
