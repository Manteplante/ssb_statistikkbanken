"""Parsing SSB metadata into something navigable."""

from __future__ import annotations

import pytest

from src import UnknownVariableError


def test_variables_keep_ssb_order(info_05810):
    assert info_05810.order == ["Kjonn", "Alder", "ContentsCode", "Tid"]


def test_values_are_ordered_by_category_index(info_05810):
    # json-stat2 only guarantees order via category.index, not the label dict.
    assert info_05810["Alder"].codes[:3] == ["999B", "00-06", "07-15"]
    assert info_05810["Kjonn"].codes == ["0", "2", "1"]


def test_mandatory_comes_from_elimination(info_05810):
    assert info_05810.mandatory == ["ContentsCode", "Tid"]
    assert info_05810["Alder"].mandatory is False


def test_roles_identify_time_and_contents(info_05810):
    assert info_05810.time_variable == "Tid"
    assert info_05810.contents_variable == "ContentsCode"
    assert info_05810.time_unit == "annual"
    assert info_05810.periods == ("1845", info_05810["Tid"].codes[-1])


def test_decimals_drive_integer_typing(info_05810):
    assert info_05810.decimals == 0


def test_resolve_accepts_code_or_label_case_insensitively(info_05810):
    assert info_05810.resolve("kjonn") == "Kjonn"
    assert info_05810.resolve("alder") == "Alder"
    assert info_05810.resolve("år") == "Tid"
    assert info_05810.resolve("nope") is None


def test_value_resolve_accepts_labels(info_05810):
    assert info_05810["Alder"].resolve("0-6 år") == "00-06"
    assert info_05810["Alder"].resolve("00-06") == "00-06"


def test_require_suggests_a_near_miss(info_05810):
    with pytest.raises(UnknownVariableError) as excinfo:
        info_05810.require("Kjonne")
    assert "Kjonn" in excinfo.value.suggestions
    assert "Did you mean: Kjonn (kjønn)?" in str(excinfo.value)


def test_code_lists_are_read_from_ssbs_lowercase_key(info_07459):
    # SSB spells it "codelists"; the PxWeb spec says "codeLists".
    ids = [cl["id"] for cl in info_07459["Alder"].code_lists]
    assert "agg_FemAarigGruppering" in ids


def test_repr_html_mentions_every_variable(info_05810):
    html = info_05810._repr_html_()
    for code in info_05810.order:
        assert code in html
