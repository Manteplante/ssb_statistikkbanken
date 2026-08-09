# `src` — the SSB wrapper

Built on [pxwebpy](https://pypi.org/project/pxwebpy/), which supplies the HTTP
layer, query batching, threading and response caching. This package adds the
SSB-specific defaults, validation and reshaping on top.

Not packaged — import it from source. From the repo root:

```python
from src import SSB, klass
```

From a notebook one directory down (`eda/`, `maps/`, …):

```python
import sys

sys.path.insert(0, "..")
from src import SSB, klass
```

## The 30-second version

```python
ssb = SSB()

ssb.search("befolkning", limit=10)  # find a table
ssb.describe("05810")  # what's in it (renders as a card)
ssb.values("05810", "Alder")  # the exact codes to filter on

df = ssb.fetch("05810", Kjonn="0", Alder="*", time=range(2020, 2026))
```

`df` comes back tidy and typed — one row per cell, `value` as a nullable
`Int64`, `year` as `Int16`, and every dimension as two columns: the human
label and a `_code` sibling.

| Kjonn | Kjonn_code | Alder | Alder_code | Tid | Tid_code | year | value |
|---|---|---|---|---|---|---|---|
| Begge kjønn | 0 | 0-6 år | 00-06 | 2020 | 2020 | 2020 | 412551 |

## What each piece does

| Call | Returns |
|---|---|
| `ssb.search(q, limit=, updated_within_days=)` | frame of matching tables |
| `ssb.paths()` / `ssb.tables(path)` | subject-area navigation (downloads the full index) |
| `ssb.describe(id)` | `TableInfo` — HTML card in Jupyter, `info["Alder"]` lookup |
| `ssb.variables(id)` | one row per dimension: size, mandatory, code lists |
| `ssb.values(id, var, search=)` | every value code — no truncation |
| `ssb.code_list(id)` | the members of a named aggregation |
| `ssb.fetch(id, ...)` | tidy pandas frame |
| `ssb.dataset(id, ...)` | `Dataset` → `.to_pandas()` / `.to_polars()` / `.to_records()` / `.query` |
| `ssb.table(id)` | a handle bound to one table |
| `klass.kommuner()` / `fylker()` / `codes(id, date=)` | KLASS classifications |
| `klass.attach_names(df, "Region_code", ...)` | authoritative names beside the codes |
| `klass.attach_parent(df, "Region_code")` | roll kommune up to fylke |

## Writing filters

Anything you can name, you can pass as a keyword argument; values can be a
single code, a list, a `range`, a wildcard or a PxWeb expression.

```python
ssb.fetch("11342", Region=["03", "11", "15"], contents="Folkemengde", time="2025")
ssb.fetch("07459", Region="03*", latest=1)
ssb.fetch("05810", Alder="0-6 år")  # labels resolve to codes
ssb.fetch("12292", filters={"KOKkommuneregion0000": "0301"})  # awkward codes
ssb.fetch("07459", Region="0301", code_list={"Alder": "agg_FemAarigGruppering"})
```

Defaults worth knowing:

- **`latest=1`** — with no time selection you get the most recent period, not
  the entire history.
- **Mandatory variables you leave out are selected in full** (`*`). Variables
  SSB can eliminate are simply left out, so it aggregates them away.
- **`labels="both"`** — set `"label"` or `"code"` for a single column each.
- **`columns="code"`** — columns are named after the variable code, so
  `language="en"` doesn't rename them under your script. `"label"` gives the
  Norwegian names.
- **`max_cells=`** — refuse a selection bigger than this, before sending it.

## Errors tell you what to do next

```
>>> ssb.fetch("05810", Kjonne="0")
UnknownVariableError: 'Kjonne' is not a variable in table 05810.
  Did you mean: Kjonn (kjønn)?
  Available: Kjonn, Alder, ContentsCode, Tid
  Tip: ssb.variables("05810")
```

Variable and value names are checked against the metadata *before* the request
goes out. `TableNotFoundError`, `BadSelectionError`, `RateLimitedError` and
`SelectionTooLargeError` all derive from `SsbError`.

## Migrating the old notebooks

The legacy wrapper (`src/api.py`, `src/fetcher.py`, `src/inspector.py` and the
old `src/klass.py`) has been **removed**. The notebooks in `eda/` and `maps/`
still open on `from src.fetcher import SSBcsvFetcher` and will not re-run as-is;
their committed outputs are kept as a record. Use this table to port one.

| Legacy | New |
|---|---|
| `SSBcsvFetcher()` | `SSB()` |
| `.search_tables(q)` / `.list_tables()` | `.search(q, limit=)` |
| `.print_table_info()` / `.print_dimensions()` / `.inspect_table()` | `.describe(id)` — returns data instead of printing |
| `.get_dimensions(id)` | `.variables(id)` / `.values(id, var)` |
| `.fetch_pivot_table()` / `.fetch_clean_table()` | `.fetch(id, **filters)` — tidy long |
| `filters={'Region': ','.join(codes)}` | `Region=codes` |
| `time_period='top(1)'` | `latest=1` (the default) |
| `df.iloc[1:]`, `df.iloc[:, 1:]`, `.str.split(' - ')` | nothing — codes arrive in their own columns |
| `.get_counties()` / `.get_county_mapping()` | `klass.fylker(date=)` / `klass.mapping(104, date=)` |
| `.get_municipalities()` / `.get_municipality_mapping()` | `klass.kommuner(date=)` / `klass.mapping(131, date=)` |
| hand-written `rename_map` for region names | `klass.attach_names(df, "Region_code", …)` |

Two legacy bugs disappeared with the old code: `inspect_table(table_id, lang)`
passed `lang` positionally into the inspector's `filters` slot, so the language
argument was silently ignored; and `get_classification` hardcoded
`from='2026-01-01'`, so it could only ever return the 2026 vintage. The
replacements take a real date — `klass.codes(131, date=2024)`.

## Tests

```bash
make test        # offline, against recorded fixtures
make test-net    # live SSB + KLASS
make fixtures    # re-record tests/fixtures/**/*.json
```

## Notes on the API this wraps

- SSB allows **800,000 cells per request**; pxwebpy splits larger selections
  automatically and fetches the parts concurrently.
- SSB's `/config` reports **no** rate limit, so pxwebpy will not throttle —
  but SSB documents 30 requests/minute per IP, which is why `max_workers`
  defaults to 4 here rather than to automatic sizing.
- `top(n)`, `from(x)`, `range(x,y)` and `?` are resolved by SSB, so a selection
  using them cannot be sized or split up front. `latest=n`, explicit lists and
  `*` all can be — prefer those for large queries.
- Avoid 07:55–08:15, SSB's publishing peak.
