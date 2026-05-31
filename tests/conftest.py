"""Shared pytest fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def petstore_doc() -> dict[str, Any]:
    """A minimal OpenAPI 3.0 document."""
    return _load_fixture("petstore_min.json")


@pytest.fixture
def swagger2_doc() -> dict[str, Any]:
    """A minimal Swagger 2.0 document mirroring the OpenAPI 3 fixture."""
    return _load_fixture("swagger2_min.json")
