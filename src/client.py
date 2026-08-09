"""The SSB client -- search, inspect and fetch tables from Statistikkbanken.

Thin, opinionated layer over `pxwebpy <https://pypi.org/project/pxwebpy/>`_,
which handles the HTTP, the query batching, the threading and the response
cache. What this module adds is the part pxwebpy deliberately leaves open:
SSB-specific defaults, validation with useful error messages, and records
reshaped into a frame you can analyse without cleaning it first.
"""

from __future__ import annotations

import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from ._frames import SHOW_FOR_LABELS, Columns, Dataset, Labels, normalize_records
from ._meta import TableInfo, Variable, parse_metadata
from ._query import build_selection
from .config import (
    DEFAULT_LANGUAGE,
    DEFAULT_MAX_WORKERS,
    DEFAULT_SEARCH_LIMIT,
    DEFAULT_TIMEOUT,
    LARGE_QUERY_WARN_CELLS,
    SSB_API,
    SSB_MAX_DATA_CELLS,
)
from .errors import wrap_pxweb_errors

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

__all__ = ["SSB", "PxApiLike", "Table"]


class PxApiLike(Protocol):
    """The slice of :class:`pxweb.PxApi` this package uses.

    Declared as a protocol so tests can inject a fake and skip the network
    entirely -- see ``SSB(api=...)``.
    """

    def get_table_metadata(self, table_id: str) -> Any: ...

    def get_table_data(
        self,
        table_id: str,
        value_codes: dict[str, list[str] | str] | None = None,
        code_list: dict[str, str] | None = None,
        show: Any = None,
    ) -> list[dict[str, Any]]: ...

    def search(
        self,
        query: str | None = None,
        past_days: int | None = None,
        include_discontinued: bool | None = None,
        page_size: int | None = None,
    ) -> Any: ...

    def get_code_list(self, code_list_id: str) -> Any: ...

    def get_paths(self, path_id: str | None = None) -> list[dict[str, str]]: ...

    def tables_on_path(self, path_id: str) -> list[dict[str, Any]]: ...


class SSB:
    """Client for SSB's Statistikkbanken (PxWebApi v2).

    Parameters
    ----------
    language:
        ``"no"`` (default) or ``"en"``. Can be overridden per call.
    timeout:
        Seconds to wait for each HTTP request.
    max_workers:
        Concurrency used when a query is split into several requests. SSB's
        ``/config`` reports no rate limit, so pxwebpy will not throttle for us,
        yet SSB documents 30 requests per minute -- hence a conservative
        default rather than automatic sizing.
    cache:
        Keep an in-memory cache of API responses for an hour (pxwebpy's own).
    api:
        Inject a pre-built :class:`pxweb.PxApi` (or any :class:`PxApiLike`).
        Mostly useful in tests.

    Examples
    --------
    >>> ssb = SSB()
    >>> ssb.search("befolkning", limit=5)[["id", "label"]]      # doctest: +SKIP
    >>> ssb.fetch("05810", Kjonn="0", time=range(2020, 2026))   # doctest: +SKIP
    """

    def __init__(
        self,
        language: str = DEFAULT_LANGUAGE,
        *,
        timeout: int = DEFAULT_TIMEOUT,
        max_workers: int = DEFAULT_MAX_WORKERS,
        cache: bool = True,
        api: PxApiLike | None = None,
    ) -> None:
        self.language = language
        self.timeout = timeout
        self.max_workers = max_workers
        self.cache = cache
        self._apis: dict[str, PxApiLike] = {language: api} if api is not None else {}
        self._info: dict[tuple[str, str], TableInfo] = {}

    # -- plumbing ------------------------------------------------------------

    def _api(self, language: str | None = None) -> PxApiLike:
        """The pxwebpy client for a language, built on first use.

        Constructing a ``PxApi`` costs two HTTP calls, so ``SSB()`` itself stays
        free and usable offline.
        """
        lang = language or self.language
        if lang not in self._apis:
            from pxweb import PxApi

            with wrap_pxweb_errors(endpoint="/config"):
                self._apis[lang] = PxApi(
                    SSB_API,
                    language=lang,
                    timeout=self.timeout,
                    disable_cache=not self.cache,
                    max_workers=self.max_workers,
                )
        return self._apis[lang]

    def __repr__(self) -> str:
        return (
            f"SSB(language={self.language!r}, timeout={self.timeout}, "
            f"max_workers={self.max_workers}, cache={self.cache})"
        )

    # -- discovery -----------------------------------------------------------

    def search(
        self,
        query: str | None = None,
        *,
        updated_within_days: int | None = None,
        include_discontinued: bool = False,
        limit: int = DEFAULT_SEARCH_LIMIT,
        language: str | None = None,
    ) -> pd.DataFrame:
        """Find tables by free-text search over titles, variables and values.

        Parameters
        ----------
        query:
            Words to search for, e.g. ``"befolkning"``. Omit to list everything.
        updated_within_days:
            Only tables updated in the last *n* days.
        include_discontinued:
            Include tables SSB no longer updates.
        limit:
            Maximum number of results. Warns if more tables matched.

        Returns
        -------
        A frame with ``id``, ``label``, ``updated``, ``firstPeriod``,
        ``lastPeriod``, ``timeUnit``, ``variables``, ``path`` and ``source``.
        """
        import pandas as pd

        with wrap_pxweb_errors(endpoint="/tables"):
            response = self._api(language).search(
                query=query,
                past_days=updated_within_days,
                include_discontinued=include_discontinued or None,
                page_size=limit,
            )

        tables = response.get("tables", [])
        total = response.get("page", {}).get("totalElements")
        if total is not None and total > len(tables):
            warnings.warn(
                f"{total} tables matched but only {len(tables)} are shown. "
                "Raise limit= or narrow the query.",
                UserWarning,
                stacklevel=2,
            )

        rows = [
            {
                "id": table.get("id"),
                "label": table.get("label"),
                "description": table.get("description"),
                "updated": table.get("updated"),
                "firstPeriod": table.get("firstPeriod"),
                "lastPeriod": table.get("lastPeriod"),
                "timeUnit": table.get("timeUnit"),
                "variables": ", ".join(table.get("variableNames") or []),
                "path": " > ".join(p.get("label", "") for p in (table.get("paths") or [[]])[0]),
                "source": table.get("source"),
            }
            for table in tables
        ]
        return pd.DataFrame(
            rows,
            columns=[
                "id",
                "label",
                "description",
                "updated",
                "firstPeriod",
                "lastPeriod",
                "timeUnit",
                "variables",
                "path",
                "source",
            ],
        )

    def paths(self, path: str | None = None, *, language: str | None = None) -> pd.DataFrame:
        """List SSB's subject-area paths, optionally within a subtree.

        Note this downloads the full table index (several thousand rows) on
        first use; :meth:`search` is usually the faster way in.
        """
        import pandas as pd

        with wrap_pxweb_errors(endpoint="/tables"):
            found = self._api(language).get_paths(path)
        return pd.DataFrame(
            [{"id": p.get("id"), "label": p.get("label")} for p in found],
            columns=["id", "label"],
        )

    def tables(self, path: str, *, language: str | None = None) -> pd.DataFrame:
        """List the tables filed under a subject path (see :meth:`paths`).

        Like :meth:`paths`, this downloads the full table index on first use.
        """
        import pandas as pd

        with wrap_pxweb_errors(endpoint="/tables"):
            found = self._api(language).tables_on_path(path)
        return pd.DataFrame(
            [{"id": t.get("id"), "label": t.get("label")} for t in found],
            columns=["id", "label"],
        )

    # -- inspection ----------------------------------------------------------

    def describe(self, table_id: str, *, language: str | None = None) -> TableInfo:
        """Fetch a table's metadata as a :class:`~._meta.TableInfo`.

        Renders as a card in Jupyter, and supports ``info["Alder"]`` lookup.
        Cached per (table, language) for the lifetime of the client.
        """
        lang = language or self.language
        key = (str(table_id), lang)
        if key not in self._info:
            with wrap_pxweb_errors(table_id=str(table_id), endpoint="/metadata"):
                metadata = self._api(lang).get_table_metadata(str(table_id))
            self._info[key] = parse_metadata(str(table_id), metadata)
        return self._info[key]

    def variables(self, table_id: str, *, language: str | None = None) -> pd.DataFrame:
        """One row per variable: its code, label, size and whether it is mandatory."""
        import pandas as pd

        info = self.describe(table_id, language=language)
        rows = []
        for code in info.order:
            var = info.variables[code]
            preview = "; ".join(f"{c}: {label}" for c, label in list(var.values.items())[:3])
            if var.n_values > 3:
                preview += "; …"
            rows.append(
                {
                    "variable": code,
                    "label": var.label,
                    "n_values": var.n_values,
                    "mandatory": var.mandatory,
                    "code_lists": ", ".join(cl["id"] for cl in var.code_lists),
                    "example_values": preview,
                }
            )
        return pd.DataFrame(
            rows,
            columns=["variable", "label", "n_values", "mandatory", "code_lists", "example_values"],
        )

    def values(
        self,
        table_id: str,
        variable: str | None = None,
        *,
        search: str | None = None,
        language: str | None = None,
    ) -> pd.DataFrame:
        """Every value code of a variable -- these are what you pass to :meth:`fetch`.

        Omit ``variable`` to stack all of them. ``search`` filters on code or
        label, case-insensitively, which is how you find one municipality among
        356 without scrolling.
        """
        import pandas as pd

        info = self.describe(table_id, language=language)
        wanted = [info.require(variable)] if variable is not None else info.order

        rows = [
            {"variable": code, "code": value, "label": label, "index": position}
            for code in wanted
            for position, (value, label) in enumerate(info.variables[code].values.items())
        ]
        frame = pd.DataFrame(rows, columns=["variable", "code", "label", "index"])

        if search:
            needle = search.casefold()
            mask = frame["code"].str.casefold().str.contains(needle, regex=False) | frame[
                "label"
            ].str.casefold().str.contains(needle, regex=False)
            frame = frame[mask].reset_index(drop=True)
        return frame

    def code_list(self, code_list_id: str, *, language: str | None = None) -> pd.DataFrame:
        """The values of a named code list (an SSB aggregation or value set)."""
        import pandas as pd

        with wrap_pxweb_errors(endpoint=f"/codelists/{code_list_id}"):
            response = self._api(language).get_code_list(code_list_id)
        return pd.DataFrame(
            [{"code": v.get("code"), "label": v.get("label")} for v in response.get("values", [])],
            columns=["code", "label"],
        )

    def table(self, table_id: str) -> Table:
        """A handle bound to one table, so you stop repeating the id."""
        return Table(self, str(table_id))

    # -- fetching ------------------------------------------------------------

    def dataset(
        self,
        table_id: str,
        filters: Mapping[str, Any] | None = None,
        *,
        time: str | int | Sequence[str | int] | range | None = None,
        latest: int | None = 1,
        contents: str | Sequence[str] | None = None,
        code_list: Mapping[str, str] | None = None,
        labels: Labels = "both",
        columns: Columns = "code",
        language: str | None = None,
        max_cells: int | None = None,
        **kwargs: Any,
    ) -> Dataset:
        """Fetch a table as a :class:`~._frames.Dataset` (records, pandas or polars).

        Same signature as :meth:`fetch`; use this when you want polars, the raw
        records, or to see the exact selection that was sent via ``.query``.
        """
        info = self.describe(table_id, language=language)
        selection = build_selection(
            info,
            filters=filters,
            kwargs=kwargs,
            time=time,
            latest=latest,
            contents=contents,
            code_list=code_list,
            max_cells=max_cells,
        )

        if selection.unexpandable_variables:
            warnings.warn(
                "Selection uses PxWeb expressions "
                f"({', '.join(selection.unexpandable_variables)}) that only SSB can resolve, "
                "so the query cannot be sized or split up front. "
                "Prefer latest=n, an explicit list, or '*' if the request is large.",
                UserWarning,
                stacklevel=2,
            )
        elif selection.exact and selection.estimated_cells > LARGE_QUERY_WARN_CELLS:
            batches = -(-selection.estimated_cells // SSB_MAX_DATA_CELLS)
            warnings.warn(
                f"Selection is ~{selection.estimated_cells:,} cells"
                + (f" and will be split into {batches} requests" if batches > 1 else "")
                + ". Narrow it with filters if this is not what you meant.",
                UserWarning,
                stacklevel=2,
            )

        with wrap_pxweb_errors(table_id=str(table_id), endpoint="/data"):
            records = self._api(language).get_table_data(
                str(table_id),
                value_codes=dict(selection.value_codes),
                code_list=dict(selection.code_list) or None,
                show=SHOW_FOR_LABELS[labels],
            )

        rows, spec = normalize_records(records, info, labels=labels, columns=columns)
        return Dataset(
            rows=rows,
            spec=spec,
            info=info,
            query=dict(selection.value_codes),
            code_list=dict(selection.code_list),
        )

    def fetch(
        self,
        table_id: str,
        filters: Mapping[str, Any] | None = None,
        *,
        time: str | int | Sequence[str | int] | range | None = None,
        latest: int | None = 1,
        contents: str | Sequence[str] | None = None,
        code_list: Mapping[str, str] | None = None,
        labels: Labels = "both",
        columns: Columns = "code",
        language: str | None = None,
        max_cells: int | None = None,
        categorical: bool = False,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Fetch a table as a tidy long pandas frame.

        Filters can be given as keyword arguments (``Kjonn="0"``) or, for
        variable codes that are not valid Python identifiers, in ``filters``.
        Values may be a single code, a list, a ``range``, a wildcard like
        ``"03*"``, or a PxWeb expression like ``"top(5)"``.

        Any mandatory variable you leave out is selected in full, except the
        time variable, which defaults to the most recent ``latest`` periods.

        Parameters
        ----------
        labels:
            ``"both"`` (default) gives a label column and a ``*_code`` sibling;
            ``"label"`` or ``"code"`` give one column each.
        columns:
            Name columns after the variable ``"code"`` (default, and stable
            across languages) or its ``"label"``.
        max_cells:
            Refuse the request if the selection is bigger than this.

        Examples
        --------
        >>> ssb = SSB()
        >>> ssb.fetch("05810", Kjonn="0", Alder="*", time=range(2020, 2026))  # doctest: +SKIP
        >>> ssb.fetch("11342", Region=["03", "11"], contents="Folkemengde")   # doctest: +SKIP
        """
        return self.dataset(
            table_id,
            filters,
            time=time,
            latest=latest,
            contents=contents,
            code_list=code_list,
            labels=labels,
            columns=columns,
            language=language,
            max_cells=max_cells,
            **kwargs,
        ).to_pandas(categorical=categorical)


@dataclass(frozen=True)
class Table:
    """A table id bound to a client: ``ssb.table("05810").fetch(Kjonn="0")``."""

    ssb: SSB
    id: str

    def describe(self, **kw: Any) -> TableInfo:
        return self.ssb.describe(self.id, **kw)

    def variables(self, **kw: Any) -> pd.DataFrame:
        return self.ssb.variables(self.id, **kw)

    def values(self, variable: str | None = None, **kw: Any) -> pd.DataFrame:
        return self.ssb.values(self.id, variable, **kw)

    def fetch(self, filters: Mapping[str, Any] | None = None, **kw: Any) -> pd.DataFrame:
        return self.ssb.fetch(self.id, filters, **kw)

    def dataset(self, filters: Mapping[str, Any] | None = None, **kw: Any) -> Dataset:
        return self.ssb.dataset(self.id, filters, **kw)

    def __getitem__(self, variable: str) -> Variable:
        return self.describe()[variable]

    def __repr__(self) -> str:
        return repr(self.describe())

    def _repr_html_(self) -> str:
        return self.describe()._repr_html_()
