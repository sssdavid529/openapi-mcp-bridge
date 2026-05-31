# openapi-mcp-bridge

[![CI](https://github.com/sssdavid529/openapi-mcp-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/sssdavid529/openapi-mcp-bridge/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/openapi-mcp-bridge.svg)](https://pypi.org/project/openapi-mcp-bridge/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Turn **any** OpenAPI/Swagger API into [Model Context Protocol](https://modelcontextprotocol.io)
tools. Point the bridge at a spec (URL or local file) and every endpoint becomes
an MCP tool that an AI assistant — Claude Desktop, or any MCP client — can call
directly. The bridge constructs the real HTTP request, sends it, and returns the
response to the model.

- 🔧 **One tool per endpoint** — names from `operationId`, JSON Schema inputs
  built from parameters and request bodies.
- 📥 **OpenAPI 3.x and Swagger 2.0** — both normalised to the same model.
- 🔌 **stdio and SSE transports** — local or remote, built on the official
  [`mcp`](https://pypi.org/project/mcp/) SDK.
- 🏷️ **Tag filtering** — `--include-tags` / `--exclude-tags` to expose only
  the endpoints your AI assistant needs.
- 🔒 **No secrets in code** — every credential comes from an environment variable.
- ✅ **Typed, tested, and linted** — 77 tests, ruff, CI across Python 3.10–3.13.

## Installation

```bash
pip install openapi-mcp-bridge
```

Or install it as an isolated CLI tool:

```bash
pipx install openapi-mcp-bridge
```

It requires Python 3.10+.

## Quickstart

List the tools generated from the public Swagger Petstore spec (this does **not**
start a server — handy for inspecting what will be exposed):

```bash
openapi-mcp-bridge --spec https://petstore3.swagger.io/api/v3/openapi.json --list-tools
```

Filter by tags to expose only a subset of a large API:

```bash
openapi-mcp-bridge --spec https://petstore3.swagger.io/api/v3/openapi.json \
  --list-tools --include-tags pet store
```

Run it as an MCP server over stdio:

```bash
openapi-mcp-bridge --spec https://petstore3.swagger.io/api/v3/openapi.json
```

Or over SSE (HTTP + Server-Sent Events) for remote MCP clients:

```bash
openapi-mcp-bridge --spec https://petstore3.swagger.io/api/v3/openapi.json \
  --transport sse --host 0.0.0.0 --port 8080
```

You can also invoke it as a module:

```bash
python -m openapi_mcp_bridge --spec ./openapi.yaml
```

## Use with Claude Desktop

### stdio (local)

Add an entry to your `claude_desktop_config.json`:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "petstore": {
      "command": "openapi-mcp-bridge",
      "args": ["--spec", "https://petstore3.swagger.io/api/v3/openapi.json"],
      "env": {
        "OPENAPI_MCP_TOKEN": "your-bearer-token-here"
      }
    }
  }
}
```

### SSE (remote / browser clients)

Start the bridge in SSE mode, then point your MCP client at
`http://localhost:8000/sse`:

```json
{
  "mcpServers": {
    "petstore": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

If you do not have the console script on your `PATH`, you can run it with
[`uv`](https://docs.astral.sh/uv/) without installing anything:

```json
{
  "mcpServers": {
    "petstore": {
      "command": "uvx",
      "args": [
        "openapi-mcp-bridge",
        "--spec",
        "https://petstore3.swagger.io/api/v3/openapi.json"
      ]
    }
  }
}
```

## Command-line options

| Option | Description |
| --- | --- |
| `--spec` (required) | OpenAPI/Swagger spec to load: an `http(s)` URL or a file path. |
| `--transport` | MCP transport: `stdio` (default) or `sse`. |
| `--host` | Host for SSE transport (default `127.0.0.1`). |
| `--port` | Port for SSE transport (default `8000`). |
| `--base-url` | Override the API server base URL declared in the spec. |
| `--name` | MCP server name (defaults to the spec's `info.title`). |
| `--timeout` | Per-request HTTP timeout in seconds (default `30`). |
| `--include-tags` | Only expose endpoints matching at least one of these tags. |
| `--exclude-tags` | Exclude endpoints matching any of these tags. |
| `--list-tools` | Print the generated tools and exit without starting the server. |
| `--version` | Print the version and exit. |

## Configuration & authentication

Credentials and connection settings are read from environment variables. **No
secret is ever stored in code or in the spec.**

| Variable | Purpose |
| --- | --- |
| `OPENAPI_MCP_BASE_URL` | Override the API base URL (same as `--base-url`). |
| `OPENAPI_MCP_TOKEN` | Bearer token → `Authorization: Bearer <token>`. |
| `OPENAPI_MCP_API_KEY` | Secret for an `apiKey` scheme; the header/query name and location are taken from the spec (default header `X-API-Key`). |
| `OPENAPI_MCP_BASIC_USERNAME` / `OPENAPI_MCP_BASIC_PASSWORD` | HTTP Basic credentials. |
| `OPENAPI_MCP_EXTRA_HEADERS` | JSON object of extra headers merged into every request; overrides derived auth headers. |
| `OPENAPI_MCP_TIMEOUT` | Per-request timeout in seconds (same as `--timeout`). |
| `OPENAPI_MCP_VERIFY_TLS` | Set to `false`/`0`/`no` to disable TLS verification (not recommended). |

A bearer token takes priority over basic credentials. Need a custom auth header
the spec doesn't describe? Use `OPENAPI_MCP_EXTRA_HEADERS`, e.g.
`{"X-Custom-Auth": "value"}`.

## How it works

1. **Load** the spec from a URL or file (JSON or YAML) and resolve intra-document
   `$ref` pointers, with cycle protection.
2. **Normalise** OpenAPI 3.x / Swagger 2.0 into a single internal model of
   operations, parameters, request bodies, and security schemes.
3. **Filter** (optional) by tags to expose only the endpoints your AI assistant
   needs.
4. **Generate** one MCP tool per operation. Path/query/header parameters become
   top-level JSON Schema properties; the request body becomes a `body` property.
5. **Proxy** each tool call to a real HTTP request — substituting path
   parameters, attaching the query string, injecting auth, and sending the body —
   then return the status line and response body to the model.

## Security

See [SECURITY.md](SECURITY.md) for details on how credentials are handled and
how to report vulnerabilities.

## Development

```bash
git clone https://github.com/sssdavid529/openapi-mcp-bridge.git
cd openapi-mcp-bridge
python -m venv .venv && pip install -e ".[dev]"
ruff check . && ruff format --check . && pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for more.

## License

[MIT](LICENSE)
