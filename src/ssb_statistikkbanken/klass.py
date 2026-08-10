"""KLASS -- SSB's classification register.

KLASS is where the authoritative names of administrative units live. Its main
job here is turning the region codes that come out of a Statistikkbanken fetch
into names you can join, label or map with -- without regex-stripping codes out
of strings or maintaining a rename dict by hand.

>>> from ssb_statistikkbanken import SSB, klass
>>> pop = SSB().fetch("11342", Region="*", contents="Folkemengde")   # doctest: +SKIP
>>> pop = klass.attach_names(pop, "Region_code", klass.Classification.FYLKE)  # doctest: +SKIP
"""

from __future__ import annotations

import datetime as _dt
import warnings
from collections.abc import Callable
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Literal, cast

import requests
from requests_cache import CachedSession

from .config import DEFAULT_TIMEOUT, KLASS_BASE_URL, KLASS_CACHE_TTL, KLASS_DEFAULT_LANGUAGE
from .errors import ClassificationNotFoundError, KlassError

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

__all__ = [
    "Classification",
    "Klass",
    "attach_names",
    "attach_parent",
    "bydeler",
    "changes",
    "classifications",
    "codes",
    "correspondence",
    "fylker",
    "kommune_til_fylke",
    "kommuner",
    "mapping",
]

OnMissing = Literal["warn", "raise", "ignore"]


class Classification(IntEnum):
    """Ids of the classifications used most often with Statistikkbanken data.

    Anything not listed here still works -- pass the numeric id straight to
    :meth:`Klass.codes`, or find it with :func:`classifications`.
    """

    GRUNNKRETS = 1
    KJONN = 2
    NARING_SN = 6
    YRKE_STYRK = 7
    UTDANNING_NUS = 36
    LANDKODER_SSB3 = 91
    LANDKODER_ALPHA2 = 100
    BYDEL = 103
    FYLKE = 104
    HELSEREGION = 105
    OKONOMISK_REGION = 108
    TETTSTED = 110
    FYLKESKOMMUNE = 127
    SENTRALITET = 128
    KOMMUNEKLASSIFISERING = 129
    KOMMUNE = 131
    ALDER = 282
    LANDKODER_ALPHA3 = 552


def _as_date(value: str | int | _dt.date | None) -> str:
    """Normalise a date argument to ``YYYY-MM-DD``, defaulting to today.

    A bare year means 1 January of that year, which is how classification
    vintages are named.
    """
    if value is None:
        return _dt.date.today().isoformat()
    if isinstance(value, int):
        return f"{value:04d}-01-01"
    if isinstance(value, _dt.datetime):
        return value.date().isoformat()
    if isinstance(value, _dt.date):
        return value.isoformat()
    return str(value)


class Klass:
    """Client for the KLASS v1 API.

    Responses are cached in memory for a day (classifications change at most
    once a year), and parsed frames are cached too -- but always handed out as
    copies, so mutating a result can never poison the cache.
    """

    def __init__(
        self,
        *,
        language: str = KLASS_DEFAULT_LANGUAGE,
        timeout: int = DEFAULT_TIMEOUT,
        cache_ttl: int = KLASS_CACHE_TTL,
        base_url: str = KLASS_BASE_URL,
        session: requests.Session | None = None,
    ) -> None:
        self.language = language
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")
        self.session = session or CachedSession(
            backend="memory", expire_after=cache_ttl, allowable_methods=("GET",)
        )
        self._frames: dict[tuple[Any, ...], pd.DataFrame] = {}

    def __repr__(self) -> str:
        return f"Klass(language={self.language!r}, base_url={self.base_url!r})"

    # -- plumbing ------------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        payload = {
            "language": self.language,
            **{k: v for k, v in (params or {}).items() if v is not None},
        }
        try:
            response = self.session.get(
                url, params=payload, headers={"Accept": "application/json"}, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise KlassError(f"Could not reach KLASS at {url}: {exc}") from exc

        if response.status_code == 404:
            detail = _detail(response)
            raise ClassificationNotFoundError(f"KLASS has no {path} (HTTP 404). {detail}".strip())
        if not response.ok:
            raise KlassError(
                f"KLASS request failed with HTTP {response.status_code} for {path}. "
                f"{_detail(response)}".strip()
            )
        # KLASS always returns a JSON object on these endpoints; a list would be
        # a protocol change, not something to defend against per call.
        return cast("dict[str, Any]", response.json())

    def _cached(self, key: tuple[Any, ...], build: Callable[[], pd.DataFrame]) -> pd.DataFrame:
        if key not in self._frames:
            self._frames[key] = build()
        return self._frames[key].copy()

    # -- catalogue -----------------------------------------------------------

    def classifications(
        self, *, family: int | None = None, search: str | None = None
    ) -> pd.DataFrame:
        """List the classifications KLASS publishes.

        ``search`` filters on the name, case-insensitively.
        """
        import pandas as pd

        def build() -> pd.DataFrame:
            payload = self._get(
                "/classifications", {"size": 1000, "classificationFamilyId": family}
            )
            items = payload.get("_embedded", {}).get("classifications", [])
            return pd.DataFrame(
                [
                    {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "type": item.get("classificationType"),
                        "familyId": item.get("classificationFamilyId"),
                        "lastModified": item.get("lastModified"),
                    }
                    for item in items
                ],
                columns=["id", "name", "type", "familyId", "lastModified"],
            )

        frame = self._cached(("classifications", family, self.language), build)
        if search:
            frame = frame[
                frame["name"].str.casefold().str.contains(search.casefold(), regex=False)
            ].reset_index(drop=True)
        return frame

    def info(self, classification: int | Classification) -> dict[str, Any]:
        """The raw description of a classification: name, type, versions, contact."""
        return self._get(f"/classifications/{int(classification)}")

    def versions(self, classification: int | Classification) -> pd.DataFrame:
        """The dated vintages of a classification -- one row per version."""
        import pandas as pd

        def build() -> pd.DataFrame:
            payload = self.info(classification)
            return pd.DataFrame(
                [
                    {
                        "id": v.get("id"),
                        "name": v.get("name"),
                        "validFrom": v.get("validFrom"),
                        "validTo": v.get("validTo"),
                    }
                    for v in payload.get("versions", [])
                ],
                columns=["id", "name", "validFrom", "validTo"],
            ).sort_values("validFrom", na_position="first", ignore_index=True)

        return self._cached(("versions", int(classification), self.language), build)

    def variants(
        self, classification: int | Classification, *, date: str | int | _dt.date | None = None
    ) -> pd.DataFrame:
        """Named variants (alternative groupings) available at a point in time."""
        import pandas as pd

        target = _as_date(date)
        versions = self.versions(classification)
        match = versions[
            (versions["validFrom"].fillna("0000-00-00") <= target)
            & ((versions["validTo"].isna()) | (versions["validTo"] > target))
        ]
        if match.empty:
            return pd.DataFrame(columns=["name", "validFrom", "validTo"])

        payload = self._get(f"/versions/{int(match.iloc[-1]['id'])}")
        return pd.DataFrame(
            [
                {
                    "name": v.get("name"),
                    "validFrom": v.get("validFrom"),
                    "validTo": v.get("validTo"),
                }
                for v in payload.get("classificationVariants", [])
            ],
            columns=["name", "validFrom", "validTo"],
        )

    # -- codes ---------------------------------------------------------------

    def codes(
        self,
        classification: int | Classification,
        *,
        date: str | int | _dt.date | None = None,
        from_: str | int | _dt.date | None = None,
        to: str | int | _dt.date | None = None,
        level: int | None = None,
        select_codes: str | None = None,
        variant: str | None = None,
    ) -> pd.DataFrame:
        """The codes of a classification, as a frame.

        By default this is a snapshot valid *today*; pass ``date=2024`` (or an
        ISO date) for another vintage, or ``from_``/``to`` for a range with
        validity intervals. ``level=1`` keeps only the top level, and
        ``select_codes="03*"`` filters by code pattern.
        """
        import pandas as pd

        classification_id = int(classification)
        params: dict[str, Any] = {"selectLevel": level, "selectCodes": select_codes}

        if from_ is not None or to is not None:
            endpoint = "variant" if variant else "codes"
            params |= {"from": _as_date(from_), "to": _as_date(to) if to is not None else None}
        else:
            endpoint = "variantAt" if variant else "codesAt"
            params |= {"date": _as_date(date)}
        if variant:
            params["variantName"] = variant

        key = ("codes", classification_id, endpoint, tuple(sorted(params.items())), self.language)

        def build() -> pd.DataFrame:
            payload = self._get(f"/classifications/{classification_id}/{endpoint}", params)
            return pd.DataFrame(
                [
                    {
                        "code": item.get("code"),
                        "parentCode": item.get("parentCode"),
                        "level": item.get("level"),
                        "name": item.get("name"),
                        "shortName": item.get("shortName"),
                        "validFrom": item.get("validFrom"),
                        "validTo": item.get("validTo"),
                        "notes": item.get("notes"),
                    }
                    for item in payload.get("codes", [])
                ],
                columns=[
                    "code",
                    "parentCode",
                    "level",
                    "name",
                    "shortName",
                    "validFrom",
                    "validTo",
                    "notes",
                ],
            )

        frame = self._cached(key, build)
        if frame.empty:
            self._warn_empty(classification_id, params.get("date") or params.get("from"))
        return frame

    def _warn_empty(self, classification_id: int, asked_for: str | None) -> None:
        """Explain a zero-code answer, which KLASS gives instead of an error.

        A retired classification (or a date before it existed) comes back as an
        empty list, so ``mapping()`` yields ``{}`` and every downstream join
        silently becomes NaN. Name the validity window so the date is fixable.
        """
        window = ""
        try:
            versions = self.versions(classification_id)
            if not versions.empty:
                first = versions["validFrom"].dropna()
                last = versions["validTo"].dropna()
                start = first.iloc[0] if len(first) else "?"
                end = last.iloc[-1] if len(last) else "still valid"
                window = f" It is only valid {start} -> {end}."
        except KlassError:  # pragma: no cover - diagnostics must never mask the result
            pass

        warnings.warn(
            f"KLASS returned no codes for classification {classification_id}"
            + (f" at {asked_for}." if asked_for else ".")
            + window
            + " Check the date -- an empty result makes downstream joins silently NaN.",
            UserWarning,
            stacklevel=3,
        )

    def mapping(self, classification: int | Classification, **kwargs: Any) -> dict[str, str]:
        """``{code: name}`` for a classification -- the shape most joins want."""
        frame = self.codes(classification, **kwargs)
        return dict(zip(frame["code"], frame["name"], strict=True))

    def correspondence(
        self,
        source: int | Classification,
        target: int | Classification,
        *,
        date: str | int | _dt.date | None = None,
        from_: str | int | _dt.date | None = None,
        to: str | int | _dt.date | None = None,
    ) -> pd.DataFrame:
        """How the codes of one classification map onto another's.

        The canonical use is kommune (131) to fylke (104).
        """
        import pandas as pd

        source_id, target_id = int(source), int(target)
        params: dict[str, Any] = {"targetClassificationId": target_id}
        if from_ is not None or to is not None:
            endpoint = "corresponds"
            params |= {"from": _as_date(from_), "to": _as_date(to) if to is not None else None}
        else:
            endpoint = "correspondsAt"
            params["date"] = _as_date(date)

        key = ("corr", source_id, target_id, tuple(sorted(params.items())), self.language)

        def build() -> pd.DataFrame:
            payload = self._get(f"/classifications/{source_id}/{endpoint}", params)
            return pd.DataFrame(
                [
                    {
                        "sourceCode": item.get("sourceCode"),
                        "sourceName": item.get("sourceName"),
                        "targetCode": item.get("targetCode"),
                        "targetName": item.get("targetName"),
                    }
                    for item in payload.get("correspondenceItems", [])
                ],
                columns=["sourceCode", "sourceName", "targetCode", "targetName"],
            )

        return self._cached(key, build)

    def changes(
        self,
        classification: int | Classification,
        *,
        from_: str | int | _dt.date,
        to: str | int | _dt.date | None = None,
    ) -> pd.DataFrame:
        """Codes that were added, removed or renumbered between two dates."""
        import pandas as pd

        classification_id = int(classification)
        params = {"from": _as_date(from_), "to": _as_date(to)}
        key = ("changes", classification_id, tuple(sorted(params.items())), self.language)

        def build() -> pd.DataFrame:
            payload = self._get(f"/classifications/{classification_id}/changes", params)
            return pd.DataFrame(
                payload.get("codeChanges", []),
                columns=["oldCode", "oldName", "newCode", "newName", "changeOccurred"],
            )

        return self._cached(key, build)


def _detail(response: requests.Response) -> str:
    try:
        return str(response.json().get("detail", ""))
    except ValueError:
        return ""


# --- module-level conveniences ---------------------------------------------

_default: Klass | None = None


def default_client() -> Klass:
    """The shared :class:`Klass` instance the module-level helpers use."""
    global _default
    if _default is None:
        _default = Klass()
    return _default


def classifications(**kwargs: Any) -> pd.DataFrame:
    """See :meth:`Klass.classifications`."""
    return default_client().classifications(**kwargs)


def codes(classification: int | Classification, **kwargs: Any) -> pd.DataFrame:
    """See :meth:`Klass.codes`."""
    return default_client().codes(classification, **kwargs)


def mapping(classification: int | Classification, **kwargs: Any) -> dict[str, str]:
    """See :meth:`Klass.mapping`."""
    return default_client().mapping(classification, **kwargs)


def correspondence(
    source: int | Classification, target: int | Classification, **kwargs: Any
) -> pd.DataFrame:
    """See :meth:`Klass.correspondence`."""
    return default_client().correspondence(source, target, **kwargs)


def changes(classification: int | Classification, **kwargs: Any) -> pd.DataFrame:
    """See :meth:`Klass.changes`."""
    return default_client().changes(classification, **kwargs)


def kommuner(date: str | int | _dt.date | None = None, **kwargs: Any) -> pd.DataFrame:
    """Norwegian municipalities as they stood on ``date`` (default: today)."""
    return default_client().codes(Classification.KOMMUNE, date=date, **kwargs)


def fylker(date: str | int | _dt.date | None = None, **kwargs: Any) -> pd.DataFrame:
    """Norwegian counties as they stood on ``date`` (default: today)."""
    return default_client().codes(Classification.FYLKE, date=date, **kwargs)


def bydeler(date: str | int | _dt.date | None = None, **kwargs: Any) -> pd.DataFrame:
    """City districts as they stood on ``date`` (default: today)."""
    return default_client().codes(Classification.BYDEL, date=date, **kwargs)


def kommune_til_fylke(date: str | int | _dt.date | None = None) -> dict[str, str]:
    """``{kommunenummer: fylkesnummer}`` at a point in time."""
    frame = default_client().correspondence(Classification.KOMMUNE, Classification.FYLKE, date=date)
    return dict(zip(frame["sourceCode"], frame["targetCode"], strict=True))


# --- join helpers -----------------------------------------------------------


def _report_missing(missing: list[Any], what: str, on_missing: OnMissing) -> None:
    if not missing or on_missing == "ignore":
        return
    shown = ", ".join(str(code) for code in missing[:10])
    more = f" (+{len(missing) - 10} more)" if len(missing) > 10 else ""
    message = (
        f"{len(missing)} code(s) had no match in {what}: {shown}{more}. "
        "SSB tables often include aggregates (e.g. '0' for the whole country) "
        "and historic codes that KLASS does not list for this date."
    )
    if on_missing == "raise":
        raise KlassError(message)
    warnings.warn(message, UserWarning, stacklevel=3)


def attach_names(
    frame: pd.DataFrame,
    code_column: str,
    classification: int | Classification = Classification.KOMMUNE,
    *,
    date: str | int | _dt.date | None = None,
    name_column: str | None = None,
    on_missing: OnMissing = "warn",
    klass: Klass | None = None,
    **kwargs: Any,
) -> pd.DataFrame:
    """Add authoritative KLASS names next to a column of codes.

    Returns a copy with the new column inserted right after ``code_column``.
    Unmatched codes become NaN and are reported, because a silent NaN after a
    join is how a map quietly loses a region.

    >>> attach_names(pop, "Region_code", Classification.FYLKE, date="2025-01-01")  # doctest: +SKIP
    """
    if code_column not in frame.columns:
        raise KeyError(f"{code_column!r} is not a column. Available: {list(frame.columns)}")

    client = klass or default_client()
    lookup = client.mapping(classification, date=date, **kwargs)
    target = name_column or f"{code_column}_navn"

    out = frame.copy()
    names = out[code_column].map(lookup)

    unmatched = sorted(
        {c for c, n in zip(out[code_column], names.isna(), strict=True) if n and c is not None}
    )
    _report_missing(unmatched, f"classification {int(classification)}", on_missing)

    if target in out.columns:
        out[target] = names
    else:
        out.insert(out.columns.get_loc(code_column) + 1, target, names)
    return out


def attach_parent(
    frame: pd.DataFrame,
    code_column: str,
    *,
    source: int | Classification = Classification.KOMMUNE,
    target: int | Classification = Classification.FYLKE,
    date: str | int | _dt.date | None = None,
    prefix: str = "fylke",
    on_missing: OnMissing = "warn",
    klass: Klass | None = None,
) -> pd.DataFrame:
    """Roll codes up to a coarser classification, e.g. kommune to fylke.

    Adds ``{prefix}_code`` and ``{prefix}`` columns.
    """
    if code_column not in frame.columns:
        raise KeyError(f"{code_column!r} is not a column. Available: {list(frame.columns)}")

    client = klass or default_client()
    corr = client.correspondence(source, target, date=date)
    to_code = dict(zip(corr["sourceCode"], corr["targetCode"], strict=True))
    to_name = dict(zip(corr["sourceCode"], corr["targetName"], strict=True))

    out = frame.copy()
    codes_out = out[code_column].map(to_code)
    names_out = out[code_column].map(to_name)

    unmatched = sorted(
        {c for c, n in zip(out[code_column], codes_out.isna(), strict=True) if n and c is not None}
    )
    _report_missing(unmatched, f"correspondence {int(source)} -> {int(target)}", on_missing)

    position = out.columns.get_loc(code_column) + 1
    for offset, (name, values) in enumerate(((f"{prefix}_code", codes_out), (prefix, names_out))):
        if name in out.columns:
            out[name] = values
        else:
            out.insert(position + offset, name, values)
    return out
