"""Exceptions raised by the wrapper.

pxwebpy raises a bare ``requests.exceptions.HTTPError`` whose *message* carries
the status code and the API's problem-details body, but with no ``.response``
attached. :func:`wrap_pxweb_errors` parses that message back into something
typed and actionable.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Iterator
from contextlib import contextmanager

from requests.exceptions import HTTPError

__all__ = [
    "BadSelectionError",
    "ClassificationNotFoundError",
    "KlassError",
    "MissingDependencyError",
    "RateLimitedError",
    "SelectionTooLargeError",
    "SsbError",
    "SsbHTTPError",
    "TableNotFoundError",
    "UnknownValueError",
    "UnknownVariableError",
    "suggest",
    "wrap_pxweb_errors",
]


class SsbError(Exception):
    """Base class for every error raised by this package."""


class SsbHTTPError(SsbError):
    """An HTTP-level failure from SSB's API."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail
        self.endpoint = endpoint


class TableNotFoundError(SsbHTTPError):
    """The table id does not exist (HTTP 404)."""


class RateLimitedError(SsbHTTPError):
    """SSB refused the request because too many were sent (HTTP 429)."""


class BadSelectionError(SsbHTTPError):
    """SSB rejected the selection (HTTP 400), e.g. an unknown value code."""


class UnknownVariableError(SsbError):
    """A filter names a variable the table does not have."""

    def __init__(
        self, message: str, *, variable: str, available: Iterable[str], suggestions: list[str]
    ) -> None:
        super().__init__(message)
        self.variable = variable
        self.available = list(available)
        self.suggestions = suggestions


class UnknownValueError(SsbError):
    """A filter names a value code the variable does not have."""

    def __init__(
        self, message: str, *, variable: str, values: Iterable[str], suggestions: list[str]
    ) -> None:
        super().__init__(message)
        self.variable = variable
        self.values = list(values)
        self.suggestions = suggestions


class SelectionTooLargeError(SsbError):
    """The selection would produce more cells than ``max_cells`` allows."""

    def __init__(
        self,
        message: str,
        *,
        estimated_cells: int,
        max_cells: int,
        largest_variable: str | None = None,
    ) -> None:
        super().__init__(message)
        self.estimated_cells = estimated_cells
        self.max_cells = max_cells
        self.largest_variable = largest_variable


class MissingDependencyError(SsbError):
    """An optional dependency is needed for the requested output format."""


class KlassError(SsbError):
    """A failure talking to the KLASS classification API."""


class ClassificationNotFoundError(KlassError):
    """The classification id does not exist in KLASS."""


# --- did-you-mean -----------------------------------------------------------


def suggest(
    needle: str, candidates: Iterable[str], *, n: int = 3, cutoff: float = 0.55
) -> list[str]:
    """Return up to ``n`` candidates that look like ``needle``, case-insensitively."""
    pool = {str(c).casefold(): str(c) for c in candidates}
    matches = difflib.get_close_matches(needle.casefold(), list(pool), n=n, cutoff=cutoff)
    return [pool[m] for m in matches]


# --- pxwebpy error translation ---------------------------------------------

_STATUS_RE = re.compile(r"^Error (\d{3}):")
_FIELD_RE = re.compile(r"^(Type|Title|Status|Detail|Instance): (.*)$", re.MULTILINE)


def parse_pxweb_message(message: str) -> tuple[int | None, str | None]:
    """Pull the status code and human-readable detail out of a pxwebpy error string.

    pxwebpy formats its ``HTTPError`` as::

        Error 404: Not Found
        Type: ...
        Title: Table not found
        Status: 404
        Detail: ...
        Instance: ...

    Returns ``(None, None)`` for anything that does not match, so an upstream
    change degrades to a generic error rather than crashing.
    """
    status: int | None = None
    if (match := _STATUS_RE.match(message)) is not None:
        status = int(match.group(1))

    fields = {key: value.strip() for key, value in _FIELD_RE.findall(message)}
    # "None" is what pxwebpy interpolates when the key is absent from the body.
    detail = next(
        (fields[key] for key in ("Detail", "Title") if fields.get(key) not in (None, "", "None")),
        None,
    )
    return status, detail


def _build(
    status: int | None,
    detail: str | None,
    message: str,
    table_id: str | None,
    endpoint: str | None,
    hint: str | None = None,
) -> SsbHTTPError:
    suffix = f" ({detail})" if detail else ""

    if status is not None and status >= 500:
        # SSB answers some *client* mistakes with a server error and no detail
        # body -- notably an unknown code list id. Say so, since the response
        # itself carries nothing the user can act on.
        return SsbHTTPError(
            f"SSB returned a server error (HTTP {status}).{suffix}"
            + (f"\n  Tip: {hint}" if hint else ""),
            status_code=status,
            detail=detail,
            endpoint=endpoint,
        )

    if status == 404:
        where = f"table '{table_id}'" if table_id else f"resource '{endpoint}'"
        return TableNotFoundError(
            f"{where} was not found (HTTP 404).{suffix}\n"
            "  Tip: find a valid table id with ssb.search(...).",
            status_code=status,
            detail=detail,
            endpoint=endpoint,
        )
    if status == 429:
        return RateLimitedError(
            "SSB rate limited the request (HTTP 429) even after retries."
            f"{suffix}\n"
            "  Tip: lower max_workers, or narrow the selection so fewer requests are needed.",
            status_code=status,
            detail=detail,
            endpoint=endpoint,
        )
    if status == 400:
        return BadSelectionError(
            f"SSB rejected the selection (HTTP 400).{suffix}\n"
            "  Tip: check variable and value codes with ssb.variables(...) / ssb.values(...).",
            status_code=status,
            detail=detail,
            endpoint=endpoint,
        )
    return SsbHTTPError(message, status_code=status, detail=detail, endpoint=endpoint)


@contextmanager
def wrap_pxweb_errors(
    *, table_id: str | None = None, endpoint: str | None = None, hint: str | None = None
) -> Iterator[None]:
    """Translate pxwebpy/requests failures into this package's exception types.

    ``hint`` is appended to server-error messages, where SSB's own response
    usually carries nothing actionable.
    """
    try:
        yield
    except HTTPError as exc:
        message = str(exc)
        status, detail = parse_pxweb_message(message)
        raise _build(status, detail, message, table_id, endpoint, hint) from exc
    except ValueError as exc:
        # pxwebpy validates value_codes types and the `show` argument itself.
        raise SsbError(str(exc)) from exc
