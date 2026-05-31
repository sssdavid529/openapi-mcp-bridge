"""Tests for CLI argument parsing and transport wiring."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from openapi_mcp_bridge.cli import build_arg_parser, main


class TestArgumentParsing:
    def test_defaults(self) -> None:
        parser = build_arg_parser()
        ns = parser.parse_args(["--spec", "openapi.json"])
        assert ns.spec == "openapi.json"
        assert ns.transport == "stdio"
        assert ns.host == "127.0.0.1"
        assert ns.port == 8000
        assert ns.include_tags is None
        assert ns.exclude_tags is None
        assert ns.list_tools is False

    def test_transport_sse(self) -> None:
        parser = build_arg_parser()
        ns = parser.parse_args(["--spec", "o.json", "--transport", "sse"])
        assert ns.transport == "sse"

    def test_transport_invalid_rejected(self) -> None:
        parser = build_arg_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--spec", "o.json", "--transport", "grpc"])

    def test_include_tags_single(self) -> None:
        parser = build_arg_parser()
        ns = parser.parse_args(["--spec", "o.json", "--include-tags", "pets"])
        assert ns.include_tags == ["pets"]

    def test_include_tags_multiple(self) -> None:
        parser = build_arg_parser()
        ns = parser.parse_args(["--spec", "o.json", "--include-tags", "pets", "store"])
        assert ns.include_tags == ["pets", "store"]

    def test_exclude_tags(self) -> None:
        parser = build_arg_parser()
        ns = parser.parse_args(["--spec", "o.json", "--exclude-tags", "admin"])
        assert ns.exclude_tags == ["admin"]

    def test_host_port(self) -> None:
        parser = build_arg_parser()
        ns = parser.parse_args(
            ["--spec", "o.json", "--transport", "sse", "--host", "0.0.0.0", "--port", "9090"]
        )
        assert ns.host == "0.0.0.0"
        assert ns.port == 9090

    def test_list_tools_shows_tags(self, capsys, tmp_path) -> None:
        import json

        doc = {
            "openapi": "3.0.0",
            "info": {"title": "T", "version": "1"},
            "servers": [{"url": "https://x.example"}],
            "paths": {
                "/a": {"get": {"operationId": "opA", "tags": ["public"]}},
                "/b": {"get": {"operationId": "opB", "tags": ["admin"]}},
            },
        }
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(doc))
        with patch("sys.stderr"):
            rc = main(["--spec", str(spec_path), "--list-tools"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "opA" in out and "public" in out
        assert "opB" in out and "admin" in out


class TestMainErrors:
    def test_missing_spec_exits(self, capsys) -> None:
        with pytest.raises(SystemExit):
            main([])
        # argparse prints usage to stderr on error
        assert capsys.readouterr().err

    def test_version_exits(self, capsys) -> None:
        with pytest.raises(SystemExit):
            main(["--version"])
        assert "openapi-mcp-bridge" in capsys.readouterr().out

    def test_bad_config_returns_2(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("OPENAPI_MCP_TIMEOUT", "not-a-number")
        spec = tmp_path / "s.json"
        spec.write_text('{"openapi":"3.0.0","info":{"title":"T","version":"1"},"paths":{}}')
        with patch("sys.stderr"):
            rc = main(["--spec", str(spec)])
        assert rc == 2

    def test_list_tools_with_tag_filter(self, capsys, tmp_path) -> None:
        import json

        doc = {
            "openapi": "3.0.0",
            "info": {"title": "T", "version": "1"},
            "servers": [{"url": "https://x.example"}],
            "paths": {
                "/a": {"get": {"operationId": "opA", "tags": ["public"]}},
                "/b": {"get": {"operationId": "opB", "tags": ["admin"]}},
            },
        }
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(doc))
        with patch("sys.stderr"):
            rc = main(["--spec", str(spec_path), "--list-tools", "--include-tags", "public"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "opA" in out
        assert "opB" not in out

    def test_lists_tools_then_no_base_url(self, capsys, tmp_path) -> None:
        """--list-tools should not require a base URL."""
        import json

        doc = {
            "openapi": "3.0.0",
            "info": {"title": "T", "version": "1"},
            "paths": {"/x": {"get": {"operationId": "opX"}}},
        }
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(doc))
        with patch("sys.stderr"):
            rc = main(["--spec", str(spec_path), "--list-tools"])
        assert rc == 0
        assert "opX" in capsys.readouterr().out


class TestTagFilteringEndToEnd:
    """Verify tag filtering works through the full main() path."""

    def test_include_tags_narrows_tools(self, capsys, tmp_path) -> None:
        import json

        doc = {
            "openapi": "3.0.0",
            "info": {"title": "TagTest", "version": "1"},
            "servers": [{"url": "https://api.example.com"}],
            "paths": {
                "/pets": {
                    "get": {"operationId": "listPets", "tags": ["pets"]},
                    "post": {"operationId": "createPet", "tags": ["pets", "admin"]},
                },
                "/users": {
                    "get": {"operationId": "listUsers", "tags": ["users"]},
                },
            },
        }
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(doc))
        with patch("sys.stderr"):
            rc = main(["--spec", str(spec_path), "--list-tools", "--include-tags", "pets"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "listPets" in out
        assert "createPet" in out
        assert "listUsers" not in out

    def test_exclude_tags_removes_tools(self, capsys, tmp_path) -> None:
        import json

        doc = {
            "openapi": "3.0.0",
            "info": {"title": "TagTest", "version": "1"},
            "servers": [{"url": "https://api.example.com"}],
            "paths": {
                "/pets": {"get": {"operationId": "listPets", "tags": ["pets"]}},
                "/admin/stats": {"get": {"operationId": "adminStats", "tags": ["admin"]}},
            },
        }
        spec_path = tmp_path / "spec.json"
        spec_path.write_text(json.dumps(doc))
        with patch("sys.stderr"):
            rc = main(["--spec", str(spec_path), "--list-tools", "--exclude-tags", "admin"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "listPets" in out
        assert "adminStats" not in out
