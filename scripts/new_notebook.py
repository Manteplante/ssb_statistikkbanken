"""Scaffold a new notebook in eda/, wired to this repo's wrapper and kernel.

Used by `make notebook name=<name> [dir=<subdir>]` -- see the Makefile.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDA = ROOT / "eda"

KERNEL_NAME = "ssb-statistikkbanken"
KERNEL_DISPLAY_NAME = "ssb-statistikkbanken (.venv)"

_INVALID = re.compile(r"[^a-zA-Z0-9_-]+")


def _slugify(name: str) -> str:
    slug = _INVALID.sub("_", name.strip()).strip("_")
    if not slug:
        raise ValueError(f"{name!r} has no usable characters for a filename.")
    return slug


def _title(slug: str) -> str:
    return slug.replace("_", " ").replace("-", " ").strip().capitalize()


def build_notebook(title: str, depth: int) -> dict:
    """A notebook with the same sys.path + import header every eda/ notebook uses."""
    path_up = "/".join([".."] * depth)
    header = [
        "import sys\n",
        f'sys.path.insert(0, "{path_up}")\n',
        "\n",
        "import pandas as pd\n",
        "\n",
        "from src import SSB, klass\n",
        "\n",
        "ssb = SSB()\n",
        "ssb\n",
    ]
    return {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": [f"# {title}\n"]},
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": header,
            },
        ],
        "metadata": {
            "kernelspec": {
                "display_name": KERNEL_DISPLAY_NAME,
                "language": "python",
                "name": KERNEL_NAME,
            },
            "language_info": {"name": "python", "pygments_lexer": "ipython3"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="Notebook name, e.g. population_trends")
    parser.add_argument(
        "--dir", default=None, help="Subfolder under eda/ to place it in (created if missing)"
    )
    args = parser.parse_args()

    slug = _slugify(args.name)
    target_dir = EDA / args.dir if args.dir else EDA
    target = target_dir / f"{slug}.ipynb"

    if target.exists():
        sys.exit(f"{target.relative_to(ROOT)} already exists -- pick a different name.")

    target_dir.mkdir(parents=True, exist_ok=True)
    depth = len(target.relative_to(ROOT).parts) - 1  # "..".repeat to reach the repo root
    notebook = build_notebook(_title(slug), depth)
    target.write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"created {target.relative_to(ROOT)}")
    print(f"  kernel: {KERNEL_DISPLAY_NAME} (run `make kernel` first if it's not registered yet)")


if __name__ == "__main__":
    main()
