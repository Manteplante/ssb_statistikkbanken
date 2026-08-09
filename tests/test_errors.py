"""Translating pxwebpy's stringly-typed failures into something actionable."""

from __future__ import annotations

import pytest
from requests.exceptions import HTTPError

from src import (
    BadSelectionError,
    RateLimitedError,
    SsbError,
    SsbHTTPError,
    TableNotFoundError,
)
from src.errors import parse_pxweb_message, suggest, wrap_pxweb_errors


def pxweb_message(status: int, reason: str, **body: object) -> str:
    """Reproduce pxwebpy's exact error string (see pxweb/_internal/client.py)."""
    fields = {"type": None, "title": None, "status": status, "detail": None, "instance": None}
    fields.update(body)
    return (
        f"Error {status}: {reason}\n"
        f"Type: {fields['type']}\nTitle: {fields['title']}\nStatus: {fields['status']}\n"
        f"Detail: {fields['detail']}\nInstance: {fields['instance']}"
    )


class TestParsing:
    def test_reads_status_and_detail(self):
        message = pxweb_message(404, "Not Found", title="Not Found", detail="Non-existent table")
        assert parse_pxweb_message(message) == (404, "Non-existent table")

    def test_falls_back_to_title_when_detail_is_absent(self):
        message = pxweb_message(400, "Bad Request", title="Missing selection")
        assert parse_pxweb_message(message) == (400, "Missing selection")

    def test_unparseable_input_degrades_instead_of_crashing(self):
        assert parse_pxweb_message("something else entirely") == (None, None)


class TestWrapping:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [(404, TableNotFoundError), (429, RateLimitedError), (400, BadSelectionError)],
    )
    def test_status_picks_the_exception_type(self, status, expected):
        with pytest.raises(expected):
            with wrap_pxweb_errors(table_id="05810"):
                raise HTTPError(pxweb_message(status, "reason"))

    def test_unknown_status_still_becomes_an_ssb_error(self):
        with pytest.raises(SsbHTTPError) as excinfo:
            with wrap_pxweb_errors():
                raise HTTPError("Reached max amount of retries.")
        assert excinfo.value.status_code is None

    def test_message_points_at_the_next_step(self):
        with pytest.raises(TableNotFoundError, match=r"ssb\.search"):
            with wrap_pxweb_errors(table_id="99999"):
                raise HTTPError(pxweb_message(404, "Not Found"))

    def test_pxwebpy_value_errors_are_wrapped_too(self):
        with pytest.raises(SsbError, match="Invalid value for show"):
            with wrap_pxweb_errors():
                raise ValueError("Invalid value for show: nope.")


class TestSuggest:
    def test_finds_a_near_miss_case_insensitively(self):
        assert suggest("kjonne", ["Kjonn", "Alder", "Tid"]) == ["Kjonn"]

    def test_returns_nothing_for_a_wild_guess(self):
        assert suggest("xyzzy", ["Kjonn", "Alder"]) == []
