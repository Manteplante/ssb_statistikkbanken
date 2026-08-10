"""Turning pxwebpy records into an analysis-ready frame.

pxwebpy hands back a list of row dicts keyed by *dimension label in the current
language*, with the measured number under ``"value"``. Everything here is plain
Python so that ``to_records()`` is genuinely useful and polars is only imported
if someone actually asks for it.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from ._meta import TableInfo
from .config import CODE_COLUMN_SUFFIX, CODE_VALUE_SEPARATOR, VALUE_COLUMN
from .errors import MissingDependencyError

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd
    import polars as pl

__all__ = ["ColumnSpec", "Dataset", "normalize_records"]

Labels = Literal["both", "label", "code"]
Columns = Literal["code", "label"]

#: What `labels=` means in pxwebpy's vocabulary.
SHOW_FOR_LABELS: dict[str, str] = {"both": "code_value", "label": "value", "code": "code"}

_MONTHLY_RE = re.compile(r"^(\d{4})M(\d{1,2})$")
_QUARTERLY_RE = re.compile(r"^(\d{4})[KQ](\d)$")
_ANNUAL_RE = re.compile(r"^\d{4}$")


@dataclass(frozen=True)
class ColumnSpec:
    """The shape of the normalized rows: names, order and how to type them."""

    columns: tuple[str, ...]
    value_column: str = VALUE_COLUMN
    integer_value: bool = True
    year_column: str | None = None
    date_column: str | None = None
    dimension_columns: tuple[str, ...] = ()
    code_columns: tuple[str, ...] = ()


def _label_to_code(info: TableInfo) -> dict[str, str]:
    """Map the record keys pxwebpy produces (dimension labels) back onto codes."""
    mapping: dict[str, str] = {}
    duplicates: list[str] = []
    for code in info.order:
        label = info.variables[code].label
        if label in mapping:
            duplicates.append(label)
        mapping[label] = code
    if duplicates:
        warnings.warn(
            f"Table {info.table_id} has variables sharing a label ({', '.join(duplicates)}); "
            "those columns cannot be told apart and one will be missing.",
            UserWarning,
            stacklevel=3,
        )
    return mapping


def _split_code_value(cell: Any) -> tuple[str | None, Any]:
    """Split ``"0301: Oslo"`` into ``("0301", "Oslo")``.

    Splits on the first separator only, and keeps the whole string as the label
    if there is none, rather than corrupting both columns.
    """
    if not isinstance(cell, str):
        return None, cell
    code, sep, label = cell.partition(CODE_VALUE_SEPARATOR)
    if not sep:
        return None, cell
    return code, label


def _derive_year(code: Any) -> int | None:
    if isinstance(code, str) and _ANNUAL_RE.match(code):
        return int(code)
    return None


def _derive_date(code: Any) -> str | None:
    """Map a period code onto the ISO date its period starts on."""
    if not isinstance(code, str):
        return None
    if (m := _MONTHLY_RE.match(code)) is not None:
        return f"{m.group(1)}-{int(m.group(2)):02d}-01"
    if (m := _QUARTERLY_RE.match(code)) is not None:
        return f"{m.group(1)}-{(int(m.group(2)) - 1) * 3 + 1:02d}-01"
    return None


def normalize_records(
    records: list[dict[str, Any]],
    info: TableInfo,
    *,
    labels: Labels = "both",
    columns: Columns = "code",
) -> tuple[list[dict[str, Any]], ColumnSpec]:
    """Rename, split and order the raw records; derive a time column if we can.

    With ``labels="both"`` every dimension becomes two adjacent columns -- the
    human label and a ``*_code`` sibling -- which is what makes joining against
    KLASS or a GeoJSON possible without stripping codes out of strings.
    """
    if labels not in SHOW_FOR_LABELS:
        raise ValueError(f"labels must be one of {sorted(SHOW_FOR_LABELS)}, got {labels!r}.")
    if columns not in ("code", "label"):
        raise ValueError(f"columns must be 'code' or 'label', got {columns!r}.")

    label_to_code = _label_to_code(info)

    # Which record keys are present, in SSB's dimension order. Eliminated
    # variables never appear in the response, so we work off the data.
    seen = [k for k in (records[0] if records else {}) if k != VALUE_COLUMN]
    unknown = [k for k in seen if k not in label_to_code]
    if unknown:
        warnings.warn(
            f"Unrecognised columns in the response for table {info.table_id}: "
            f"{', '.join(unknown)}. They are kept under their original names.",
            UserWarning,
            stacklevel=2,
        )

    code_by_key = {key: label_to_code.get(key) for key in seen}

    def _dimension_position(key: str) -> int:
        """Unrecognised columns sort to the end, after every known dimension."""
        code = code_by_key[key]
        return info.order.index(code) if code else len(info.order)

    ordered_keys = sorted(seen, key=_dimension_position)

    def out_name(key: str) -> str:
        code = code_by_key[key]
        if code is None:
            return key
        return code if columns == "code" else info.variables[code].label

    names = {key: out_name(key) for key in ordered_keys}

    # Which column carries the raw period code, for deriving year/date.
    time_key = next((k for k in ordered_keys if code_by_key[k] == info.time_variable), None)

    dimension_columns: list[str] = []
    code_columns: list[str] = []
    column_order: list[str] = []
    for key in ordered_keys:
        name = names[key]
        dimension_columns.append(name)
        column_order.append(name)
        if labels == "both":
            code_columns.append(name + CODE_COLUMN_SUFFIX)
            column_order.append(name + CODE_COLUMN_SUFFIX)

    rows: list[dict[str, Any]] = []
    for record in records:
        row: dict[str, Any] = {}
        for key in ordered_keys:
            name = names[key]
            cell = record.get(key)
            if labels == "both":
                code, label = _split_code_value(cell)
                row[name] = label
                row[name + CODE_COLUMN_SUFFIX] = code
            else:
                row[name] = cell
        row[VALUE_COLUMN] = record.get(VALUE_COLUMN)
        rows.append(row)

    # A period column is only worth deriving when every row parses.
    year_column: str | None = None
    date_column: str | None = None
    if time_key is not None and rows:
        time_col = names[time_key] + (CODE_COLUMN_SUFFIX if labels == "both" else "")
        raw = [row.get(time_col) for row in rows]
        if all(_derive_year(v) is not None for v in raw):
            year_column = "year"
            for row in rows:
                row["year"] = _derive_year(row.get(time_col))
        elif all(_derive_date(v) is not None for v in raw):
            date_column = "date"
            for row in rows:
                row["date"] = _derive_date(row.get(time_col))

    derived = [c for c in (year_column, date_column) if c]
    spec = ColumnSpec(
        columns=tuple(column_order + derived + [VALUE_COLUMN]),
        value_column=VALUE_COLUMN,
        integer_value=info.decimals == 0,
        year_column=year_column,
        date_column=date_column,
        dimension_columns=tuple(dimension_columns),
        code_columns=tuple(code_columns),
    )
    # Re-emit rows in the declared column order so to_records() is ordered too.
    rows = [{name: row.get(name) for name in spec.columns} for row in rows]
    return rows, spec


@dataclass(frozen=True)
class Dataset:
    """A fetched result, convertible to whichever frame you prefer."""

    rows: list[dict[str, Any]]
    spec: ColumnSpec
    info: TableInfo
    #: The exact value codes that were sent -- handy when a result surprises you.
    query: dict[str, list[str]] = field(default_factory=dict)
    code_list: dict[str, str] = field(default_factory=dict)

    def _use_integer_values(self) -> bool:
        """Whether the value column really can be held as an integer.

        SSB's ``decimals`` is a *table-level* hint, but a table can mix units
        across ContentsCode -- 13902 reports ``decimals=0`` while pairing
        building counts with road length in km (0.2, 0.7). Trusting the hint
        made pandas raise and made polars silently truncate 0.2 to 0, so the
        data gets the final say.
        """
        if not self.spec.integer_value:
            return False
        return not any(
            isinstance(row.get(self.spec.value_column), float)
            and not row[self.spec.value_column].is_integer()
            for row in self.rows
        )

    def __len__(self) -> int:
        return len(self.rows)

    def __repr__(self) -> str:
        return (
            f"Dataset({self.info.table_id!r}, {len(self.rows)} rows, "
            f"columns={list(self.spec.columns)})"
        )

    def to_records(self) -> list[dict[str, Any]]:
        """The normalized rows as plain dicts -- bring your own dataframe."""
        return [dict(row) for row in self.rows]

    def to_pandas(self, *, categorical: bool = False) -> pd.DataFrame:
        """A tidy long pandas frame with nullable numeric dtypes.

        ``categorical=True`` casts the dimension columns to ``category``. It is
        opt-in because categorical dtypes change groupby and plotting behaviour
        in ways that surprise people mid-analysis.
        """
        import pandas as pd

        frame = pd.DataFrame(self.rows, columns=list(self.spec.columns))

        value = pd.to_numeric(frame[self.spec.value_column], errors="coerce")
        frame[self.spec.value_column] = value.astype(
            "Int64" if self._use_integer_values() else "Float64"
        )

        if self.spec.year_column:
            frame[self.spec.year_column] = pd.to_numeric(
                frame[self.spec.year_column], errors="coerce"
            ).astype("Int16")
        if self.spec.date_column:
            frame[self.spec.date_column] = pd.to_datetime(
                frame[self.spec.date_column], errors="coerce"
            )
        if categorical:
            for column in self.spec.dimension_columns:
                frame[column] = frame[column].astype("category")

        return frame

    def to_polars(self) -> pl.DataFrame:
        """A polars frame, built straight from the records (no pandas round-trip)."""
        try:
            import polars as pl
        except ModuleNotFoundError as exc:
            raise MissingDependencyError(
                "polars is required for .to_polars(). Install it with:\n"
                "  uv add polars\n"
                "or use .to_pandas() / .to_records() instead."
            ) from exc

        schema: dict[str, Any] = {
            self.spec.value_column: pl.Int64 if self._use_integer_values() else pl.Float64
        }
        if self.spec.year_column:
            schema[self.spec.year_column] = pl.Int16

        frame = pl.DataFrame(
            self.rows or [dict.fromkeys(self.spec.columns)],
            schema_overrides=schema,
            infer_schema_length=None,
        )
        if not self.rows:
            frame = frame.clear()
        if self.spec.date_column:
            frame = frame.with_columns(
                pl.col(self.spec.date_column).str.to_date("%Y-%m-%d", strict=False)
            )
        return frame.select(list(self.spec.columns))
