"""An ergonomic Python wrapper around SSB's Statistikkbanken (PxWebApi v2).

Built on `pxwebpy <https://pypi.org/project/pxwebpy/>`_, which supplies the
HTTP layer, query batching, threading and response caching. This package adds
SSB-specific defaults, validation with actionable errors, and results reshaped
into tidy frames with codes and labels in separate columns.

>>> import sys; sys.path.insert(0, "..")
>>> from src import SSB, klass
>>> ssb = SSB()
>>> ssb.fetch("05810", Kjonn="0", Alder="*", time=range(2020, 2026))   # doctest: +SKIP
"""

from __future__ import annotations

from . import klass
from ._frames import ColumnSpec, Dataset, normalize_records
from ._meta import TableInfo, Variable, parse_metadata
from ._query import Selection, build_selection
from .client import SSB, PxApiLike, Table
from .errors import (
    BadSelectionError,
    ClassificationNotFoundError,
    KlassError,
    MissingDependencyError,
    RateLimitedError,
    SelectionTooLargeError,
    SsbError,
    SsbHTTPError,
    TableNotFoundError,
    UnknownValueError,
    UnknownVariableError,
)
from .klass import Classification, Klass, attach_names, attach_parent

__version__ = "0.2.0.dev0"

__all__ = [
    "SSB",
    "BadSelectionError",
    "Classification",
    "ClassificationNotFoundError",
    "ColumnSpec",
    "Dataset",
    "Klass",
    "KlassError",
    "MissingDependencyError",
    "PxApiLike",
    "RateLimitedError",
    "Selection",
    "SelectionTooLargeError",
    "SsbError",
    "SsbHTTPError",
    "Table",
    "TableInfo",
    "TableNotFoundError",
    "UnknownValueError",
    "UnknownVariableError",
    "Variable",
    "__version__",
    "attach_names",
    "attach_parent",
    "build_selection",
    "klass",
    "normalize_records",
    "parse_metadata",
]
