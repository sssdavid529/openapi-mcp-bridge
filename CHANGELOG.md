# Changelog

All notable changes to openapi-mcp-bridge are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-05-31

### Added
- **SSE transport** (`--transport sse`) — serve over HTTP + Server-Sent Events
  via Starlette and uvicorn, with configurable `--host` and `--port`. Enables
  remote MCP clients and browser-based AI tools to use the bridge.
- **Endpoint tag filtering** (`--include-tags` / `--exclude-tags`) — filter
  which API endpoints become MCP tools by their OpenAPI `tags`. Operates on
  a union (include) / difference (exclude) basis; works with `--list-tools`
  and with the running server.
- `--list-tools` output now shows tags for each tool.

## [0.1.0] — 2026-05-31

### Added
- Initial release.
- OpenAPI 3.x and Swagger 2.0 spec loading from URL or local file (JSON/YAML).
- Intra-document `$ref` resolution with cycle protection.
- One MCP tool generated per API endpoint, with JSON Schema `inputSchema`
  derived from path/query/header parameters and request bodies.
- stdio transport via the official `mcp` SDK low-level Server.
- Environment-variable-based authentication (Bearer, API key, Basic) — no
  secrets in code.
- CLI with `--spec`, `--base-url`, `--name`, `--timeout`, `--list-tools`,
  `--version`.
- Full type annotations, docstrings, 57 pytest tests, ruff linting.
- CI matrix (Python 3.10–3.13, ruff, pytest) and PyPI Trusted Publishing
  workflow.

[0.2.0]: https://github.com/sssdavid529/openapi-mcp-bridge/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/sssdavid529/openapi-mcp-bridge/releases/tag/v0.1.0
