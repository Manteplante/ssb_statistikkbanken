# Cheat sheet — `ssb_statistikkbanken` in Jupyter

Keep this open in a split pane while working in `eda/`. Everything below is
copy-pasteable. Full prose reference: [`src/README.md`](src/README.md).

```python
from ssb_statistikkbanken import SSB, klass

ssb = SSB()
```

---

## The loop

**search → describe → values → fetch → reshape.** Repeat with any table id.

```python
ssb.search("befolkning", limit=10)  # 1. which table?
ssb.describe("05810")  # 2. what's in it?
ssb.values("05810", "Alder")  # 3. what codes can I filter on?
df = ssb.fetch("05810", Kjonn="0", Alder="*", time=range(2020, 2026))  # 4. get it
wide = ssb.dataset("05810", Kjonn="0", Alder="*", time=range(2020, 2026)).to_wide()
```

---

## Discovery

| Call | Returns |
|---|---|
| `ssb.search("ulykke")` | matching tables as a DataFrame |
| `ssb.search("ulykke", limit=25)` | more rows (default 100; warns if truncated) |
| `ssb.search("ulykke", updated_within_days=365)` | only recently updated |
| `ssb.search(include_discontinued=True)` | include retired tables |
| `ssb.paths()` | subject-area tree (downloads full index, ~1.5s, then cached) |
| `ssb.tables("al")` | tables under a subject path |

⚠️ `search` matches **value labels** too, not just titles — `"skred"` returns a
table of surnames. Read the `label` column before trusting a hit.

---

## Inspection

| Call | Returns |
|---|---|
| `ssb.describe("05810")` | `TableInfo` — HTML card in Jupyter |
| `ssb.variables("05810")` | one row per dimension: size, **mandatory**, code lists |
| `ssb.values("05810", "Alder")` | every value code — never truncated |
| `ssb.values("07459", "Region", search="oslo")` | filter codes *and* labels |
| `ssb.values("05810")` | all variables stacked |
| `ssb.code_list("agg_FemAarigGruppering")` | members of a named aggregation |
| `ssb.table("05810")` | handle bound to one table |

Useful `TableInfo` attributes:

```python
info = ssb.describe("05810")
info.label  # '05810: Aldersgrupper og kjønnsfordeling ...'
info.order  # ['Kjonn', 'Alder', 'ContentsCode', 'Tid']
info.mandatory  # ['ContentsCode', 'Tid']  <- omit these and SSB 400s
info.time_unit  # 'annual' | 'monthly' | 'quarterly' | None
info.periods  # ('1845', '2026')
info.decimals  # 0   (a hint, not a promise -- see Gotchas)
info["Alder"].codes  # ['999B', '00-06', ...]  in SSB's own order
info["Alder"].labels  # ['Alle', '0-6 år', ...]
info["Alder"].n_values
```

---

## Fetching

```python
ssb.fetch(table_id, filters=None, *, time=None, latest=1, contents=None,
          code_list=None, labels="both", columns="code", language=None,
          max_cells=None, categorical=False, **filters)
```

### Filter values — all of these work

```python
ssb.fetch("11342", Region="03")  # single code
ssb.fetch("11342", Region=["03", "11", "15"])  # list (never ",".join!)
ssb.fetch("05810", time=range(2020, 2026))  # range
ssb.fetch("05810", time=[2024, 2025])  # ints are fine
ssb.fetch("07459", Region="03*")  # wildcard prefix
ssb.fetch("11342", Region="*")  # everything
ssb.fetch("05810", Alder="0-6 år")  # labels resolve to codes
ssb.fetch("05810", time="top(5)")  # PxWeb expression (see Gotchas)
ssb.fetch("12292", filters={"KOKkommuneregion0000": "EAK"})  # non-identifier codes
```

### Key parameters

| Parameter | Default | What it does |
|---|---|---|
| `latest=n` | `1` | last *n* periods when you don't pass `time` |
| `time=` | — | the time variable, by any of the forms above |
| `contents=` | — | alias for `ContentsCode` |
| `code_list={"Alder": "agg_..."}` | — | use an SSB aggregation; auto-selects that variable |
| `labels="both"` | `"both"` | `"label"` or `"code"` for a single column each |
| `columns="code"` | `"code"` | name columns by variable code (stable across languages) or `"label"` |
| `language="en"` | `"no"` | translates values; column names stay put |
| `max_cells=50_000` | `None` | refuse an oversized selection before sending |
| `categorical=True` | `False` | dimension columns as `category` dtype |

Anything mandatory you leave out is filled in automatically (`*`, or `latest`
for time). Eliminable variables you skip are aggregated away by SSB.

---

## Output shapes

```python
ds = ssb.dataset("05810", Kjonn="0", Alder="*", time=range(2020, 2026))

ds.to_pandas()  # tidy long (same as ssb.fetch)
ds.to_wide()  # wide pivot, SSB's value order preserved
ds.to_polars()  # needs polars installed
ds.to_records()  # list[dict] -- bring your own frame
ds.query  # the exact value codes that were sent
len(ds)  # row count
```

### `to_wide()` — use this instead of `pivot_table`

```python
ds.to_wide()  # time down, widest dimension across
ds.to_wide(columns="Alder_code")  # codes as headers
ds.to_wide(columns="Alder", index="year")
ds.to_wide(aggfunc="mean")
```

Plain `df.pivot_table(...)` sorts columns **alphabetically**, which puts
`7-15 år` between `67-79 år` and `80 år eller eldre` and pushes the `Alle` total
to the end. `to_wide()` restores SSB's published order on both axes.

---

## What comes back

`fetch()` gives one row per observation, already typed:

| Kjonn | Kjonn_code | Alder | Alder_code | Tid | Tid_code | year | value |
|---|---|---|---|---|---|---|---|
| Begge kjønn | 0 | 0-6 år | 00-06 | 2020 | 2020 | 2020 | 412551 |

- every dimension → a label column **and** a `_code` column (join on codes)
- `value` → nullable `Int64`, or `Float64` when the data has decimals
- `year` → `Int16` for annual tables; `date` → `datetime64` for monthly/quarterly

---

## KLASS — classifications and joins

```python
klass.kommuner(2025)  # municipalities at a date
klass.fylker(2025)  # counties
klass.bydeler(2025)  # city districts
klass.kommune_til_fylke(2025)  # {'0301': '03', ...}
klass.codes(klass.Classification.NARING_SN, date=2025)
klass.mapping(104, date=2025)  # {code: name}
klass.correspondence(131, 104, date=2025)  # kommune -> fylke
klass.changes(131, from_=2019, to=2021)  # the 2020 reform
klass.classifications(search="yrke")  # find a classification id
```

### Attach names / roll up

```python
df = klass.attach_names(df, "Region_code", klass.Classification.KOMMUNE, date=2025)
df = klass.attach_parent(df, "Region_code", date=2025)  # adds fylke_code + fylke
```

`on_missing="warn"` (default) reports codes KLASS doesn't have — SSB tables carry
aggregates like `"0"` (Hele landet) and historic codes. Use `"raise"` in a
pipeline, `"ignore"` to silence.

### Classification ids

`GRUNNKRETS 1` · `KJONN 2` · `NARING_SN 6` · `YRKE_STYRK 7` · `UTDANNING_NUS 36` ·
`LANDKODER_SSB3 91` · `LANDKODER_ALPHA2 100` · `BYDEL 103` · **`FYLKE 104`** ·
`HELSEREGION 105` · `OKONOMISK_REGION 108` · `TETTSTED 110` · `FYLKESKOMMUNE 127` ·
`SENTRALITET 128` · `KOMMUNEKLASSIFISERING 129` · **`KOMMUNE 131`** · `ALDER 282` ·
`LANDKODER_ALPHA3 552`

---

## Errors

All derive from `SsbError`, so one `except` catches everything:

```python
from ssb_statistikkbanken import SsbError

try:
    ssb.fetch("05810", Kjonne="0")
except SsbError as exc:
    print(exc)
```

| Exception | When |
|---|---|
| `UnknownVariableError` | typo'd variable — includes a did-you-mean |
| `UnknownValueError` | bad value code — includes a did-you-mean |
| `SelectionTooLargeError` | selection exceeds your `max_cells` |
| `TableNotFoundError` | HTTP 404 |
| `BadSelectionError` | HTTP 400 from SSB |
| `RateLimitedError` | HTTP 429 after retries |
| `MissingDependencyError` | `.to_polars()` without polars |
| `KlassError` / `ClassificationNotFoundError` | KLASS problems |

Variable and value names are checked **before** the request goes out, so typos
come back instantly rather than as an HTTP error.

---

## Gotchas

- **`decimals` is a hint.** SSB reports it per table, but units can vary per
  `ContentsCode` (counts + km in one table). The wrapper checks the actual values
  and falls back to `Float64` — don't assume `Int64`.
- **PxWeb expressions defeat batching.** `top(n)`, `from(x)`, `range(x,y)`, `?`
  are resolved by SSB, so the size can't be known up front and the request won't
  be split. For big pulls prefer `latest=n`, an explicit list, or `*`.
- **800,000 cells per request.** Larger selections are split and stitched
  automatically; you get a warning naming the split.
- **Empty KLASS result = wrong date.** A retired classification returns no codes;
  the wrapper warns and names the validity window.
- **Notebook kernels ignore `uv run --with`.** Anything a notebook imports must
  be a real project dependency.
- **Avoid 07:55–08:15**, SSB's publishing peak.

---

## Make targets

| Command | What |
|---|---|
| `make notebook` | scaffold a notebook in `eda/` (prompts for name + subfolder) |
| `make kernel` | register the venv as a Jupyter kernel |
| `make sync` | create/update `.venv` from `uv.lock` + install the git hooks |
| `make hooks` | point git at `.githooks/` so pre-commit lints (idempotent) |
| `make test` / `make test-net` | offline suite / live SSB smoke tests |
| `make lint` / `make format` / `make typecheck` | ruff and mypy |
| `make check` | everything CI runs |
| `make fixtures` | re-record test fixtures |

Branching is **feature branch → `dev` → `main`**; the pre-commit hook runs
`make lint`, and `git commit --no-verify` skips it. See
[Branching and review](README.md#branching-and-review).
