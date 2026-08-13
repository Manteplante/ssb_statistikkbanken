# SSB-statistikkbanken

A Python wrapper around [SSB](https://www.ssb.no)'s Statistikkbanken
([PxWebApi v2](https://www.ssb.no/api/pxwebapiv2)) and the
[KLASS](https://www.ssb.no/klass) classification register, built on
[pxwebpy](https://pypi.org/project/pxwebpy/).

The point of it is that a query returns a frame you can analyse immediately:
tidy long, correctly typed, with codes and labels in separate columns — no
`.iloc` surgery, no splitting `"0301: Oslo"` back apart, no hand-maintained
lookup tables for region names.

## Contents

- [Quickstart](#quickstart)
- [Use this as a library](#use-this-as-a-library)
- [Requirements](#requirements)
- [Setup](#setup)
- [Layout](#layout)
- [Development](#development)
- [Branching and review](#branching-and-review)
- [The notebooks in `eda/` and `maps/`](#the-notebooks-in-eda-and-maps)
- [Exploring data in Jupyter](#exploring-data-in-jupyter)
- [Cheat sheet](#cheat-sheet)
- [References](#references)
- [License](#license)

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

## Use this as a library

It's a real installable package (`src/ssb_statistikkbanken/`), so a Streamlit
app, a pipeline, or any other project on your machine can depend on it
directly from GitHub — no PyPI, nothing published, this repo stays private.

**1. Add it** — from the other project:

```bash
uv add "git+https://github.com/Manteplante/ssb_statistikkbanken" --branch main
```

**2. Import it** — exactly like the Quickstart above:

```python
from ssb_statistikkbanken import SSB, klass

ssb = SSB()
df = ssb.fetch("05810", Kjonn="0", Alder="*", time=range(2020, 2026))
```

**3. Auth** — nothing extra to configure. `uv add` shells out to `git`, so
whatever already lets you `git clone` this repo on that machine (VS Code's
GitHub auth, an SSH key, a stored PAT) is sufficient. Since the repo is
private, anyone else who wants to add it needs to be a GitHub collaborator
first.

**4. Pick up a later change here** — the consuming repo tracks `main`, so:

```bash
uv lock --upgrade-package ssb-statistikkbanken
```

pip works the same way, if that's what the other project uses:

```bash
pip install "git+https://github.com/Manteplante/ssb_statistikkbanken@main"
```

## Requirements

- **Linux, or WSL if you're on Windows.** Microsoft's install guide:
  [learn.microsoft.com/windows/wsl/install](https://learn.microsoft.com/en-us/windows/wsl/install).
- **[uv](https://docs.astral.sh/uv/)** for Python and dependency management. It's
  a standalone tool, not a pip package — if you haven't used it before, this
  walkthrough is a good primer: [realpython.com/python-uv](https://realpython.com/python-uv/).

## Setup

```bash
make sync     # uv sync --locked, plus core.hooksPath -> .githooks
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
| `make sync` | create/update `.venv` from `uv.lock`, and install the git hooks |
| `make hooks` | point git at `.githooks/` (idempotent; `make sync` does it for you) |
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
Python 3.14 — the version `.python-version` pins and everyone here develops on.
It never calls SSB — run `make test-net` yourself when you want to know whether
the live API has drifted.

`requires-python` still allows 3.12, and ruff's `target-version` and mypy's
`python_version` both stay at 3.12 so nothing 3.13+-only can sneak into the
source. The syntax floor is enforced statically; it just isn't exercised at
runtime any more.

## Branching and review

```
feature branch ──PR──▶ dev ──PR──▶ main
                        ▲
                        └── admins may push straight here
```

`main` is the branch other repos install from, so it only ever moves through a
reviewed PR from `dev`. `dev` is the integration branch: it takes PRs from
feature branches, and repo admins can also push to it directly for small
changes that don't need the ceremony.

```bash
git switch dev && git pull
git switch -c feature/short-name
# ... work, commit ...
git push -u origin feature/short-name        # CI runs on this push
# open the PR against dev
```

Three things hold the flow together, at three different distances from you:

| Where | What it catches |
|---|---|
| `.githooks/pre-commit` | lint failures, before the commit exists |
| the `branch flow` CI job | a PR into `main` that didn't come from `dev` |
| GitHub rulesets | direct pushes, force-pushes, unreviewed merges |

### The pre-commit hook

`make sync` sets `core.hooksPath` to `.githooks/`, so the hook arrives with a
fresh clone's first setup command — no separate install step, and no
`pre-commit` package to add. It runs `make lint` (~1s) and refuses the commit if
ruff complains:

```bash
make format        # fix what it found
git add -u
git commit         # again
git commit --no-verify   # or skip the check for one commit
```

It deliberately doesn't run mypy or the tests — a hook people find slow is a
hook people disable. CI is where those live.

### Rulesets

Rulesets are server-side, so they're the only part a collaborator can't skip.
Set them up once:

```bash
DRY_RUN=1 ./scripts/protect_branches.sh                    # inspect the payloads
GITHUB_TOKEN=github_pat_... ./scripts/protect_branches.sh  # apply them
```

The token needs **Administration: read and write** on this repo. The script is
idempotent — re-run it after renaming a CI job, since the required checks are
matched by job name.

Two things worth knowing before you turn it on:

- **GitHub won't let you approve your own PR.** With
  `required_approving_review_count: 1` and no collaborators yet, `dev → main` is
  only mergeable via the admin bypass the script grants you. Run it with
  `APPROVALS=0` if you'd rather not lean on the bypass, and raise it when someone
  else joins.
- **To let a specific collaborator bypass too**, give them the *Maintain* role
  under Settings → Collaborators and add `{"actor_id": 4, ...}` to
  `bypass_actors` in the script.

If the API answers 403 with an upgrade notice, rulesets aren't available for
private repos on this account's plan. The hook and the `branch flow` job still
work; you just lose the enforcement half.

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
