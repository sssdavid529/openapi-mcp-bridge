# Security Policy

## Credential handling

**No credentials are ever hard-coded in this project.** Every secret is read
from an `OPENAPI_MCP_*` environment variable at startup. The configuration
dataclass marks credential fields with `repr=False`, so they do not appear in
stack traces or debug output.

### Principles

- **Bearer tokens**, **API keys**, **Basic auth credentials**, and **custom
  headers** are injected into outbound HTTP requests at call time and are never
  persisted, logged, or serialised.
- The `Authorization` header is only set if a token or username/password is
  explicitly provided via environment variables.
- Custom headers from `OPENAPI_MCP_EXTRA_HEADERS` override derived auth headers,
  giving operators full control.

### TLS verification

TLS certificate verification is **enabled by default**. It can be disabled with
`OPENAPI_MCP_VERIFY_TLS=false` (not recommended outside of development).

### Logging

All diagnostic output goes to **stderr**. stdout is reserved exclusively for
the MCP JSON-RPC protocol stream. No request bodies, response bodies, or
headers are logged at the default `INFO` level.

## Reporting a vulnerability

If you discover a security issue in openapi-mcp-bridge, please report it
privately via GitHub's **Security Advisory** system:

1. Go to the [Security tab](https://github.com/sssdavid529/openapi-mcp-bridge/security) of the repository.
2. Click **Report a vulnerability**.
3. Describe the issue with as much detail as possible.

We aim to acknowledge reports within 48 hours and publish fixes within 7 days.

> **Do not open a public issue for security vulnerabilities.**

## Supported versions

| Version | Supported |
| --- | --- |
| 0.2.x | ✅ |
| 0.1.x | ✅ |
