#!/usr/bin/env python3
"""Оставить в steps.jsonl только последний прогон эпизода.

Тот же дефект, что чинил `clean_stale_frames.py`, но в другом артефакте:
`run_episode` открывал `steps.jsonl` на дозапись, поэтому пересбор эпизода
дописывал новые шаги к старым вместо замены. Лог тогда содержит два эпизода
подряд — видно по тому, что нумерация шагов начинается заново.

Это ломает всё, что читает траекторию: длину эпизода, максимальный подъём цели,
контакты. Метрики из `rollout_annotations.jsonl` не затронуты — они писались по
живым данным прогона, — но перерасчёт меток по такому логу дал бы смесь двух
попыток.

Починено в `storage.ensure_episode_dirs` (файл удаляется перед новым эпизодом);
этот скрипт приводит в порядок то, что собрано раньше.

    python3 scripts/clean_stale_steps.py            # только показать
    python3 scripts/clean_stale_steps.py --delete   # переписать файлы
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def last_run(lines: list[str]) -> list[str]:
    """Строки последнего прогона: от последнего шага с номером 1 и до конца."""
    start = 0
    for index, line in enumerate(lines):
        try:
            if json.loads(line).get("step") == 1:
                start = index
        except json.JSONDecodeError:
            continue
    return lines[start:]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", default="pilot_v0")
    parser.add_argument("--delete", action="store_true")
    args = parser.parse_args()

    root = PROJECT_ROOT / "rollouts" / "final" / args.pool / "episodes"
    fixed = removed = 0
    for episode in sorted(p for p in root.iterdir() if p.is_dir()):
        path = episode / "steps.jsonl"
        if not path.exists():
            continue
        lines = [l for l in path.read_text().splitlines() if l.strip()]
        kept = last_run(lines)
        if len(kept) == len(lines):
            continue
        fixed += 1
        removed += len(lines) - len(kept)
        print(f"{episode.name}: {len(lines)} строк → {len(kept)}")
        if args.delete:
            path.write_text("\n".join(kept) + "\n")
    verb = "удалено" if args.delete else "нашлось (запустите с --delete)"
    print(f"\n{fixed} эпизодов, {removed} лишних строк {verb}")


if __name__ == "__main__":
    main()
