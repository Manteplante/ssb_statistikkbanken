"""Defaults and constants for the SSB wrapper.

Everything tunable lives here so the rest of the package never hardcodes a
magic number.
"""

from __future__ import annotations

# --- PxWebApi v2 -----------------------------------------------------------

#: Shorthand understood by pxwebpy (resolves to https://data.ssb.no/api/pxwebapi/v2).
SSB_API = "ssb"

DEFAULT_LANGUAGE = "no"
DEFAULT_TIMEOUT = 30

#: SSB reports ``maxCallsPerTimeWindow: 0`` in /config, which means pxwebpy's
#: rate limiter never engages -- yet SSB documents a limit of 30 requests per
#: minute per IP. We therefore cap concurrency ourselves instead of letting
#: ThreadPoolExecutor size itself from the CPU count.
DEFAULT_MAX_WORKERS = 4

#: Hard ceiling enforced by SSB on a single query.
SSB_MAX_DATA_CELLS = 800_000

#: Above this we warn, because the query will be split into several requests.
LARGE_QUERY_WARN_CELLS = 200_000

#: Default number of tables returned by :meth:`SSB.search`.
DEFAULT_SEARCH_LIMIT = 100

# --- KLASS ------------------------------------------------------------------

KLASS_BASE_URL = "https://data.ssb.no/api/klass/v1"
KLASS_DEFAULT_LANGUAGE = "nb"

#: Classifications change at most once a year, so a day of caching is plenty.
KLASS_CACHE_TTL = 86_400

# --- Query sugar ------------------------------------------------------------

#: Friendly aliases accepted wherever a variable name is expected. Resolution
#: still falls back to the table's own codes and labels, so these only kick in
#: when a table uses the conventional names.
VARIABLE_ALIASES: dict[str, str] = {
    "time": "Tid",
    "tid": "Tid",
    "year": "Tid",
    "aar": "Tid",
    "contents": "ContentsCode",
    "contentscode": "ContentsCode",
    "statistikkvariabel": "ContentsCode",
    "region": "Region",
}

#: Separator pxwebpy uses when ``show="code_value"``: ``"0301: Oslo"``.
CODE_VALUE_SEPARATOR = ": "

#: Suffix added to the code column when ``labels="both"``.
CODE_COLUMN_SUFFIX = "_code"

#: Name of the column holding the measured value.
VALUE_COLUMN = "value"
