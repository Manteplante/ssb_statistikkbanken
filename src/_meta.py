"""Table metadata: parsing SSB's json-stat2 metadata into something navigable.

This is deliberately I/O-free -- :func:`parse_metadata` takes the already
fetched JSON. The client owns the network call and the caching.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from .errors import UnknownVariableError, suggest

__all__ = ["TableInfo", "Variable", "parse_metadata"]

_ANNUAL_RE = re.compile(r"^\d{4}$")
_MONTHLY_RE = re.compile(r"^(\d{4})M(\d{2})$")
_QUARTERLY_RE = re.compile(r"^(\d{4})[KQ](\d)$")


@dataclass(frozen=True)
class Variable:
    """One dimension of a table, with its value codes in API order."""

    code: str
    label: str
    values: dict[str, str]
    elimination: bool
    code_lists: list[dict[str, str]] = field(default_factory=list)
    show: str | None = None

    @property
    def codes(self) -> list[str]:
        """Value codes, in the order SSB presents them."""
        return list(self.values)

    @property
    def labels(self) -> list[str]:
        """Value labels, in the order SSB presents them."""
        return list(self.values.values())

    @property
    def n_values(self) -> int:
        return len(self.values)

    @property
    def mandatory(self) -> bool:
        """True when the variable cannot be eliminated and must be selected."""
        return not self.elimination

    def resolve(self, value: str) -> str | None:
        """Map a code or a label onto its code, case-insensitively."""
        needle = value.casefold()
        for code in self.values:
            if code.casefold() == needle:
                return code
        for code, label in self.values.items():
            if label.casefold() == needle:
                return code
        return None

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        head = ", ".join(f"{c}" for c in self.codes[:4])
        more = ", ..." if self.n_values > 4 else ""
        return (
            f"Variable({self.code!r}, label={self.label!r}, {self.n_values} values: {head}{more})"
        )


@dataclass(frozen=True)
class TableInfo:
    """Everything worth knowing about a table, parsed once and cached.

    Renders as a card in Jupyter; ``info["Alder"]`` gets you a :class:`Variable`.
    """

    table_id: str
    label: str
    source: str | None
    updated: str | None
    notes: list[str]
    order: list[str]
    variables: dict[str, Variable]
    decimals: int
    time_variable: str | None
    contents_variable: str | None

    # -- lookup --------------------------------------------------------------

    def __getitem__(self, name: str) -> Variable:
        return self.variables[self.require(name)]

    def __contains__(self, name: str) -> bool:
        return self.resolve(name) is not None

    def __iter__(self) -> Iterator[str]:
        return iter(self.order)

    @property
    def codes(self) -> list[str]:
        """Variable codes, in the order SSB presents them."""
        return list(self.order)

    def resolve(self, name: str) -> str | None:
        """Map a variable code or label onto its code, case-insensitively."""
        needle = str(name).casefold()
        for code in self.order:
            if code.casefold() == needle:
                return code
        for code in self.order:
            if self.variables[code].label.casefold() == needle:
                return code
        return None

    def require(self, name: str) -> str:
        """Like :meth:`resolve`, but raises with a did-you-mean instead of None."""
        code = self.resolve(name)
        if code is not None:
            return code

        candidates = self.order + [v.label for v in self.variables.values()]
        hits = suggest(str(name), candidates)
        lines = [f"{name!r} is not a variable in table {self.table_id}."]
        resolved = [c for c in (self.resolve(h) for h in hits) if c is not None]
        if resolved:
            named = dict.fromkeys(f"{c} ({self.variables[c].label})" for c in resolved)
            lines.append(f"  Did you mean: {', '.join(named)}?")
        lines.append(f"  Available: {', '.join(self.order)}")
        lines.append(f'  Tip: ssb.variables("{self.table_id}")')
        raise UnknownVariableError(
            "\n".join(lines), variable=str(name), available=self.order, suggestions=hits
        )

    # -- derived -------------------------------------------------------------

    @property
    def mandatory(self) -> list[str]:
        """Variables that must appear in a selection."""
        return [code for code in self.order if self.variables[code].mandatory]

    @property
    def time_unit(self) -> str | None:
        """``"annual"``, ``"monthly"``, ``"quarterly"`` or None, from the time codes."""
        if self.time_variable is None:
            return None
        codes = self.variables[self.time_variable].codes
        if not codes:
            return None
        if all(_ANNUAL_RE.match(c) for c in codes):
            return "annual"
        if all(_MONTHLY_RE.match(c) for c in codes):
            return "monthly"
        if all(_QUARTERLY_RE.match(c) for c in codes):
            return "quarterly"
        return None

    @property
    def periods(self) -> tuple[str, str] | None:
        """First and last time code, or None when the table has no time dimension."""
        if self.time_variable is None:
            return None
        codes = self.variables[self.time_variable].codes
        return (codes[0], codes[-1]) if codes else None

    # -- display -------------------------------------------------------------

    def __repr__(self) -> str:
        period = f", {self.periods[0]}-{self.periods[1]}" if self.periods else ""
        return (
            f"TableInfo({self.table_id!r}, {len(self.order)} variables{period})\n"
            + f"  {self.label}\n"
            + "\n".join(
                f"  {code:<16} {v.label:<24} {v.n_values:>5} values"
                + ("  (mandatory)" if v.mandatory else "")
                for code, v in ((c, self.variables[c]) for c in self.order)
            )
        )

    def _repr_html_(self) -> str:
        def esc(value: Any) -> str:
            return html.escape(str(value))

        rows = []
        for code in self.order:
            var = self.variables[code]
            preview = "; ".join(f"{c}: {label}" for c, label in list(var.values.items())[:4])
            if var.n_values > 4:
                preview += f"; … (+{var.n_values - 4})"
            rows.append(
                "<tr>"
                f"<td style='padding:2px 10px 2px 0'><code>{esc(code)}</code></td>"
                f"<td style='padding:2px 10px 2px 0'>{esc(var.label)}</td>"
                f"<td style='padding:2px 10px 2px 0;text-align:right'>{var.n_values}</td>"
                f"<td style='padding:2px 10px 2px 0'>{'yes' if var.mandatory else ''}</td>"
                f"<td style='padding:2px 0;opacity:.75'>{esc(preview)}</td>"
                "</tr>"
            )

        meta = [f"updated {esc(self.updated)}" if self.updated else "", esc(self.source or "")]
        if self.periods:
            meta.insert(0, f"{esc(self.periods[0])}–{esc(self.periods[1])}")
        notes = (
            f"<div style='margin-top:6px;opacity:.75'>{esc(' '.join(self.notes))}</div>"
            if self.notes
            else ""
        )

        return (
            "<div style='font-family:system-ui,sans-serif;font-size:13px;line-height:1.45'>"
            f"<div style='font-weight:600'>{esc(self.label)}</div>"
            f"<div style='opacity:.7'>{esc(' · '.join(m for m in meta if m))}</div>"
            "<table style='margin-top:8px;border-collapse:collapse'>"
            "<tr style='text-align:left;opacity:.7'>"
            "<th style='padding-right:10px'>variable</th><th style='padding-right:10px'>label</th>"
            "<th style='padding-right:10px'>values</th>"
            "<th style='padding-right:10px'>mandatory</th>"
            "<th>examples</th></tr>"
            + "".join(rows)
            + "</table>"
            + notes
            + f"<div style='margin-top:6px;opacity:.6'>ssb.values(\"{esc(self.table_id)}\", "
            "&lt;variable&gt;) lists every value code.</div>"
            "</div>"
        )


def parse_metadata(table_id: str, metadata: dict[str, Any]) -> TableInfo:
    """Turn SSB's ``/tables/{id}/metadata`` response into a :class:`TableInfo`.

    Uses ``category.index`` to preserve SSB's own ordering (which json-stat2
    does not guarantee from the label dict alone) and ``role`` to identify the
    time and contents dimensions without hardcoding ``Tid``/``ContentsCode``.
    """
    dimensions: dict[str, Any] = metadata.get("dimension", {})
    order: list[str] = list(metadata.get("id") or dimensions.keys())

    variables: dict[str, Variable] = {}
    for code in order:
        dim = dimensions.get(code, {})
        category = dim.get("category", {})
        labels: dict[str, str] = dict(category.get("label", {}))
        index: dict[str, int] = category.get("index", {})
        if index:
            labels = {k: labels[k] for k in sorted(labels, key=lambda k: index.get(k, 0))}

        extension = dim.get("extension", {})
        # SSB spells the key "codelists"; the PxWeb spec (and SCB) use "codeLists".
        raw_code_lists = extension.get("codelists") or extension.get("codeLists") or []
        variables[code] = Variable(
            code=code,
            label=dim.get("label", code),
            values=labels,
            elimination=bool(extension.get("elimination", False)),
            code_lists=[
                {"id": cl["id"], "label": cl.get("label", ""), "type": cl.get("type", "")}
                for cl in raw_code_lists
                if "id" in cl
            ],
            show=extension.get("show"),
        )

    role = metadata.get("role") or {}
    time_variable = next((c for c in role.get("time", []) if c in variables), None)
    contents_variable = next((c for c in role.get("metric", []) if c in variables), None)

    notes = metadata.get("note") or []
    if isinstance(notes, str):
        notes = [notes]

    return TableInfo(
        table_id=table_id,
        label=metadata.get("label", table_id),
        source=metadata.get("source"),
        updated=metadata.get("updated"),
        notes=list(notes),
        order=order,
        variables=variables,
        decimals=int(metadata.get("extension", {}).get("px", {}).get("decimals", 0) or 0),
        time_variable=time_variable,
        contents_variable=contents_variable,
    )
