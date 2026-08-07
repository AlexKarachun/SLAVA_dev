#!/usr/bin/env python3
"""Слить пофайловые выгрузки параллельного сбора в один инвентарь и проверить квоты.

Параллельный сбор пишет по каталогу на (сьют × задача), потому что
`collect_libero.py` держит один inventory-файл на процесс и иначе они затирали
бы друг друга. Этот скрипт сводит их вместе и сразу отвечает на вопрос, ради
которого сбор и затевался: хватает ли запаса по каждой квоте `task.md`.

    python3 scripts/merge_full_set.py --parts data/incoming --output data/full_set
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# task.md, «Квоты v0»: абсолютные счётчики для 20 сцен. Читаем как доли —
# это НАШЕ решение, см. docs/FULL_SET_PLAN.md.
QUOTA_SHARE = {
    "spatial": 8 / 20,
    "pick_with_distractors": 5 / 20,
    "container": 4 / 20,
    "surface": 3 / 20,
}

# Пространственные отношения в LIBERO живут в РЕФЕРЕНЦИИ («миска между тарелкой
# и формочкой»), а не в предикате цели: предикатов left_of/next_to там нет
# вовсе. Поэтому квота считается по тексту инструкции.
SPATIAL_RE = re.compile(
    r"\b(left|right|between|next to|front|back|behind|on top|middle|center|centre)\b",
    re.I,
)


def categories(row: dict) -> set[str]:
    out: set[str] = set()
    text = row.get("canonical_en") or ""
    preds = [p[0] if isinstance(p, list) else p for p in (row.get("success_predicates") or [])]
    if SPATIAL_RE.search(text):
        out.add("spatial")
    if "in" in preds:
        out.add("container")
    if "on" in preds:
        out.add("surface")
    if len(row.get("objects_raw") or []) >= 3:
        out.add("pick_with_distractors")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", type=Path, required=True, help="каталог с подкаталогами частей")
    ap.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "full_set")
    ap.add_argument("--target", type=int, default=150, help="сколько сцен планируем отобрать")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    rows: dict[str, dict] = {}
    for part in sorted(args.parts.iterdir()):
        inv = part / "libero_inventory.jsonl"
        if not inv.is_file():
            continue
        for line in inv.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["task_uid"]] = r  # дубликаты по uid невозможны, но пусть

    print(f"собрано сцен: {len(rows)}")
    by_suite = collections.Counter(u.split("__")[0] for u in rows)
    for k, v in sorted(by_suite.items()):
        print(f"  {k:16s} {v}")
    print(f"уникальных формулировок: {len({r.get('canonical_en') for r in rows.values()})}")

    cat = collections.Counter()
    for r in rows.values():
        for c in categories(r):
            cat[c] += 1
    print(f"\nЗАПАС ПО КВОТАМ (цель — отобрать {args.target} сцен):")
    worst = None
    for name, share in QUOTA_SHARE.items():
        need = round(args.target * share)
        have = cat[name]
        ratio = have / need if need else float("inf")
        worst = ratio if worst is None else min(worst, ratio)
        mark = "OK" if ratio >= 4 else ("тесно" if ratio >= 2 else "МАЛО")
        print(f"  {name:22s} нужно {need:3d}, есть {have:4d}  ->  x{ratio:.1f}  {mark}")
    print(f"\nминимальный запас по всем квотам: x{worst:.1f}")

    if not args.write:
        print("\nсухой прогон — ничего не записано, добавьте --write")
        return

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "images" / "libero").mkdir(parents=True, exist_ok=True)
    moved = 0
    for part in sorted(args.parts.iterdir()):
        src = part / "images" / "libero"
        if not src.is_dir():
            continue
        for png in src.glob("*.png"):
            shutil.copy2(png, args.output / "images" / "libero" / png.name)
            moved += 1
    out = args.output / "libero_inventory.jsonl"
    out.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows.values()) + "\n",
        encoding="utf-8",
    )
    print(f"\nзаписано: {out} ({len(rows)} сцен), картинок скопировано {moved}")


if __name__ == "__main__":
    main()
