# Contributing

Thanks for your interest in improving **openapi-mcp-bridge**! Contributions of
all kinds are welcome — bug reports, documentation, and code.

## Development setup

```bash
git clone https://github.com/sssdavid529/openapi-mcp-bridge.git
cd openapi-mcp-bridge
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

## Checks before opening a PR

The CI runs the same three commands; please run them locally first:

```bash
ruff check .            # lint
ruff format --check .   # formatting
pytest                  # tests
```

Run `ruff format .` to auto-format and `ruff check --fix .` to auto-fix lint
issues.

## Guidelines

- Keep full type annotations and docstrings on public functions.
- Add or update tests for any behavioural change; the suite mocks HTTP with
  `httpx.MockTransport`, so tests need no network access.
- **Never commit secrets.** All credentials are supplied at runtime through
  `OPENAPI_MCP_*` environment variables.
- Keep modules focused: spec loading, normalisation/tool generation, HTTP
  proxying, and server wiring live in separate modules.

## Reporting bugs

Open an issue with the spec (or a minimal excerpt) that reproduces the problem,
the command you ran, and what you expected versus what happened.
