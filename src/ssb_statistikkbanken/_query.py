"""Turning user-friendly filters into a PxWeb value-code selection.

Pure functions -- no network, no pandas. The client hands in a
:class:`~._meta.TableInfo` it already fetched and gets back a validated
selection plus an honest cell estimate.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ._meta import TableInfo
from .config import VARIABLE_ALIASES
from .errors import SelectionTooLargeError, UnknownValueError, suggest

__all__ = ["Selection", "build_selection", "coerce_values", "is_expression"]

#: PxWeb selection expressions we pass through untouched: top(5), from(2020), ...
_EXPRESSION_RE = re.compile(r"^[a-zA-Z]+\([^()]*\)$")


def is_expression(value: str) -> bool:
    """True for anything PxWeb must interpret itself rather than a literal code."""
    return "*" in value or "?" in value or bool(_EXPRESSION_RE.match(value))


def coerce_values(value: Any) -> list[str]:
    """Normalise whatever the caller passed into a list of strings.

    Accepts a single code, an int, a ``range``, or any sequence of those --
    which is what lets you write ``Region=["03", "11"]`` and
    ``time=range(2020, 2026)`` instead of pre-joining strings.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, bool):
        raise TypeError(f"Expected value codes, got {value!r}.")
    if isinstance(value, int):
        return [str(value)]
    if isinstance(value, range):
        return [str(v) for v in value]
    if isinstance(value, Sequence):
        out: list[str] = []
        for item in value:
            out.extend(coerce_values(item))
        return out
    raise TypeError(
        f"Cannot use {value!r} as value codes. Pass a string, an int, a range, or a list of those."
    )


def expand_wildcard(pattern: str, items: Sequence[str]) -> list[str]:
    """Expand a PxWeb wildcard against the known codes, matching pxwebpy's rules."""
    if pattern == "*":
        return list(items)
    starts, ends = pattern.startswith("*"), pattern.endswith("*")
    if starts and ends:
        needle = pattern[1:-1]
        return [c for c in items if needle in c]
    if ends:
        return [c for c in items if c.startswith(pattern[:-1])]
    if starts:
        return [c for c in items if c.endswith(pattern[1:])]
    return [pattern]


@dataclass(frozen=True)
class Selection:
    """A validated selection, ready to hand to pxwebpy."""

    value_codes: dict[str, list[str]]
    code_list: dict[str, str] = field(default_factory=dict)
    estimated_cells: int = 1
    #: False when ``estimated_cells`` is a lower bound rather than the real size.
    exact: bool = True
    #: Variables whose selection only SSB can resolve -- ``top(5)``, ``?``, ...
    #: pxwebpy counts these as one cell each, so its automatic batching cannot
    #: protect a query that uses them.
    unexpandable_variables: tuple[str, ...] = ()

    @property
    def largest_variable(self) -> str | None:
        if not self.value_codes:
            return None
        return max(self.value_codes, key=lambda k: len(self.value_codes[k]))

    def sizes(self) -> dict[str, int]:
        return {k: len(v) for k, v in self.value_codes.items()}


def _merge_filters(
    info: TableInfo,
    filters: Mapping[str, Any] | None,
    kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve both filter sources onto variable codes, refusing silent overrides."""
    merged: dict[str, Any] = {}
    origin: dict[str, str] = {}

    for source_name, source in (("filters", filters or {}), ("keyword argument", kwargs)):
        for raw_key, value in source.items():
            key = VARIABLE_ALIASES.get(str(raw_key).casefold(), raw_key)
            code = info.require(key)
            if code in merged:
                raise ValueError(
                    f"Variable {code!r} was given twice "
                    f"(as {origin[code]} and as {source_name}). Pass it once."
                )
            merged[code] = value
            origin[code] = source_name

    return merged


def _resolve_codes(
    info: TableInfo, variable: str, values: list[str], *, has_code_list: bool
) -> tuple[list[str], bool, bool]:
    """Validate and expand one variable's values.

    Returns ``(codes, exact, unexpandable)`` -- ``exact`` says whether the
    length of ``codes`` is the true selection size, ``unexpandable`` whether
    pxwebpy will be unable to expand it either (and so cannot batch it).
    """
    var = info.variables[variable]
    available = var.codes
    resolved: list[str] = []
    exact = True
    unexpandable = False

    for value in values:
        if not is_expression(value):
            # A literal: accept the code, or a label the user copied out of a frame.
            code = var.resolve(value)
            if code is None:
                if has_code_list:
                    # The valid codes come from the named code list, not the table.
                    resolved.append(value)
                    continue
                hits = suggest(value, available + var.labels)
                named = dict.fromkeys(
                    f"{c!r} ({var.values[c]})" for c in (var.resolve(h) for h in hits) if c
                )
                lines = [
                    f"{value!r} is not a value code for {variable} ({var.label}) "
                    f"in table {info.table_id}."
                ]
                if named:
                    lines.append(f"  Did you mean: {', '.join(named)}?")
                lines.append(f'  Tip: ssb.values("{info.table_id}", "{variable}")')
                raise UnknownValueError(
                    "\n".join(lines), variable=variable, values=values, suggestions=hits
                )
            resolved.append(code)
            continue

        if "*" in value and has_code_list:
            # pxwebpy expands this against the named code list, so batching
            # still works -- we just cannot size it from the table metadata.
            resolved.append(value)
            exact = False
            continue

        if "*" in value:
            # Expand locally so the cell count stays exact and pxwebpy does not
            # have to re-fetch the metadata we already hold.
            expanded = expand_wildcard(value, available)
            if not expanded:
                raise UnknownValueError(
                    f"Wildcard {value!r} matched no value codes for {variable} "
                    f"({var.label}) in table {info.table_id}.\n"
                    f'  Tip: ssb.values("{info.table_id}", "{variable}")',
                    variable=variable,
                    values=values,
                    suggestions=[],
                )
            resolved.extend(expanded)
            continue

        # top(n) / from(2020) / range(a,b) / ? -- PxWeb resolves these server side,
        # so neither we nor pxwebpy can count the cells they will produce.
        resolved.append(value)
        exact = False
        unexpandable = True

    # Deduplicate while preserving order (overlapping wildcards are easy to write).
    return list(dict.fromkeys(resolved)), exact, unexpandable


def build_selection(
    info: TableInfo,
    *,
    filters: Mapping[str, Any] | None = None,
    kwargs: Mapping[str, Any] | None = None,
    time: Any = None,
    latest: int | None = 1,
    contents: Any = None,
    code_list: Mapping[str, str] | None = None,
    max_cells: int | None = None,
) -> Selection:
    """Build and validate the value-code selection for a fetch.

    Mandatory variables the caller did not mention are filled with ``*``, except
    the time variable, which falls back to ``latest`` -- so an unqualified fetch
    returns the most recent period rather than the entire history.
    """
    merged = _merge_filters(info, filters, kwargs or {})
    resolved_code_list = {info.require(k): v for k, v in (code_list or {}).items()}

    time_var, contents_var = info.time_variable, info.contents_variable

    if time is not None:
        if time_var is None:
            raise ValueError(
                f"Table {info.table_id} has no time variable, so time= does not apply."
            )
        if time_var in merged:
            raise ValueError(
                f"Both time= and {time_var}= were given. Pass the time selection once."
            )
        merged[time_var] = time

    if contents is not None:
        if contents_var is None:
            raise ValueError(
                f"Table {info.table_id} has no contents variable, so contents= does not apply."
            )
        if contents_var in merged:
            raise ValueError(
                f"Both contents= and {contents_var}= were given. Pass the selection once."
            )
        merged[contents_var] = contents

    # Asking for a code list means you want that variable grouped, not summed
    # away -- so select all of it unless the caller narrowed it themselves.
    for code in resolved_code_list:
        merged.setdefault(code, "*")

    # Fill in what the API requires but the caller did not mention.
    for code in info.mandatory:
        if code in merged:
            continue
        if code == time_var and latest is not None:
            if latest < 1:
                raise ValueError(f"latest must be at least 1, got {latest}.")
            merged[code] = info.variables[code].codes[-latest:]
        else:
            merged[code] = "*"

    value_codes: dict[str, list[str]] = {}
    inexact: list[str] = []
    unexpandable: list[str] = []
    for variable in info.order:  # keep SSB's own dimension order
        if variable not in merged:
            continue
        codes, exact, cannot_expand = _resolve_codes(
            info,
            variable,
            coerce_values(merged[variable]),
            has_code_list=variable in resolved_code_list,
        )
        value_codes[variable] = codes
        if not exact:
            inexact.append(variable)
        if cannot_expand:
            unexpandable.append(variable)

    cells = 1
    for codes in value_codes.values():
        cells *= len(codes)

    selection = Selection(
        value_codes=value_codes,
        code_list=resolved_code_list,
        estimated_cells=cells,
        exact=not inexact,
        unexpandable_variables=tuple(unexpandable),
    )

    if max_cells is not None and cells > max_cells:
        sizes = selection.sizes()
        largest = selection.largest_variable
        breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(sizes.items(), key=lambda i: -i[1]))
        raise SelectionTooLargeError(
            f"Selection is ~{cells:,} cells (limit {max_cells:,}).\n"
            f"  Largest variable: {largest} ({sizes.get(largest or '', 0)} values). {breakdown}\n"
            "  Narrow the selection, or raise max_cells "
            "(SSB allows 800,000 per request and larger queries are batched automatically).",
            estimated_cells=cells,
            max_cells=max_cells,
            largest_variable=largest,
        )

    return selection
