# ssb-statistikkbanken

A Python wrapper around [SSB](https://www.ssb.no)'s Statistikkbanken
([PxWebApi v2](https://www.ssb.no/api/pxwebapiv2)) and the
[KLASS](https://www.ssb.no/klass) classification register, built on
[pxwebpy](https://pypi.org/project/pxwebpy/).

The point of it is that a query returns a frame you can analyse immediately:
tidy long, correctly typed, with codes and labels in separate columns — no
`.iloc` surgery, no splitting `"0301: Oslo"` back apart, no hand-maintained
lookup tables for region names.

## Quickstart

`make sync` installs the package itself into `.venv` (editable), so this works
from anywhere in the repo — no `sys.path` hack:

```python
from ssb_statistikkbanken import SSB, klass

ssb = SSB()

# find a table
ssb.search("befolkning", limit=10)

# see what's in it -- an HTML card in Jupyter -- and the exact codes to filter on
ssb.describe("05810")
ssb.values("05810", "Alder")

df = ssb.fetch("05810", Kjonn="0", Alder="*", time=range(2020, 2026))
```

| Kjonn | Kjonn_code | Alder | Alder_code | Tid | Tid_code | year | value |
|---|---|---|---|---|---|---|---|
| Begge kjønn | 0 | 0-6 år | 00-06 | 2020 | 2020 | 2020 | 412551 |

`value` is a nullable `Int64`, `year` an `Int16`. Because the codes are their
own columns, joining against KLASS or a GeoJSON is a merge rather than a regex:

```python
kommuner = klass.kommuner(2025)["code"].tolist()
pop = ssb.fetch("11342", Region=kommuner, contents="Folkemengde", time="2025")

# roll municipalities up to counties using KLASS's own correspondence
pop = klass.attach_parent(pop, "Region_code")
pop.groupby("fylke", as_index=False)["value"].sum()
```

Full API reference: [`src/README.md`](src/README.md).

## Using this from another repo

It's a real installable package (`src/ssb_statistikkbanken/`), so a Streamlit
app, a pipeline, or any other repo on your machine can depend on it directly
from GitHub — no PyPI, nothing published, this repo stays private:

```bash
uv add "git+https://github.com/Manteplante/ssb_statistikkbanken" --branch main
```

```python
from ssb_statistikkbanken import SSB, klass
```

Whatever already lets you `git clone` this repo (VS Code's GitHub auth, an SSH
key, a stored PAT) is all `uv add` needs too — nothing extra to configure. The
consuming repo tracks `main`, so a change here shows up there after:

```bash
uv lock --upgrade-package ssb-statistikkbanken
```

Since it's private, anyone else who wants to add it needs to be a GitHub
collaborator on this repo first.

## Requirements

- **Linux, or WSL if you're on Windows.** Microsoft's install guide:
  [learn.microsoft.com/windows/wsl/install](https://learn.microsoft.com/en-us/windows/wsl/install).
- **[uv](https://docs.astral.sh/uv/)** for Python and dependency management. It's
  a standalone tool, not a pip package — if you haven't used it before, this
  walkthrough is a good primer: [realpython.com/python-uv](https://realpython.com/python-uv/).

## Setup

```bash
make sync     # uv sync --locked
```

`.python-version` pins 3.14; uv fetches it if you don't have it. On WSL2 keep
the repo on the Linux filesystem (`~/repositories/…`, not `/mnt/c/…`) — uv and
the test suite are dramatically slower across the 9p mount.

## Layout

| Path | What |
|---|---|
| `src/` | the wrapper — see [`src/README.md`](src/README.md) |
| `tests/` | 108 offline tests against recorded fixtures, plus 8 live tests marked `network` |
| `tests/fixtures/` | recorded SSB and KLASS responses; regenerate with `make fixtures` |
| `eda/`, `maps/` | analysis notebooks (see the note below) |

## Development

| Command | What |
|---|---|
| `make sync` | create/update `.venv` from `uv.lock` |
| `make format` | ruff auto-fix, then format |
| `make lint` | ruff check + format check, writing nothing |
| `make typecheck` | mypy over `src/` |
| `make test` | offline suite (no network) |
| `make test-net` | live smoke tests against SSB and KLASS |
| `make check` | lint + typecheck + test, in CI's order |
| `make coverage` | offline suite with an HTML report |
| `make kernel` | register this repo's `.venv` as a Jupyter kernel (idempotent) |
| `make notebook` | scaffold a new notebook in `eda/` — see [Exploring data in Jupyter](#exploring-data-in-jupyter) |
| `make fixtures` | re-record the test fixtures |

CI runs ruff, mypy and the offline suite on every push and pull request, on
Python 3.12 and 3.14. It never calls SSB — run `make test-net` yourself when you
want to know whether the live API has drifted.

## ⚠️ The notebooks in `eda/` and `maps/`

Most were written against an earlier wrapper (`from src.fetcher import
SSBcsvFetcher`) that has since been removed, and **will not re-run as-is** —
their committed outputs are kept as a record of the analysis. The migration
table in [`src/README.md`](src/README.md) maps every old call onto its
replacement.

**Exception:** [`eda/ssb_dataframe_fetcher_tool.ipynb`](eda/ssb_dataframe_fetcher_tool.ipynb)
has been ported to the new wrapper and runs end to end — see below.

## Exploring data in Jupyter

Develop notebooks locally in `eda/`, on this repo's own kernel — no separate
environment, no `sys.path` guesswork:

```bash
make notebook                            # prompts for a name, and a subfolder in eda/
make notebook name=population_trends     # -> eda/population_trends.ipynb
make notebook name=fylke_map subdir=maps_wip   # -> eda/maps_wip/fylke_map.ipynb
```

Each one is created with the standard header already in place
(`from ssb_statistikkbanken import SSB`, an `SSB()` instance ready to use — no
`sys.path` hack needed, the package is installed into `.venv`) and a kernelspec
pointing at this project's `.venv` — pick **ssb-statistikkbanken (.venv)** from
the kernel list in Jupyter or VS Code.
Because `eda/` is linted (`make lint` / `make check`, CI included — the three
notebooks still on the removed legacy wrapper are the only exclusion), what you
commit is held to the same bar as `src/`.

[`eda/ssb_dataframe_fetcher_tool.ipynb`](eda/ssb_dataframe_fetcher_tool.ipynb)
is a guided tour of the wrapper against a real table (05803, population changes
1735–2026) and is the fastest way to learn the API hands-on. It walks through:

1. **`ssb.search(...)`** — find a table by free-text query; the result is a
   DataFrame you can filter further, e.g. down to tables with a long history
2. **`ssb.describe(...)`** — an HTML metadata card: which variables exist, how
   many values each has, and which are mandatory
3. **`ssb.values(...)`** — every value code for a variable, the ones you pass
   to `fetch`
4. **`ssb.fetch(...)`** — the actual data, already tidy and typed
5. **`.pivot_table(...)`** — reshaping the tidy frame into a wide table for a
   quick look or a plot
6. a deliberate typo, to show what the did-you-mean error messages look like

Open it, run it top to bottom, then swap in your own table id and filters —
that loop (search → describe → values → fetch) is the intended way to explore
a new dataset.

## Cheat sheet

The calls behind that walkthrough, if you just want the reference:

| Call | What you get |
|---|---|
| `ssb.search("befolkning", limit=10)` | matching tables as a DataFrame |
| `ssb.describe("05803")` | table metadata card |
| `ssb.variables("05803")` | one row per variable |
| `ssb.values("05803", "ContentsCode")` | every value code |
| `ssb.fetch("05803", contents=[...], time=range(2020, 2026))` | tidy DataFrame |
| `ssb.dataset(...)` | same, but `.to_polars()` / `.to_records()` / `.query` |
| `ssb.table("05803")` | a handle bound to one table |

Filters take a single code, a list, a `range`, a wildcard (`"03*"`) or a PxWeb
expression (`"top(5)"`). Leave the time selection out and you get the most recent
period; mandatory variables you omit are selected in full.

## References

- [SSB PxWebApi v2](https://www.ssb.no/api/pxwebapiv2) — 800,000 cells per
  request, 30 requests/minute per IP, avoid 07:55–08:15
- [KLASS API](https://data.ssb.no/api/klass/v1/api-guide.html)
- [pxwebpy](https://stefur.github.io/pxwebpy/) — the client this builds on

## License

MIT
