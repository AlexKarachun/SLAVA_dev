#!/usr/bin/env python3
"""Validate one or more SLAVA inventory JSONL files against canonical schema v1."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_inventory.io_utils import load_jsonl  # noqa: E402
from slava_inventory.schema import validate_inventory  # noqa: E402


DEFAULT_FILES = [
    PROJECT_ROOT / "data" / "libero_inventory.jsonl",
    PROJECT_ROOT / "data" / "simpler_inventory.jsonl",
    PROJECT_ROOT / "data" / "task_inventory.jsonl",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, nargs="*", default=DEFAULT_FILES)
    args = parser.parse_args()
    for path in args.files:
        records = load_jsonl(path)
        validate_inventory(records)
        print(f"OK: {path} ({len(records)} records)")


if __name__ == "__main__":
    main()
