"""Load and pre-process OpenAPI/Swagger documents.

Responsibilities:

* fetch a document from a URL or read it from a local file,
* parse it as JSON or YAML,
* detect whether it is OpenAPI 3.x or Swagger 2.0, and
* resolve intra-document ``$ref`` pointers with cycle protection.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml

from .errors import SpecError


def load_spec(ref: str, *, timeout: float = 30.0) -> dict[str, Any]:
    """Load a specification from a URL or local path into a dict.

    Args:
        ref: An ``http(s)://`` URL or a filesystem path.
        timeout: Network timeout (seconds) used when ``ref`` is a URL.

    Raises:
        SpecError: If the source cannot be read or parsed, or if the top-level
            value is not a JSON/YAML object.
    """
    raw = _read_source(ref, timeout=timeout)
    document = _parse_document(raw, hint=ref)
    if not isinstance(document, dict):
        raise SpecError("Top-level OpenAPI document must be a mapping/object")
    return document


def detect_version(document: dict[str, Any]) -> str:
    """Return ``"openapi-3"`` or ``"swagger-2"`` for a parsed document.

    Raises:
        SpecError: If the version field is missing or unsupported.
    """
    openapi = document.get("openapi")
    if isinstance(openapi, str) and openapi.startswith("3"):
        return "openapi-3"
    swagger = document.get("swagger")
    if isinstance(swagger, str) and swagger.startswith("2"):
        return "swagger-2"
    raise SpecError(
        "Unsupported or missing spec version: expected 'openapi: 3.x' or 'swagger: 2.0'"
    )


def resolve_refs(document: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy with all local ``$ref`` pointers resolved.

    Local references (``#/...``) are inlined. External references (anything not
    starting with ``#/``) are preserved verbatim because they cannot be resolved
    from the document alone. Reference cycles are broken by substituting an empty
    object schema, guaranteeing the result is finite and JSON-serialisable.
    """
    root = document

    def _resolve(node: Any, seen: frozenset[str]) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/"):
                if ref in seen:
                    return {"type": "object"}
                target = _lookup_pointer(root, ref)
                return _resolve(target, seen | {ref})
            return {key: _resolve(value, seen) for key, value in node.items()}
        if isinstance(node, list):
            return [_resolve(item, seen) for item in node]
        return node

    result: Any = _resolve(root, frozenset())
    return result


def _lookup_pointer(root: dict[str, Any], ref: str) -> Any:
    """Resolve a JSON pointer of the form ``#/a/b/c`` against ``root``."""
    parts = ref[2:].split("/") if len(ref) > 2 else []
    node: Any = root
    for part in parts:
        token = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and token in node:
            node = node[token]
        else:
            raise SpecError(f"Cannot resolve $ref {ref!r}: missing segment {token!r}")
    return node


def _is_url(ref: str) -> bool:
    return urlparse(ref).scheme in {"http", "https"}


def _read_source(ref: str, *, timeout: float) -> str:
    if _is_url(ref):
        try:
            response = httpx.get(ref, timeout=timeout, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SpecError(f"Failed to fetch spec from {ref!r}: {exc}") from exc
        return response.text
    path = Path(ref).expanduser()
    if not path.is_file():
        raise SpecError(f"Spec file not found: {ref!r}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SpecError(f"Failed to read spec file {ref!r}: {exc}") from exc


def _parse_document(raw: str, *, hint: str) -> Any:
    # JSON parses faster and gives clearer errors; YAML is a superset fallback.
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise SpecError(f"Could not parse spec {hint!r} as JSON or YAML: {exc}") from exc
