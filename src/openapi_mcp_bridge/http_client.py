"""Proxy MCP tool invocations to real HTTP API calls.

:class:`ApiProxy` takes a normalised :class:`~openapi_mcp_bridge.models.Operation`
plus the arguments supplied by the MCP client, builds the corresponding HTTP
request (path substitution, query string, headers, body), injects credentials
derived from :class:`~openapi_mcp_bridge.config.Config`, sends it, and renders the
response as text for the model to read.
"""

from __future__ import annotations

import base64
import json
import re
from types import TracebackType
from typing import Any
from urllib.parse import quote

import httpx

from .config import Config
from .errors import ToolInvocationError
from .models import Operation, ParsedSpec

_MAX_BODY_CHARS = 100_000
_DEFAULT_API_KEY_HEADER = "X-API-Key"
# Response headers worth surfacing to the model; everything else is noise.
_INTERESTING_HEADERS = ("content-type", "content-length", "location", "retry-after")


class ApiProxy:
    """Execute API calls for tool invocations against a single specification."""

    def __init__(
        self,
        spec: ParsedSpec,
        config: Config,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._spec = spec
        self._config = config
        self._client = client
        self._owns_client = client is None
        self._auth_headers, self._auth_query = _build_auth(spec, config)

    async def __aenter__(self) -> ApiProxy:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._config.timeout, verify=self._config.verify_tls
            )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def call(self, operation: Operation, arguments: dict[str, Any]) -> str:
        """Perform the HTTP call for ``operation`` and return a text result.

        Raises:
            ToolInvocationError: If no base URL is configured, a path parameter
                is missing, or the request cannot be completed (network/timeout).
        """
        if self._client is None:
            raise ToolInvocationError("HTTP client is not initialised")

        base_url = self._config.base_url or self._spec.base_url
        if not base_url:
            raise ToolInvocationError(
                "No base URL available. Set OPENAPI_MCP_BASE_URL or pass --base-url."
            )

        path_params, query_params, header_params, body = self._split_arguments(operation, arguments)
        url = _join_url(base_url, _substitute_path(operation.path, path_params))
        request_kwargs = _body_kwargs(operation, body)

        try:
            response = await self._client.request(
                operation.method,
                url,
                params={**self._auth_query, **query_params},
                headers={**self._auth_headers, **header_params},
                **request_kwargs,
            )
        except httpx.TimeoutException as exc:
            raise ToolInvocationError(
                f"Request to {url} timed out after {self._config.timeout}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise ToolInvocationError(f"HTTP request to {url} failed: {exc}") from exc

        return _format_response(response)

    def _split_arguments(
        self, operation: Operation, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, str], Any]:
        path_params: dict[str, Any] = {}
        query_params: dict[str, Any] = {}
        header_params: dict[str, str] = {}
        body = arguments.get("body")
        by_name = {param.name: param for param in operation.parameters}
        for key, value in arguments.items():
            if key == "body" or value is None:
                continue
            param = by_name.get(key)
            if param is None:
                continue  # unknown args are dropped (schema validation runs upstream)
            if param.location == "path":
                path_params[key] = value
            elif param.location == "query":
                query_params[key] = value
            elif param.location == "header":
                header_params[key] = str(value)
        return path_params, query_params, header_params, body


def _build_auth(spec: ParsedSpec, config: Config) -> tuple[dict[str, str], dict[str, str]]:
    """Derive auth headers/query params from config + the spec's security schemes.

    A bearer token takes priority over basic credentials. An API key is placed in
    the header or query named by the first ``apiKey`` scheme in the spec (falling
    back to ``X-API-Key`` in the header). ``extra_headers`` is merged last so it
    always wins.
    """
    headers: dict[str, str] = {}
    query: dict[str, str] = {}

    if config.bearer_token:
        headers["Authorization"] = f"Bearer {config.bearer_token}"
    elif config.has_basic_auth:
        raw = f"{config.basic_username or ''}:{config.basic_password or ''}"
        encoded = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"

    if config.api_key:
        name, location = _DEFAULT_API_KEY_HEADER, "header"
        api_key_schemes = [s for s in spec.security_schemes.values() if s.type == "apiKey"]
        if api_key_schemes:
            name = api_key_schemes[0].name or name
            location = api_key_schemes[0].location or "header"
        if location == "query":
            query[name] = config.api_key
        else:
            headers[name] = config.api_key

    headers.update(config.extra_headers)
    return headers, query


def _body_kwargs(operation: Operation, body: Any) -> dict[str, Any]:
    if body is None:
        return {}
    content_type = operation.request_body_content_type
    if content_type.startswith("application/json"):
        return {"json": body}
    if "x-www-form-urlencoded" in content_type or "form-data" in content_type:
        return {"data": body}
    if isinstance(body, (str, bytes)):
        return {"content": body}
    return {"content": json.dumps(body)}


def _substitute_path(path: str, path_params: dict[str, Any]) -> str:
    result = path
    for name, value in path_params.items():
        result = result.replace("{" + name + "}", quote(str(value), safe=""))
    missing = re.findall(r"{([^}]+)}", result)
    if missing:
        raise ToolInvocationError(f"Missing required path parameter(s): {', '.join(missing)}")
    return result


def _join_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def _format_response(response: httpx.Response) -> str:
    status_line = f"HTTP {response.status_code} {response.reason_phrase}".rstrip()
    headers = [
        f"{name}: {response.headers[name]}"
        for name in _INTERESTING_HEADERS
        if name in response.headers
    ]

    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        try:
            body_text = json.dumps(response.json(), indent=2, ensure_ascii=False)
        except ValueError:
            body_text = response.text
    else:
        body_text = response.text

    if len(body_text) > _MAX_BODY_CHARS:
        total = len(body_text)
        body_text = body_text[:_MAX_BODY_CHARS] + f"\n... [truncated, {total} chars total]"

    sections = [status_line]
    if headers:
        sections.append("\n".join(headers))
    sections.append(body_text if body_text else "(empty response body)")
    return "\n\n".join(sections)
