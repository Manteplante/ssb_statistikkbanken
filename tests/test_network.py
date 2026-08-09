"""Live smoke tests. Deselected by default -- run with ``-m network``.

These are the tests that notice when SSB changes something the offline
fixtures froze in place.
"""

from __future__ import annotations

import pytest
from pandas.api import types as ptypes

from ssb_statistikkbanken import SSB, TableNotFoundError, klass

pytestmark = pytest.mark.network


@pytest.fixture(scope="module")
def live() -> SSB:
    return SSB()


def test_search_finds_population_tables(live):
    assert not live.search("befolkning", limit=5).empty


def test_metadata_shape_is_still_what_we_assume(live):
    info = live.describe("05810")
    assert info.order == ["Kjonn", "Alder", "ContentsCode", "Tid"]
    assert info.time_variable == "Tid"
    assert info.decimals == 0


def test_fetch_returns_a_tidy_typed_frame(live):
    frame = live.fetch("05810", Kjonn="0", Alder="*", time=range(2020, 2026))
    assert frame.shape == (42, 10)
    assert ptypes.is_integer_dtype(frame["value"])
    assert frame["Alder_code"].notna().all()


def test_code_and_label_separator_is_still_colon_space(live):
    # We split on ": ". If pxwebpy or SSB changes it, the code column empties.
    assert live.fetch("05810", Kjonn="0")["Kjonn_code"].iloc[0] == "0"


def test_latest_matches_what_top_n_returns(live):
    by_latest = live.fetch("05810", Kjonn="0", latest=3)["Tid_code"].tolist()
    by_expression = live.fetch("05810", Kjonn="0", time="top(3)")["Tid_code"].tolist()
    assert by_latest == by_expression


def test_unknown_table_is_a_typed_error(live):
    with pytest.raises(TableNotFoundError):
        live.describe("99999")


def test_klass_kommuner_and_correspondence(live):
    assert len(klass.kommuner(2025)) > 300
    assert klass.kommune_til_fylke(2025)["0301"] == "03"


def test_rollup_reproduces_the_national_total(live):
    kommune_codes = klass.kommuner(2025)["code"].tolist()
    pop = live.fetch("11342", Region=kommune_codes, contents="Folkemengde", time="2025")
    pop = klass.attach_parent(pop, "Region_code", date=2025)
    national = live.fetch("11342", Region="0", contents="Folkemengde", time="2025")
    assert pop["value"].sum() == national["value"].iloc[0]
