"""Turn a parsed spec into normalised operations and MCP tool definitions.

Two responsibilities:

* :func:`parse_spec` normalises an OpenAPI 3.x **or** Swagger 2.0 document into a
  version-agnostic :class:`~openapi_mcp_bridge.models.ParsedSpec`.
* :func:`generate_tool_defs` derives a unique, MCP-safe tool name and a JSON
  Schema ``inputSchema`` for every operation.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from .models import Operation, Parameter, ParsedSpec, SecurityScheme, ToolDef
from .spec_loader import detect_version

_HTTP_METHODS = ("get", "post", "put", "delete", "patch", "options", "head", "trace")
_MAX_NAME_LENGTH = 64
_MAX_DESCRIPTION_LENGTH = 1024
_INVALID_NAME_CHARS = re.compile(r"[^a-zA-Z0-9_-]")
_PATH_PLACEHOLDER = re.compile(r"{([^}]+)}")
_V2_NON_SCHEMA_KEYS = frozenset(
    {"name", "in", "required", "description", "collectionFormat", "allowEmptyValue", "$ref"}
)


# --------------------------------------------------------------------------- #
# Spec parsing
# --------------------------------------------------------------------------- #
def parse_spec(
    document: dict[str, Any],
    *,
    source_ref: str | None = None,
    base_url_override: str | None = None,
) -> ParsedSpec:
    """Normalise a (ref-resolved) document into a :class:`ParsedSpec`.

    Args:
        document: A parsed spec, ideally already passed through
            :func:`~openapi_mcp_bridge.spec_loader.resolve_refs`.
        source_ref: The original URL/path; used to absolutise relative server
            URLs and to derive an origin when the spec omits the host.
        base_url_override: When set, wins over any server URL in the document.
    """
    version = detect_version(document)
    if version == "openapi-3":
        return _parse_v3(document, source_ref, base_url_override)
    return _parse_v2(document, source_ref, base_url_override)


def _parse_v3(
    document: dict[str, Any], source_ref: str | None, base_url_override: str | None
) -> ParsedSpec:
    info = document.get("info") or {}
    base_url = base_url_override or _base_url_v3(document, source_ref)
    operations: list[Operation] = []

    for path, item in _iter_path_items(document):
        shared = _params_v3(item.get("parameters"))
        for method in _HTTP_METHODS:
            op_obj = item.get(method)
            if not isinstance(op_obj, dict):
                continue
            params = _merge_params(shared, _params_v3(op_obj.get("parameters")))
            body_schema, body_required, body_ct = _request_body_v3(op_obj.get("requestBody"))
            operations.append(
                Operation(
                    operation_id=op_obj.get("operationId") or "",
                    method=method.upper(),
                    path=path,
                    parameters=tuple(params),
                    request_body_schema=body_schema,
                    request_body_required=body_required,
                    request_body_content_type=body_ct,
                    summary=op_obj.get("summary"),
                    description=op_obj.get("description"),
                    tags=tuple(op_obj.get("tags") or ()),
                )
            )

    return ParsedSpec(
        title=info.get("title"),
        base_url=base_url,
        operations=operations,
        security_schemes=_security_v3(document),
        spec_version="openapi-3",
    )


def _parse_v2(
    document: dict[str, Any], source_ref: str | None, base_url_override: str | None
) -> ParsedSpec:
    info = document.get("info") or {}
    base_url = base_url_override or _base_url_v2(document, source_ref)
    operations: list[Operation] = []

    for path, item in _iter_path_items(document):
        shared_params, _, _, shared_form, _ = _params_v2(item.get("parameters"))
        for method in _HTTP_METHODS:
            op_obj = item.get(method)
            if not isinstance(op_obj, dict):
                continue
            params, body_schema, body_required, form_props, form_required = _params_v2(
                op_obj.get("parameters")
            )
            merged = _merge_params(shared_params, params)
            content_type = "application/json"
            combined_form = {**shared_form, **form_props}
            if body_schema is None and combined_form:
                body_schema = {"type": "object", "properties": combined_form}
                if form_required:
                    body_schema["required"] = form_required
                body_required = bool(form_required)
                content_type = "application/x-www-form-urlencoded"
            operations.append(
                Operation(
                    operation_id=op_obj.get("operationId") or "",
                    method=method.upper(),
                    path=path,
                    parameters=tuple(merged),
                    request_body_schema=body_schema,
                    request_body_required=body_required,
                    request_body_content_type=content_type,
                    summary=op_obj.get("summary"),
                    description=op_obj.get("description"),
                    tags=tuple(op_obj.get("tags") or ()),
                )
            )

    return ParsedSpec(
        title=info.get("title"),
        base_url=base_url,
        operations=operations,
        security_schemes=_security_v2(document),
        spec_version="swagger-2",
    )


def _iter_path_items(document: dict[str, Any]):
    paths = document.get("paths")
    if not isinstance(paths, dict):
        return
    for path, item in paths.items():
        if isinstance(item, dict):
            yield path, item


def _params_v3(raw: Any) -> list[Parameter]:
    result: list[Parameter] = []
    for entry in raw or ():
        if not isinstance(entry, dict) or "$ref" in entry:
            continue
        location = entry.get("in")
        name = entry.get("name")
        if location not in ("path", "query", "header", "cookie") or not name:
            continue
        raw_schema = entry.get("schema")
        result.append(
            Parameter(
                name=name,
                location=location,
                required=bool(entry.get("required", location == "path")),
                schema=raw_schema if isinstance(raw_schema, dict) else {},
                description=entry.get("description"),
            )
        )
    return result


def _params_v2(
    raw: Any,
) -> tuple[list[Parameter], dict[str, Any] | None, bool, dict[str, Any], list[str]]:
    """Return (params, body_schema, body_required, form_props, form_required)."""
    params: list[Parameter] = []
    body_schema: dict[str, Any] | None = None
    body_required = False
    form_props: dict[str, Any] = {}
    form_required: list[str] = []
    for entry in raw or ():
        if not isinstance(entry, dict):
            continue
        location = entry.get("in")
        name = entry.get("name") or ""
        if location == "body":
            schema = entry.get("schema")
            if isinstance(schema, dict):
                body_schema = schema
                body_required = bool(entry.get("required", False))
        elif location == "formData" and name:
            form_props[name] = _schema_from_v2_param(entry)
            if entry.get("required"):
                form_required.append(name)
        elif location in ("path", "query", "header") and name:
            params.append(
                Parameter(
                    name=name,
                    location=location,
                    required=bool(entry.get("required", location == "path")),
                    schema=_schema_from_v2_param(entry),
                    description=entry.get("description"),
                )
            )
    return params, body_schema, body_required, form_props, form_required


def _schema_from_v2_param(entry: dict[str, Any]) -> dict[str, Any]:
    schema = {k: v for k, v in entry.items() if k not in _V2_NON_SCHEMA_KEYS}
    return schema or {"type": "string"}


def _merge_params(shared: list[Parameter], specific: list[Parameter]) -> list[Parameter]:
    """Operation-level parameters override path-level ones by (name, location)."""
    merged: dict[tuple[str, str], Parameter] = {(p.name, p.location): p for p in shared}
    for param in specific:
        merged[(param.name, param.location)] = param
    return list(merged.values())


def _request_body_v3(request_body: Any) -> tuple[dict[str, Any] | None, bool, str]:
    if not isinstance(request_body, dict):
        return None, False, "application/json"
    content = request_body.get("content")
    if not isinstance(content, dict) or not content:
        return None, False, "application/json"
    content_type = "application/json" if "application/json" in content else next(iter(content))
    media = content.get(content_type) or {}
    schema = media.get("schema") if isinstance(media, dict) else None
    return (
        schema if isinstance(schema, dict) else None,
        bool(request_body.get("required", False)),
        content_type,
    )


# --------------------------------------------------------------------------- #
# Base URL resolution
# --------------------------------------------------------------------------- #
def _base_url_v3(document: dict[str, Any], source_ref: str | None) -> str | None:
    servers = document.get("servers")
    if isinstance(servers, list) and servers and isinstance(servers[0], dict):
        url = servers[0].get("url") or ""
        for var, definition in (servers[0].get("variables") or {}).items():
            if isinstance(definition, dict) and "default" in definition:
                url = url.replace("{" + var + "}", str(definition["default"]))
        return _absolutize(url, source_ref) or _origin_of(source_ref)
    return _origin_of(source_ref)


def _base_url_v2(document: dict[str, Any], source_ref: str | None) -> str | None:
    schemes = document.get("schemes") or []
    host = document.get("host")
    base_path = document.get("basePath") or ""
    scheme = "https" if "https" in schemes else (schemes[0] if schemes else None)
    if host:
        scheme = scheme or _scheme_of(source_ref) or "https"
        return f"{scheme}://{host}{base_path}"
    origin = _origin_of(source_ref)
    return origin.rstrip("/") + base_path if origin else None


def _scheme_of(ref: str | None) -> str | None:
    if not ref:
        return None
    parsed = urlparse(ref)
    return parsed.scheme if parsed.scheme in ("http", "https") else None


def _origin_of(ref: str | None) -> str | None:
    if not ref:
        return None
    parsed = urlparse(ref)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return None


def _absolutize(url: str, ref: str | None) -> str:
    if not url or urlparse(url).scheme:
        return url
    if ref and _origin_of(ref):
        return urljoin(ref, url)
    return url


# --------------------------------------------------------------------------- #
# Security schemes
# --------------------------------------------------------------------------- #
def _security_v3(document: dict[str, Any]) -> dict[str, SecurityScheme]:
    defs = (document.get("components") or {}).get("securitySchemes") or {}
    result: dict[str, SecurityScheme] = {}
    for name, scheme in defs.items():
        if not isinstance(scheme, dict):
            continue
        kind = scheme.get("type")
        if kind == "http":
            result[name] = SecurityScheme(
                type="http", scheme=(scheme.get("scheme") or "").lower() or None
            )
        elif kind == "apiKey":
            result[name] = SecurityScheme(
                type="apiKey", name=scheme.get("name"), location=scheme.get("in")
            )
        elif kind in ("oauth2", "openIdConnect"):
            result[name] = SecurityScheme(type="oauth2")
    return result


def _security_v2(document: dict[str, Any]) -> dict[str, SecurityScheme]:
    defs = document.get("securityDefinitions") or {}
    result: dict[str, SecurityScheme] = {}
    for name, scheme in defs.items():
        if not isinstance(scheme, dict):
            continue
        kind = scheme.get("type")
        if kind == "basic":
            result[name] = SecurityScheme(type="http", scheme="basic")
        elif kind == "apiKey":
            result[name] = SecurityScheme(
                type="apiKey", name=scheme.get("name"), location=scheme.get("in")
            )
        elif kind == "oauth2":
            result[name] = SecurityScheme(type="oauth2")
    return result


# --------------------------------------------------------------------------- #
# Tool generation
# --------------------------------------------------------------------------- #
def generate_tool_defs(
    spec: ParsedSpec,
    *,
    include_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
) -> list[ToolDef]:
    """Build one :class:`ToolDef` per operation, with unique MCP-safe names.

    Args:
        spec: Normalised specification.
        include_tags: When non-empty, only operations that have at least one of
            these tags are included. Operations with no tags are excluded.
        exclude_tags: When non-empty, operations that have any of these tags are
            removed. Applied after ``include_tags``.
    """
    used: set[str] = set()
    defs: list[ToolDef] = []

    operations = spec.operations
    if include_tags:
        tag_set = frozenset(include_tags)
        operations = [op for op in operations if tag_set.intersection(op.tags)]
    if exclude_tags:
        skip_set = frozenset(exclude_tags)
        operations = [op for op in operations if not skip_set.intersection(op.tags)]

    for operation in operations:
        name = _tool_name(operation, used)
        defs.append(
            ToolDef(
                name=name,
                description=_tool_description(operation),
                input_schema=_build_input_schema(operation),
                operation=operation,
            )
        )
    return defs


def _tool_name(operation: Operation, used: set[str]) -> str:
    base = operation.operation_id or f"{operation.method.lower()}_{operation.path}"
    name = _INVALID_NAME_CHARS.sub("_", base)
    name = re.sub(r"_{2,}", "_", name).strip("_") or "operation"
    if len(name) > _MAX_NAME_LENGTH:
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
        name = f"{name[: _MAX_NAME_LENGTH - 9]}_{digest}"
    candidate, counter = name, 2
    while candidate in used:
        suffix = f"_{counter}"
        candidate = name[: _MAX_NAME_LENGTH - len(suffix)] + suffix
        counter += 1
    used.add(candidate)
    return candidate


def _tool_description(operation: Operation) -> str:
    header = f"{operation.method} {operation.path}"
    parts = [header]
    if operation.summary:
        parts.append(operation.summary)
    if operation.description and operation.description != operation.summary:
        parts.append(operation.description)
    return "\n\n".join(parts)[:_MAX_DESCRIPTION_LENGTH]


def _build_input_schema(operation: Operation) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param in operation.parameters:
        if param.location == "cookie":
            continue  # cookie params are not exposed as tool inputs
        schema = dict(param.schema) if param.schema else {"type": "string"}
        if param.description and "description" not in schema:
            schema["description"] = param.description
        properties[param.name] = schema
        if param.required:
            required.append(param.name)

    if operation.request_body_schema is not None:
        body_schema = dict(operation.request_body_schema)
        body_schema.setdefault("description", "Request body payload.")
        properties["body"] = body_schema
        if operation.request_body_required:
            required.append("body")

    result_schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        result_schema["required"] = required
    return result_schema
