from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable


LEXICON_COLUMNS = [
    "raw_name",
    "category_en",
    "category_ru",
    "color_en",
    "color_ru",
    "allowed_synonyms_ru",
    "usable_v0",
    "notes",
]


def _json_safe(value: Any) -> Any:
    """Convert pandas / numpy missing values and scalars into JSON values."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, TypeError):
            pass
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_no}: {exc}") from exc
    return records


def save_jsonl(records: Iterable[dict[str, Any]], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(_json_safe(record), ensure_ascii=False) + "\n")
    temp_path.replace(path)


def append_jsonl(record: dict[str, Any], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_json_safe(record), ensure_ascii=False) + "\n")


def humanize_raw_name(raw_name: str) -> str:
    remove = {
        "generated",
        "modified",
        "objaverse",
        "bridge",
        "baked",
        "v0",
        "v1",
        "v2",
        "dummy",
    }
    words = [word for word in raw_name.lower().split("_") if word not in remove]
    words = [word for word in words if not word.endswith("cm")]
    while words and words[-1].isdigit():
        words.pop()
    return " ".join(words)


def build_object_lexicon(
    records: Iterable[dict[str, Any]],
    existing_csv: str | Path | None = None,
) -> list[dict[str, str]]:
    """Build a unique raw-object lexicon while preserving existing annotations."""
    existing: dict[str, dict[str, str]] = {}
    if existing_csv is not None and Path(existing_csv).exists():
        with Path(existing_csv).open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                existing[row["raw_name"]] = {column: row.get(column, "") for column in LEXICON_COLUMNS}

    names: dict[str, str] = {}
    for record in records:
        for obj in record.get("objects_raw", []):
            raw_name = str(obj.get("raw_name") or "").strip()
            sim_handle = str(obj.get("sim_handle") or "").strip()
            if not raw_name:
                continue
            if sim_handle == "main_table" or raw_name.startswith("dummy_"):
                continue
            names.setdefault(raw_name, humanize_raw_name(raw_name))

    rows = []
    for raw_name in sorted(names):
        if raw_name in existing:
            rows.append(existing[raw_name])
            continue
        rows.append(
            {
                "raw_name": raw_name,
                "category_en": names[raw_name],
                "category_ru": "",
                "color_en": "",
                "color_ru": "",
                "allowed_synonyms_ru": "",
                "usable_v0": "review",
                "notes": "",
            }
        )
    return rows


def save_lexicon(rows: Iterable[dict[str, Any]], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEXICON_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in LEXICON_COLUMNS})
    temp_path.replace(path)
