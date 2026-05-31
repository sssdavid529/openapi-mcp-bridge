"""Tests for spec normalisation and MCP tool generation."""

from __future__ import annotations

from openapi_mcp_bridge.spec_loader import resolve_refs
from openapi_mcp_bridge.tool_generator import generate_tool_defs, parse_spec


def _tools_by_name(document: dict) -> dict:
    spec = parse_spec(resolve_refs(document))
    return {td.name: td for td in generate_tool_defs(spec)}


def test_one_tool_per_operation(petstore_doc: dict) -> None:
    tools = _tools_by_name(petstore_doc)
    assert set(tools) == {"listPets", "createPet", "getPet"}


def test_base_url_from_servers(petstore_doc: dict) -> None:
    spec = parse_spec(resolve_refs(petstore_doc))
    assert spec.base_url == "https://api.petstore.example/v1"
    assert spec.title == "Petstore"


def test_path_param_schema_and_required(petstore_doc: dict) -> None:
    get_pet = _tools_by_name(petstore_doc)["getPet"]
    assert get_pet.input_schema["properties"]["petId"] == {"type": "string"}
    assert get_pet.input_schema["required"] == ["petId"]
    assert get_pet.operation.method == "GET"
    assert get_pet.operation.path == "/pets/{petId}"


def test_optional_query_param_not_required(petstore_doc: dict) -> None:
    list_pets = _tools_by_name(petstore_doc)["listPets"]
    assert list_pets.input_schema["properties"]["limit"]["type"] == "integer"
    assert list_pets.input_schema["properties"]["limit"]["description"] == "Max items"
    assert "required" not in list_pets.input_schema


def test_request_body_becomes_body_property(petstore_doc: dict) -> None:
    create_pet = _tools_by_name(petstore_doc)["createPet"]
    body = create_pet.input_schema["properties"]["body"]
    assert body["type"] == "object"
    assert set(body["properties"]) == {"name", "tag"}
    assert create_pet.input_schema["required"] == ["body"]


def test_security_scheme_parsed(petstore_doc: dict) -> None:
    spec = parse_spec(resolve_refs(petstore_doc))
    scheme = spec.security_schemes["ApiKeyAuth"]
    assert scheme.type == "apiKey"
    assert scheme.name == "X-Api-Key"
    assert scheme.location == "header"


def test_tool_name_generated_from_method_and_path() -> None:
    document = {
        "openapi": "3.0.0",
        "info": {"title": "NoIds", "version": "1"},
        "servers": [{"url": "https://x.example"}],
        "paths": {"/foo/bar": {"get": {"summary": "no operationId here"}}},
    }
    tools = _tools_by_name(document)
    assert "get_foo_bar" in tools


def test_tool_names_are_deduplicated() -> None:
    document = {
        "openapi": "3.0.0",
        "info": {"title": "Dupes", "version": "1"},
        "servers": [{"url": "https://x.example"}],
        "paths": {
            "/a": {"get": {"operationId": "dup"}},
            "/b": {"get": {"operationId": "dup"}},
        },
    }
    names = list(_tools_by_name(document))
    assert names == ["dup", "dup_2"]


def test_long_tool_name_is_truncated() -> None:
    long_id = "x" * 200
    document = {
        "openapi": "3.0.0",
        "info": {"title": "Long", "version": "1"},
        "servers": [{"url": "https://x.example"}],
        "paths": {"/a": {"get": {"operationId": long_id}}},
    }
    (name,) = _tools_by_name(document)
    assert len(name) <= 64


# ------------------------------------------------------------------ #
# Tag filtering
# ------------------------------------------------------------------ #
_TAGGED_DOC: dict = {
    "openapi": "3.0.0",
    "info": {"title": "Tagged", "version": "1"},
    "servers": [{"url": "https://x.example"}],
    "paths": {
        "/a": {"get": {"operationId": "op_a", "tags": ["public"]}},
        "/b": {"get": {"operationId": "op_b", "tags": ["admin"]}},
        "/c": {"get": {"operationId": "op_c", "tags": ["public", "beta"]}},
        "/d": {"get": {"operationId": "op_d"}},
    },
}


def _tagged_tool_names(**kwargs):
    spec = parse_spec(resolve_refs(_TAGGED_DOC))
    return {td.name for td in generate_tool_defs(spec, **kwargs)}


def test_include_tags_keeps_only_matching() -> None:
    names = _tagged_tool_names(include_tags=["public"])
    assert names == {"op_a", "op_c"}  # op_d has no tags → excluded


def test_include_tags_multiple_acts_as_or() -> None:
    names = _tagged_tool_names(include_tags=["public", "admin"])
    assert names == {"op_a", "op_b", "op_c"}


def test_exclude_tags_removes_matching() -> None:
    names = _tagged_tool_names(exclude_tags=["admin"])
    assert names == {"op_a", "op_c", "op_d"}


def test_include_and_exclude_compose() -> None:
    # include public → {op_a, op_c}; exclude beta → remove op_c
    names = _tagged_tool_names(include_tags=["public"], exclude_tags=["beta"])
    assert names == {"op_a"}


def test_empty_include_behaves_like_none() -> None:
    names1 = _tagged_tool_names(include_tags=[])
    names2 = _tagged_tool_names(include_tags=None)
    assert names1 == names2 == {"op_a", "op_b", "op_c", "op_d"}


def test_openapi3_and_swagger2_normalise_identically(
    petstore_doc: dict, swagger2_doc: dict
) -> None:
    v3 = parse_spec(resolve_refs(petstore_doc), source_ref="https://api.petstore.example/o.json")
    v2 = parse_spec(resolve_refs(swagger2_doc), source_ref="https://api.petstore.example/o.json")

    assert v3.base_url == v2.base_url == "https://api.petstore.example/v1"

    v3_tools = {td.name: td for td in generate_tool_defs(v3)}
    v2_tools = {td.name: td for td in generate_tool_defs(v2)}
    assert set(v3_tools) == set(v2_tools)

    for name in v3_tools:
        assert v3_tools[name].input_schema == v2_tools[name].input_schema, name
        assert v3_tools[name].operation.method == v2_tools[name].operation.method
        assert v3_tools[name].operation.path == v2_tools[name].operation.path
