"""Tests for loading, parsing, version detection and $ref resolution."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from openapi_mcp_bridge.errors import SpecError
from openapi_mcp_bridge.spec_loader import detect_version, load_spec, resolve_refs


def test_load_spec_from_json_file(fixtures_dir: Path) -> None:
    document = load_spec(str(fixtures_dir / "petstore_min.json"))
    assert document["openapi"].startswith("3")
    assert document["info"]["title"] == "Petstore"


def test_load_spec_from_yaml_file(tmp_path: Path) -> None:
    yaml_text = "openapi: 3.0.0\ninfo:\n  title: YamlApi\n  version: '1.0'\npaths: {}\n"
    path = tmp_path / "spec.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    document = load_spec(str(path))
    assert document["info"]["title"] == "YamlApi"


def test_load_spec_from_url(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"openapi": "3.0.0", "info": {"title": "Remote", "version": "1"}, "paths": {}}

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr("openapi_mcp_bridge.spec_loader.httpx.get", fake_get)
    document = load_spec("https://example.com/openapi.json")
    assert document["info"]["title"] == "Remote"


def test_load_spec_missing_file_raises() -> None:
    with pytest.raises(SpecError, match="not found"):
        load_spec("does-not-exist-12345.json")


def test_load_spec_non_object_raises(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(SpecError, match="mapping/object"):
        load_spec(str(path))


def test_load_spec_unparseable_raises(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not valid: ::: json", encoding="utf-8")
    with pytest.raises(SpecError):
        load_spec(str(path))


def test_detect_version() -> None:
    assert detect_version({"openapi": "3.0.3"}) == "openapi-3"
    assert detect_version({"swagger": "2.0"}) == "swagger-2"


def test_detect_version_unsupported_raises() -> None:
    with pytest.raises(SpecError, match="Unsupported or missing"):
        detect_version({"info": {}})


def test_resolve_refs_inlines_local_ref(petstore_doc: dict) -> None:
    resolved = resolve_refs(petstore_doc)
    body_schema = resolved["paths"]["/pets"]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]
    assert "$ref" not in body_schema
    assert body_schema["type"] == "object"
    assert set(body_schema["properties"]) == {"name", "tag"}
    # The original document must not be mutated.
    original = petstore_doc["paths"]["/pets"]["post"]["requestBody"]["content"]["application/json"][
        "schema"
    ]
    assert original == {"$ref": "#/components/schemas/NewPet"}


def test_resolve_refs_breaks_cycles() -> None:
    document = {
        "openapi": "3.0.0",
        "components": {
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": {"next": {"$ref": "#/components/schemas/Node"}},
                }
            }
        },
    }
    resolved = resolve_refs(document)  # must terminate, not recurse forever
    node = resolved["components"]["schemas"]["Node"]
    assert node["type"] == "object"
    assert node["properties"]["next"]["properties"]["next"] == {"type": "object"}


def test_resolve_refs_leaves_external_refs() -> None:
    document = {"a": {"$ref": "external.json#/Thing"}}
    assert resolve_refs(document) == document


def test_resolve_refs_unknown_pointer_raises() -> None:
    with pytest.raises(SpecError, match="Cannot resolve"):
        resolve_refs({"a": {"$ref": "#/nope/missing"}})


def test_round_trips_through_json(fixtures_dir: Path) -> None:
    resolved = resolve_refs(load_spec(str(fixtures_dir / "petstore_min.json")))
    # A resolved spec must remain JSON-serialisable (no leftover cycles/objects).
    json.dumps(resolved)
