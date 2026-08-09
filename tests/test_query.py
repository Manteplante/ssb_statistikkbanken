"""Turning friendly filters into a PxWeb selection."""

from __future__ import annotations

import pytest

from ssb_statistikkbanken import (
    SelectionTooLargeError,
    UnknownValueError,
    UnknownVariableError,
    build_selection,
)
from ssb_statistikkbanken._query import coerce_values, expand_wildcard, is_expression


class TestCoercion:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("03", ["03"]),
            (2025, ["2025"]),
            (["03", "11"], ["03", "11"]),
            ([2020, 2021], ["2020", "2021"]),
            (range(2020, 2023), ["2020", "2021", "2022"]),
            (("03", 11), ["03", "11"]),
        ],
    )
    def test_accepts_the_shapes_people_actually_type(self, value, expected):
        assert coerce_values(value) == expected

    def test_rejects_nonsense(self):
        with pytest.raises(TypeError):
            coerce_values({"a": 1})


class TestExpressions:
    @pytest.mark.parametrize("value", ["*", "03*", "*sk*", "top(5)", "from(2020)", "20??"])
    def test_recognised(self, value):
        assert is_expression(value)

    @pytest.mark.parametrize("value", ["03", "999B", "80+", "0-6 år"])
    def test_literals_are_not_expressions(self, value):
        assert not is_expression(value)

    def test_wildcards_match_pxwebpy_semantics(self):
        items = ["03", "0301", "0302", "1103"]
        assert expand_wildcard("*", items) == items
        assert expand_wildcard("03*", items) == ["03", "0301", "0302"]
        assert expand_wildcard("*03", items) == ["03", "1103"]
        assert expand_wildcard("*30*", items) == ["0301", "0302"]


class TestSelection:
    def test_wildcards_expand_locally_so_cells_are_exact(self, info_05810):
        selection = build_selection(info_05810, kwargs={"Alder": "*"}, latest=1)
        assert selection.value_codes["Alder"] == info_05810["Alder"].codes
        assert selection.exact
        assert selection.estimated_cells == 7

    def test_mandatory_variables_are_filled_in(self, info_05810):
        # ContentsCode is mandatory and unmentioned: SSB would 400 without it.
        selection = build_selection(info_05810, kwargs={"Kjonn": "0"})
        assert selection.value_codes["ContentsCode"] == ["Personer"]

    def test_time_defaults_to_the_latest_period(self, info_05810):
        selection = build_selection(info_05810, kwargs={"Kjonn": "0"})
        assert selection.value_codes["Tid"] == [info_05810["Tid"].codes[-1]]

    def test_latest_n_takes_the_last_n_in_api_order(self, info_05810):
        selection = build_selection(info_05810, latest=3)
        assert selection.value_codes["Tid"] == info_05810["Tid"].codes[-3:]

    def test_time_argument_accepts_a_range(self, info_05810):
        selection = build_selection(info_05810, time=range(2020, 2023))
        assert selection.value_codes["Tid"] == ["2020", "2021", "2022"]

    def test_labels_are_resolved_to_codes(self, info_05810):
        selection = build_selection(info_05810, kwargs={"Alder": "0-6 år"})
        assert selection.value_codes["Alder"] == ["00-06"]

    def test_aliases_resolve(self, info_05810):
        selection = build_selection(info_05810, kwargs={"contents": "Personer"})
        assert selection.value_codes["ContentsCode"] == ["Personer"]

    def test_selection_follows_ssbs_dimension_order(self, info_05810):
        selection = build_selection(info_05810, kwargs={"Alder": "999B", "Kjonn": "0"})
        assert list(selection.value_codes) == ["Kjonn", "Alder", "ContentsCode", "Tid"]

    def test_duplicate_values_are_dropped(self, info_05810):
        selection = build_selection(info_05810, kwargs={"Alder": ["999B", "*"]})
        assert selection.value_codes["Alder"] == info_05810["Alder"].codes

    def test_unknown_variable_raises_with_a_suggestion(self, info_05810):
        with pytest.raises(UnknownVariableError, match="Did you mean: Kjonn"):
            build_selection(info_05810, kwargs={"Kjonne": "0"})

    def test_unknown_value_raises_with_a_suggestion(self, info_05810):
        with pytest.raises(UnknownValueError, match="Did you mean: '00-06'"):
            build_selection(info_05810, kwargs={"Alder": "0-6"})

    def test_wildcard_matching_nothing_is_an_error(self, info_05810):
        with pytest.raises(UnknownValueError, match="matched no value codes"):
            build_selection(info_05810, kwargs={"Alder": "zzz*"})

    def test_giving_a_variable_twice_is_refused(self, info_05810):
        with pytest.raises(ValueError, match="given twice"):
            build_selection(info_05810, filters={"Kjonn": "0"}, kwargs={"kjønn": "1"})

    def test_time_and_tid_together_is_refused(self, info_05810):
        with pytest.raises(ValueError, match="Pass the time selection once"):
            build_selection(info_05810, kwargs={"Tid": "2024"}, time="2025")

    def test_max_cells_names_the_biggest_variable(self, info_05810):
        with pytest.raises(SelectionTooLargeError) as excinfo:
            build_selection(info_05810, kwargs={"Alder": "*"}, time="*", max_cells=10)
        assert excinfo.value.largest_variable == "Tid"
        assert excinfo.value.estimated_cells == 7 * len(info_05810["Tid"].codes)

    def test_expressions_are_passed_through_and_flagged(self, info_05810):
        selection = build_selection(info_05810, time="top(5)")
        assert selection.value_codes["Tid"] == ["top(5)"]
        assert selection.unexpandable_variables == ("Tid",)
        assert not selection.exact

    def test_code_list_variable_is_selected_rather_than_summed_away(self, info_07459):
        selection = build_selection(
            info_07459,
            kwargs={"Region": "0301"},
            code_list={"Alder": "agg_FemAarigGruppering"},
        )
        # Without this, Alder would be eliminated and the grouping never appear.
        assert selection.value_codes["Alder"] == ["*"]
        # pxwebpy expands it against the code list, so batching still works.
        assert selection.unexpandable_variables == ()
