"""Re-record the offline test fixtures from the live SSB and KLASS APIs.

Run this when SSB changes something and the offline tests start lying:

    uv run python tests/fixtures/refresh.py

It is deliberately a script rather than a test, so recording is always an
explicit act.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

HERE = Path(__file__).parent
PXWEB = HERE / "pxweb"
KLASS = HERE / "klass"

PXWEB_BASE = "https://data.ssb.no/api/pxwebapi/v2"
KLASS_BASE = "https://data.ssb.no/api/klass/v1"

#: The data selections the offline tests assert against.
DATA_QUERIES: dict[str, dict[str, list[str]]] = {
    "05810": {
        "Kjonn": ["0"],
        "Alder": ["999B", "00-06", "07-15", "16-44", "45-66", "67-79", "80+"],
        "ContentsCode": ["Personer"],
        "Tid": ["2020", "2021", "2022", "2023", "2024", "2025"],
    },
    "11342": {
        "Region": ["03", "11", "50", "56"],
        "ContentsCode": ["Folkemengde"],
        "Tid": ["2025"],
    },
    # Mixed units under one ContentsCode: building counts (integers) alongside
    # road length in km (0.2, 0.7), while the table reports decimals=0. Guards
    # the regression where that hint was trusted over the actual values.
    "13902": {
        "Region": ["0301"],
        "Naturfare": ["01_flom20", "08_skredfare100"],
        "ContentsCode": ["Bygninger", "Veger"],
        "Tid": ["2026"],
    },
}

METADATA_TABLES = ["05810", "11342", "07459", "13902"]


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {path.relative_to(HERE.parent.parent)}")


def _get(url: str, **params: object) -> object:
    response = requests.get(url, params=params, headers={"Accept": "application/json"}, timeout=60)
    response.raise_for_status()
    return response.json()


def main() -> None:
    for table_id in METADATA_TABLES:
        _write(
            PXWEB / f"{table_id}_metadata.json",
            _get(f"{PXWEB_BASE}/tables/{table_id}/metadata", lang="no"),
        )

    for table_id, value_codes in DATA_QUERIES.items():
        query = {
            "selection": [
                {"variableCode": variable, "valueCodes": codes}
                for variable, codes in value_codes.items()
            ]
        }
        response = requests.post(
            f"{PXWEB_BASE}/tables/{table_id}/data",
            params={"lang": "no", "outputFormat": "json-stat2"},
            json=query,
            timeout=60,
        )
        response.raise_for_status()
        _write(PXWEB / f"{table_id}_data.json", response.json())

    _write(
        PXWEB / "search_befolkning.json",
        _get(f"{PXWEB_BASE}/tables", lang="no", query="befolkning", pageSize=5),
    )
    _write(PXWEB / "config.json", _get(f"{PXWEB_BASE}/config"))

    for classification in (104, 131):
        _write(
            KLASS / f"{classification}_codesAt_2025.json",
            _get(
                f"{KLASS_BASE}/classifications/{classification}/codesAt",
                date="2025-01-01",
                language="nb",
            ),
        )
    _write(
        KLASS / "131_correspondsAt_104_2025.json",
        _get(
            f"{KLASS_BASE}/classifications/131/correspondsAt",
            targetClassificationId=104,
            date="2025-01-01",
            language="nb",
        ),
    )


if __name__ == "__main__":
    main()
