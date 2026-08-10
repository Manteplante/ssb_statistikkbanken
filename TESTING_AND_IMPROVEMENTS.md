# Battle-testing `ssb_statistikkbanken`

The offline suite proves the code does what we designed. This tracks whether the
design survives SSB's *real* data.

## Round 1 — 10 Aug 2026

Four notebooks in [`eda/battle_testing/`](eda/battle_testing/), both checklists
worked through live. **3 bugs found, 3 fixed.** Tests 108 → 121.

**The lesson:** both serious bugs came from trusting SSB's metadata over the data
that actually came back — treat metadata as a hint, not a fact. Neither was
catchable offline: every fixture was annual and single-unit, so the suite only
confirmed its own assumptions. Table 13902 is now a fixture.

## Summary report

Ran the wrapper against tables it had never seen -- traffic accidents,
naturfare (flom/skred) -- via four new notebooks in eda/battle_testing/.
Found three real bugs. All three came from the same root cause: trusting
SSB's metadata over the data that actually came back.

F-05: fetch() crashed on tables that mix units
  SSB reports `decimals` per table, but a table can vary units per
  ContentsCode. Table 13902 pairs building counts (2) with road length in
  km (0.2) while declaring decimals=0, so the Int64 cast raised TypeError
  and the table was unreachable as a DataFrame. Narrowing to one statistic
  did not help -- decimals is read from the table, not the selection.

  Worse, to_polars() did not crash: it silently truncated 0.2 to 0. The two
  backends disagreed and the quiet one corrupted data, which is why this is
  fixed with a shared Dataset._use_integer_values() rather than a pandas-only
  try/except. Genuine integer tables still get Int64, including whole floats
  and counts-only selections from a mixed table.

F-01: retired classifications returned silently empty
  KLASS answers an out-of-window date with an empty list, not an error, so
  klass.mapping(129, date=2025) returned {} and every downstream join became
  NaN with nothing to explain why. Now warns and names the real validity
  window, looked up via versions(). A failing lookup is swallowed so the
  diagnostic can never mask the caller's result.

F-04: a mistyped code list id gave a bare HTTP 500
  SSB answers this client mistake with a detail-free server error, so there
  was nothing actionable to show. The parsing was correct -- the information
  simply is not in the response. The wrapper now supplies the context and
  names the code_list ids to check.

Also documented, not changed:
  - search() matches value labels, not just titles ("skred" returns a table
    of surnames) -- noted in the docstring and src/README.md
  - ranged codes(from_=, to=) leaves validFrom/validTo as None (KLASS's shape)
  - notebook kernels ignore `uv run --with`; the kernelspec hardcodes .venv

Tests: 108 -> 121. Table 13902 is now a fixture, because none of this was
catchable offline -- every existing fixture was annual and single-unit, so
the suite only ever confirmed the assumptions the code was written with.

Confirmed working under real load: batching (898,560 cells split into 2
requests, stitched back to the exact row count), monthly date derivation,
language="en", code_list on Region, all 18 Classification members, and the
2020 kommune reform via changes().

Restores eda/output/.gitignore, which went missing unrelated to this work.

### Fixed

🔴 **F-05 · `fetch()` crashed on mixed-unit tables.** `decimals` is table-level,
but 13902 mixes counts (`2`) with km (`0.2`) under one `ContentsCode`. pandas
raised `TypeError`; polars silently truncated `0.2` → `0`. `_use_integer_values()`
now lets the data decide, shared by both backends. Integer tables keep `Int64`.

🟠 **F-01 · retired classifications returned silently empty.**
`mapping(129, date=2025)` → `{}` with no warning, so downstream joins became
`NaN`. Now warns and names the window (*"only valid 1994-10-01 -> 2019-01-01"*).

🟡 **F-04 · a mistyped code list gave a bare 500.** SSB returns a detail-free 500
for a client mistake; the wrapper now says so and names the ids to check.

### Documented, not changed

- **F-07** — `search()` matches value labels, so `"skred"` returns a table of
  surnames. Noted in the docstring and `src/README.md`.
- **F-06** — notebook kernels ignore `uv run --with` (kernelspec hardcodes
  `.venv`), so anything a notebook needs must be a real dependency.
- **F-03** — ranged `codes(from_=, to=)` leaves `validFrom`/`validTo` as `None`.

### Confirmed working

Batching (898,560 cells → 2 requests → exact row count, 6.3s) · monthly `date`
derivation · `language="en"` · `code_list` on `Region` · all 18 `Classification`
members · the 2020 kommune reform via `changes()` · `attach_names` warnings stay
readable at scale. PxWeb expressions *do* defeat batching, as documented:
`time="top(330)"` gave a live `400 Too many cells selected`.

## Notebooks

- `01_search_discovery` — keyword search (ulykke/drukning/flom/skred), `paths()`
- `02_klass_sweep` — the whole KLASS checklist
- `03_fetch_stress` — monthly dates, `code_list`, batching, language, F-05
- `04_error_shapes` — live 404 / 500 / 400 vs `errors.py`

Re-run after any wrapper change: `cd eda/battle_testing && uv run jupyter
nbconvert --to notebook --execute --inplace *.ipynb`

## Next round

Quarterly tables (`2026K1` — shares the monthly path, never run) · a huge-`Region`
table (grunnkrets, ~16k codes) · more of the ~3,787 tables, since round 1 touched
6 and still found a crash · decide whether polars joins the `notebook` group.
