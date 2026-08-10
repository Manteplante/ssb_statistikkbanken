"""End-to-end through the client, against recorded responses -- no HTTP."""

from __future__ import annotations

import pytest
from pandas.api import types as ptypes

from ssb_statistikkbanken import SSB, TableInfo


def test_constructing_a_client_makes_no_calls():
    # PxApi() would cost two requests, so it must not be built eagerly.
    assert SSB()._apis == {}


class TestInspection:
    def test_describe_returns_parsed_metadata(self, ssb):
        assert isinstance(ssb.describe("05810"), TableInfo)

    def test_metadata_is_fetched_once_per_table(self, ssb, fake_api):
        ssb.describe("05810")
        ssb.describe("05810")
        ssb.variables("05810")
        assert sum(1 for call in fake_api.calls if "search" in call) == 0

    def test_variables_lists_every_dimension(self, ssb):
        frame = ssb.variables("05810")
        assert list(frame["variable"]) == ["Kjonn", "Alder", "ContentsCode", "Tid"]
        assert frame.loc[frame["variable"] == "Tid", "mandatory"].item()

    def test_values_are_not_truncated(self, ssb):
        assert len(ssb.values("05810", "Alder")) == 7

    def test_values_can_be_searched(self, ssb):
        hits = ssb.values("11342", "Region", search="oslo")
        assert not hits.empty
        assert hits["label"].str.contains("Oslo").all()

    def test_values_without_a_variable_stacks_them_all(self, ssb):
        assert set(ssb.values("05810")["variable"]) == {"Kjonn", "Alder", "ContentsCode", "Tid"}


class TestSearch:
    def test_returns_a_frame_of_tables(self, ssb):
        with pytest.warns(UserWarning):
            frame = ssb.search("befolkning", limit=5)
        assert list(frame.columns)[:3] == ["id", "label", "description"]
        assert len(frame) == 5

    def test_warns_when_more_matched_than_shown(self, ssb):
        with pytest.warns(UserWarning, match="tables matched"):
            ssb.search("befolkning", limit=5)


class TestFetch:
    def test_returns_a_tidy_frame_with_codes_split_out(self, ssb):
        frame = ssb.fetch("05810", Kjonn="0", Alder="*", time=range(2020, 2026))
        assert list(frame.columns) == [
            "Kjonn",
            "Kjonn_code",
            "Alder",
            "Alder_code",
            "ContentsCode",
            "ContentsCode_code",
            "Tid",
            "Tid_code",
            "year",
            "value",
        ]
        assert len(frame) == 42
        assert ptypes.is_integer_dtype(frame["value"])
        # No .iloc surgery and no string splitting needed to get here.
        assert frame.loc[0, "Alder"] == "Alder" or frame["Alder_code"].iloc[0] == "999B"

    def test_show_is_always_explicit(self, ssb, fake_api):
        # SSB mixes per-dimension defaults (Tid is "code", the rest "value"),
        # so relying on show=None gives a mixed-format frame.
        ssb.fetch("05810", Kjonn="0")
        assert fake_api.last_call["show"] == "code_value"

    @pytest.mark.parametrize(("labels", "show"), [("label", "value"), ("code", "code")])
    def test_labels_maps_onto_show(self, ssb, fake_api, labels, show):
        ssb.fetch("05810", Kjonn="0", labels=labels)
        assert fake_api.last_call["show"] == show

    def test_the_sent_selection_is_recorded(self, ssb):
        dataset = ssb.dataset("05810", Kjonn="0", time=["2024", "2025"])
        assert dataset.query["Tid"] == ["2024", "2025"]
        assert dataset.query["ContentsCode"] == ["Personer"]

    def test_multi_value_filters_take_a_real_list(self, ssb, fake_api):
        ssb.fetch("11342", Region=["03", "11", "50", "56"], contents="Folkemengde", time="2025")
        assert fake_api.last_call["value_codes"]["Region"] == ["03", "11", "50", "56"]

    def test_table_handle_binds_the_id(self, ssb):
        assert ssb.table("05810").fetch(Kjonn="0").equals(ssb.fetch("05810", Kjonn="0"))

    def test_filters_dict_works_for_awkward_variable_codes(self, ssb, fake_api):
        ssb.fetch("05810", {"Kjonn": "0"})
        assert fake_api.last_call["value_codes"]["Kjonn"] == ["0"]

    def test_a_code_list_failure_names_the_code_list_in_the_error(self, ssb, fake_api, monkeypatch):
        # SSB returns a detail-free 500 for an unknown code list id, so the
        # wrapper has to point at the likely culprit itself. F-04.
        from requests.exceptions import HTTPError

        from ssb_statistikkbanken import SsbHTTPError

        def boom(*args, **kwargs):
            raise HTTPError("Error 500: Internal Server Error\nDetail: None")

        monkeypatch.setattr(fake_api, "get_table_data", boom)
        with pytest.raises(SsbHTTPError, match="agg_FemAarigGruppering"):
            ssb.fetch("07459", Region="0301", code_list={"Alder": "agg_FemAarigGruppering"})
