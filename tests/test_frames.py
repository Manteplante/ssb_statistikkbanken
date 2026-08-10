"""Reshaping pxwebpy records into an analysis-ready frame."""

from __future__ import annotations

import pandas as pd
import pytest
from pandas.api import types as ptypes

from ssb_statistikkbanken import Dataset, normalize_records
from ssb_statistikkbanken._frames import _split_code_value


class TestSplitting:
    def test_splits_on_the_first_separator_only(self):
        assert _split_code_value("0301: Oslo") == ("0301", "Oslo")
        assert _split_code_value("50: Trøndelag - Trööndelage") == (
            "50",
            "Trøndelag - Trööndelage",
        )

    def test_missing_separator_keeps_the_label_intact(self):
        # Better a missing code than two corrupted columns.
        assert _split_code_value("Oslo") == (None, "Oslo")

    def test_non_strings_pass_through(self):
        assert _split_code_value(None) == (None, None)


class TestNormalize:
    def test_columns_are_named_after_variable_codes_by_default(self, info_05810):
        records = [{"kjønn": "0: Begge kjønn", "år": "2024: 2024", "value": 1}]
        rows, spec = normalize_records(records, info_05810)
        assert spec.columns == ("Kjonn", "Kjonn_code", "Tid", "Tid_code", "year", "value")
        assert rows[0]["Kjonn"] == "Begge kjønn"
        assert rows[0]["Kjonn_code"] == "0"

    def test_columns_label_uses_the_norwegian_names(self, info_05810):
        records = [{"kjønn": "0: Begge kjønn", "år": "2024: 2024", "value": 1}]
        _, spec = normalize_records(records, info_05810, columns="label")
        assert "kjønn" in spec.columns
        assert "kjønn_code" in spec.columns

    @pytest.mark.parametrize(("labels", "expected"), [("label", "Begge kjønn"), ("code", "0")])
    def test_single_column_modes(self, info_05810, labels, expected):
        records = [{"kjønn": expected, "år": "2024", "value": 1}]
        rows, spec = normalize_records(records, info_05810, labels=labels)
        assert "Kjonn_code" not in spec.columns
        assert rows[0]["Kjonn"] == expected

    def test_dimensions_are_ordered_as_ssb_orders_them(self, info_05810):
        records = [{"år": "2024: 2024", "kjønn": "0: Begge kjønn", "value": 1}]
        _, spec = normalize_records(records, info_05810)
        assert spec.columns.index("Kjonn") < spec.columns.index("Tid")

    def test_value_is_always_last(self, info_05810):
        records = [{"kjønn": "0: Begge kjønn", "år": "2024: 2024", "value": 1}]
        _, spec = normalize_records(records, info_05810)
        assert spec.columns[-1] == "value"

    def test_unknown_keys_are_kept_and_warned_about(self, info_05810):
        records = [{"kjønn": "0: Begge kjønn", "mystery": "x: y", "value": 1}]
        with pytest.warns(UserWarning, match="Unrecognised columns"):
            _, spec = normalize_records(records, info_05810)
        assert "mystery" in spec.columns

    def test_year_is_derived_from_annual_period_codes(self, info_05810):
        records = [{"år": "2024: 2024", "value": 1}]
        rows, spec = normalize_records(records, info_05810)
        assert spec.year_column == "year"
        assert rows[0]["year"] == 2024

    def test_no_time_column_derived_when_codes_do_not_parse(self, info_05810):
        records = [{"år": "1845-1900: perioden", "value": 1}]
        _, spec = normalize_records(records, info_05810)
        assert spec.year_column is None and spec.date_column is None

    def test_empty_result_still_has_a_shape(self, info_05810):
        rows, spec = normalize_records([], info_05810)
        assert rows == []
        assert spec.columns == ("value",)

    def test_invalid_arguments_are_rejected(self, info_05810):
        with pytest.raises(ValueError, match="labels must be"):
            normalize_records([], info_05810, labels="nope")


class TestDataset:
    @pytest.fixture
    def dataset(self, info_05810):
        records = [
            {"kjønn": "0: Begge kjønn", "år": "2024: 2024", "value": 5550203},
            {"kjønn": "0: Begge kjønn", "år": "2025: 2025", "value": None},
        ]
        rows, spec = normalize_records(records, info_05810)
        return Dataset(rows=rows, spec=spec, info=info_05810, query={"Kjonn": ["0"]})

    def test_to_records_returns_copies(self, dataset):
        records = dataset.to_records()
        records[0]["value"] = 0
        assert dataset.rows[0]["value"] == 5550203

    def test_value_is_a_nullable_integer(self, dataset):
        frame = dataset.to_pandas()
        assert ptypes.is_integer_dtype(frame["value"])
        assert pd.isna(frame["value"].iloc[1])

    def test_year_is_a_small_integer(self, dataset):
        assert ptypes.is_integer_dtype(dataset.to_pandas()["year"])

    def test_dimensions_stay_strings_unless_asked(self, dataset):
        assert not isinstance(dataset.to_pandas()["Kjonn"].dtype, pd.CategoricalDtype)
        assert isinstance(dataset.to_pandas(categorical=True)["Kjonn"].dtype, pd.CategoricalDtype)

    def test_frame_columns_follow_the_spec(self, dataset):
        assert list(dataset.to_pandas().columns) == list(dataset.spec.columns)

    def test_len_counts_rows(self, dataset):
        assert len(dataset) == 2


class TestFloatTables:
    def test_decimals_make_the_value_column_float(self, info_05810):
        from dataclasses import replace

        info = replace(info_05810, decimals=1)
        rows, spec = normalize_records([{"år": "2024: 2024", "value": 1.5}], info)
        frame = Dataset(rows=rows, spec=spec, info=info).to_pandas()
        assert ptypes.is_float_dtype(frame["value"])


class TestMixedUnitTables:
    """Regression cover for a real table whose decimals hint contradicts its data.

    13902 reports decimals=0 but pairs building counts with road length in km.
    Trusting the hint made pandas raise TypeError and made polars silently
    truncate 0.2 to 0 -- see TESTING_AND_IMPROVEMENTS.md F-05.
    """

    @pytest.fixture
    def mixed(self, info_13902):
        records = [
            {
                "region": "0301: Oslo",
                "statistikkvariabel": "Bygninger",
                "år": "2026: 2026",
                "value": 2,
            },
            {
                "region": "0301: Oslo",
                "statistikkvariabel": "Veger",
                "år": "2026: 2026",
                "value": 0.2,
            },
        ]
        rows, spec = normalize_records(records, info_13902)
        return Dataset(rows=rows, spec=spec, info=info_13902)

    def test_the_hint_really_does_claim_integers(self, mixed):
        assert mixed.info.decimals == 0
        assert mixed.spec.integer_value is True

    def test_to_pandas_falls_back_to_float_instead_of_raising(self, mixed):
        frame = mixed.to_pandas()
        assert ptypes.is_float_dtype(frame["value"])
        assert frame["value"].tolist() == [2.0, 0.2]

    def test_to_polars_does_not_silently_truncate(self, mixed):
        pl = pytest.importorskip("polars")
        frame = mixed.to_polars()
        assert frame.schema["value"] == pl.Float64
        assert frame["value"].to_list() == [2.0, 0.2]

    def test_a_genuinely_integer_selection_still_gets_int64(self, info_13902):
        # Only the counts statistic: the hint and the data agree, so keep Int64.
        records = [
            {
                "region": "0301: Oslo",
                "statistikkvariabel": "Bygninger",
                "år": "2026: 2026",
                "value": 2,
            },
        ]
        rows, spec = normalize_records(records, info_13902)
        frame = Dataset(rows=rows, spec=spec, info=info_13902).to_pandas()
        assert ptypes.is_integer_dtype(frame["value"])

    def test_whole_floats_are_not_demoted(self, info_13902):
        # 4.0 is integral, so there is no reason to lose Int64 over it.
        records = [
            {
                "region": "0301: Oslo",
                "statistikkvariabel": "Bygninger",
                "år": "2026: 2026",
                "value": 4.0,
            },
        ]
        rows, spec = normalize_records(records, info_13902)
        frame = Dataset(rows=rows, spec=spec, info=info_13902).to_pandas()
        assert ptypes.is_integer_dtype(frame["value"])

    def test_nulls_do_not_trigger_the_fallback(self, info_13902):
        records = [
            {
                "region": "0301: Oslo",
                "statistikkvariabel": "Bygninger",
                "år": "2026: 2026",
                "value": None,
            },
        ]
        rows, spec = normalize_records(records, info_13902)
        frame = Dataset(rows=rows, spec=spec, info=info_13902).to_pandas()
        assert ptypes.is_integer_dtype(frame["value"])
