"""KLASS access and the joins it exists for -- stubbed, no network."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import requests
import responses

from src import Classification, Klass, KlassError, attach_names, attach_parent

FIXTURES = Path(__file__).parent / "fixtures" / "klass"
BASE = "https://data.ssb.no/api/klass/v1"


def stub(path: str, fixture: str) -> None:
    responses.add(
        responses.GET,
        f"{BASE}{path}",
        json=json.loads((FIXTURES / fixture).read_text(encoding="utf-8")),
        status=200,
    )


@pytest.fixture
def klass() -> Klass:
    # A plain Session rather than the default CachedSession, so nothing leaks
    # between tests.
    return Klass(session=requests.Session())


@pytest.fixture
def pop() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Region": ["Oslo - Oslove", "Bergen", "Hele landet"],
            "Region_code": ["0301", "4601", "0"],
            "value": [724290, 291940, 5594340],
        }
    )


class TestCodes:
    @responses.activate
    def test_snapshot_uses_codes_at_a_date(self, klass):
        stub("/classifications/131/codesAt", "131_codesAt_2025.json")
        frame = klass.codes(Classification.KOMMUNE, date="2025-01-01")
        assert len(frame) == 358
        assert list(frame.columns)[:4] == ["code", "parentCode", "level", "name"]
        assert responses.calls[0].request.params["date"] == "2025-01-01"

    @responses.activate
    def test_a_bare_year_means_january_first(self, klass):
        stub("/classifications/104/codesAt", "104_codesAt_2025.json")
        klass.codes(Classification.FYLKE, date=2025)
        assert responses.calls[0].request.params["date"] == "2025-01-01"

    @responses.activate
    def test_a_range_uses_the_codes_endpoint_which_requires_from(self, klass):
        # /codes without `from` is a hard 400 from KLASS.
        stub("/classifications/104/codes", "104_codesAt_2025.json")
        klass.codes(Classification.FYLKE, from_=2024, to=2025)
        assert responses.calls[0].request.params["from"] == "2024-01-01"

    @responses.activate
    def test_mapping_is_code_to_name(self, klass):
        stub("/classifications/104/codesAt", "104_codesAt_2025.json")
        assert klass.mapping(Classification.FYLKE, date=2025)["03"] == "Oslo"

    @responses.activate
    def test_a_cached_frame_is_never_handed_out_by_reference(self, klass):
        stub("/classifications/104/codesAt", "104_codesAt_2025.json")
        first = klass.codes(Classification.FYLKE, date=2025)
        first.loc[0, "name"] = "MUTATED"
        second = klass.codes(Classification.FYLKE, date=2025)
        assert second.loc[0, "name"] != "MUTATED"
        assert len(responses.calls) == 1  # and it did come from the cache

    @responses.activate
    def test_a_missing_classification_is_reported_clearly(self, klass):
        responses.add(
            responses.GET,
            f"{BASE}/classifications/9999/codesAt",
            json={"detail": "no such classification"},
            status=404,
        )
        with pytest.raises(KlassError, match="404"):
            klass.codes(9999)


class TestCorrespondence:
    @responses.activate
    def test_kommune_maps_onto_fylke(self, klass):
        stub("/classifications/131/correspondsAt", "131_correspondsAt_104_2025.json")
        frame = klass.correspondence(Classification.KOMMUNE, Classification.FYLKE, date=2025)
        assert frame.loc[frame["sourceCode"] == "0301", "targetCode"].item() == "03"


class TestAttachNames:
    @responses.activate
    def test_adds_the_name_beside_the_code(self, klass, pop):
        stub("/classifications/131/codesAt", "131_codesAt_2025.json")
        with pytest.warns(UserWarning, match="no match"):
            out = attach_names(pop, "Region_code", date=2025, name_column="kommune", klass=klass)
        assert list(out.columns) == ["Region", "Region_code", "kommune", "value"]
        assert out.loc[0, "kommune"] == "Oslo"

    @responses.activate
    def test_aggregate_codes_are_reported_not_swallowed(self, klass, pop):
        # "0" is Hele landet: SSB has it, KLASS does not. A silent NaN here is
        # how a choropleth quietly loses a region.
        stub("/classifications/131/codesAt", "131_codesAt_2025.json")
        with pytest.warns(UserWarning, match="'0'"):
            out = attach_names(pop, "Region_code", date=2025, klass=klass)
        assert pd.isna(out.loc[2, "Region_code_navn"])

    @responses.activate
    def test_on_missing_raise(self, klass, pop):
        stub("/classifications/131/codesAt", "131_codesAt_2025.json")
        with pytest.raises(KlassError, match="no match"):
            attach_names(pop, "Region_code", date=2025, on_missing="raise", klass=klass)

    @responses.activate
    def test_on_missing_ignore_is_silent(self, klass, pop, recwarn):
        stub("/classifications/131/codesAt", "131_codesAt_2025.json")
        attach_names(pop, "Region_code", date=2025, on_missing="ignore", klass=klass)
        assert not [w for w in recwarn if "no match" in str(w.message)]

    def test_a_bad_column_name_fails_immediately(self, klass, pop):
        with pytest.raises(KeyError, match="nope"):
            attach_names(pop, "nope", klass=klass)

    @responses.activate
    def test_the_input_frame_is_left_alone(self, klass, pop):
        stub("/classifications/131/codesAt", "131_codesAt_2025.json")
        before = list(pop.columns)
        attach_names(pop, "Region_code", date=2025, on_missing="ignore", klass=klass)
        assert list(pop.columns) == before


class TestAttachParent:
    @responses.activate
    def test_rolls_municipalities_up_to_counties(self, klass, pop):
        stub("/classifications/131/correspondsAt", "131_correspondsAt_104_2025.json")
        with pytest.warns(UserWarning, match="no match"):
            out = attach_parent(pop, "Region_code", date=2025, klass=klass)
        assert list(out.columns) == ["Region", "Region_code", "fylke_code", "fylke", "value"]
        assert out.loc[0, "fylke_code"] == "03"
        assert out.loc[1, "fylke"] == "Vestland"
