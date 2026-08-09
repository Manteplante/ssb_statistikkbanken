"""Shared fixtures. Nothing here touches the network."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# The repo root reaches sys.path via `pythonpath = ["."]` in pyproject.toml,
# which pytest applies before conftest is imported.


def load(*parts: str) -> Any:
    """Read a recorded API response. See ``tests/fixtures/refresh.py``."""
    return json.loads(FIXTURES.joinpath(*parts).read_text(encoding="utf-8"))


class FakePxApi:
    """A stand-in for :class:`pxweb.PxApi` backed by recorded responses.

    Data goes through pxwebpy's own ``unpack_table_data`` so the record shape
    stays authentic -- if pxwebpy changes how it flattens json-stat2, these
    tests notice.
    """

    def __init__(self, *, language: str = "no") -> None:
        self.language = language
        self.calls: list[dict[str, Any]] = []

    def get_table_metadata(self, table_id: str) -> Any:
        return load("pxweb", f"{table_id}_metadata.json")

    def get_table_data(
        self,
        table_id: str,
        value_codes: dict[str, list[str] | str] | None = None,
        code_list: dict[str, str] | None = None,
        show: Any = None,
    ) -> list[dict[str, Any]]:
        from pxweb._internal.functions import unpack_table_data

        self.calls.append(
            {
                "table_id": table_id,
                "value_codes": value_codes,
                "code_list": code_list,
                "show": show,
            }
        )
        return unpack_table_data(load("pxweb", f"{table_id}_data.json"), show=show)

    def search(
        self,
        query: str | None = None,
        past_days: int | None = None,
        include_discontinued: bool | None = None,
        page_size: int | None = None,
    ) -> Any:
        self.calls.append({"search": query, "page_size": page_size})
        return load("pxweb", "search_befolkning.json")

    def get_code_list(self, code_list_id: str) -> Any:  # pragma: no cover - unused so far
        raise NotImplementedError

    def get_paths(self, path_id: str | None = None) -> list[dict[str, str]]:  # pragma: no cover
        raise NotImplementedError

    def tables_on_path(self, path_id: str) -> list[dict[str, Any]]:  # pragma: no cover
        raise NotImplementedError

    @property
    def last_call(self) -> dict[str, Any]:
        return self.calls[-1]


@pytest.fixture
def fake_api() -> FakePxApi:
    return FakePxApi()


@pytest.fixture
def ssb(fake_api: FakePxApi):
    from src import SSB

    return SSB(api=fake_api)


@pytest.fixture
def info_05810():
    from src import parse_metadata

    return parse_metadata("05810", load("pxweb", "05810_metadata.json"))


@pytest.fixture
def info_07459():
    from src import parse_metadata

    return parse_metadata("07459", load("pxweb", "07459_metadata.json"))
