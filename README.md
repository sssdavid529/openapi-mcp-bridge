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
- 🔌 **stdio transport** built on the official [`mcp`](https://pypi.org/project/mcp/) SDK.
- 🔒 **No secrets in code** — every credential comes from an environment variable.
- ✅ **Typed, tested, and linted.**

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

Run it as an MCP server over stdio:

```bash
openapi-mcp-bridge --spec https://petstore3.swagger.io/api/v3/openapi.json
```

You can also invoke it as a module:

```bash
python -m openapi_mcp_bridge --spec ./openapi.yaml
```

## Use with Claude Desktop

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

Restart Claude Desktop after editing the config. The same `command`/`args`/`env`
shape works for any MCP client (e.g. Cursor, Continue, or a custom one).

## Command-line options

| Option | Description |
| --- | --- |
| `--spec` (required) | OpenAPI/Swagger spec to load: an `http(s)` URL or a file path. |
| `--base-url` | Override the API server base URL declared in the spec. |
| `--name` | MCP server name (defaults to the spec's `info.title`). |
| `--timeout` | Per-request HTTP timeout in seconds (default `30`). |
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
3. **Generate** one MCP tool per operation. Path/query/header parameters become
   top-level JSON Schema properties; the request body becomes a `body` property.
4. **Proxy** each tool call to a real HTTP request — substituting path
   parameters, attaching the query string, injecting auth, and sending the body —
   then return the status line and response body to the model.

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
