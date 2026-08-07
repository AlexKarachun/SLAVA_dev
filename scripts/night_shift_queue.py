#!/usr/bin/env python3
"""Отметить строку очереди автономной смены выполненной или заблокированной.

Отдельным скриптом, а не sed'ом в оркестраторе: очередь — это состояние смены,
и порча её разметки посреди ночи стоит дороже, чем двадцать строк питона.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

QUEUE = Path(__file__).resolve().parents[1] / "docs" / "NIGHT_QUEUE.md"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--done", type=int)
    parser.add_argument("--blocked", type=int)
    parser.add_argument("--reason", default="")
    args = parser.parse_args()

    number = args.done or args.blocked
    if not number:
        raise SystemExit("нужен --done N или --blocked N (номер строки)")

    lines = QUEUE.read_text(encoding="utf-8").splitlines()
    index = number - 1
    if not (0 <= index < len(lines)) or not lines[index].startswith("- [ ] "):
        raise SystemExit(f"строка {number} не является незакрытым пунктом очереди")

    stamp = time.strftime("%d.%m %H:%M")
    if args.done:
        lines[index] = lines[index].replace("- [ ] ", "- [x] ", 1) + f"  _(готово {stamp})_"
    else:
        lines[index] = (
            lines[index].replace("- [ ] ", "- [!] ", 1)
            + f"  _(заблокировано {stamp}: {args.reason})_"
        )
    QUEUE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(lines[index])


if __name__ == "__main__":
    main()
