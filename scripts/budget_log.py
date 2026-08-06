#!/usr/bin/env python3
"""Measure what a unit of work actually cost, from the session transcript.

Pacing rules are only as good as the estimate behind them, and "how much of the
window does this kind of task eat" is not something to guess twice. Claude Code
writes every API response's `usage` into the session transcript
(~/.claude/projects/<project>/<session>.jsonl), so consumption and context size
can be read locally — no API key, and unlike the status line this works in every
frontend.

    python3 scripts/budget_log.py                       # current totals
    python3 scripts/budget_log.py --mark "починили X"    # append a row to docs/BUDGET_LOG.md

Each mark records the delta since the previous one: tokens spent, API calls, and
the context size at that moment — context matters because every call re-sends
the window, so the same task costs more late in a session than early.

What this does NOT give: the plan's 5-hour/weekly percentages. Those come only
from the status-line payload (~/.claude/usage-cache.json). When that cache is
missing, treat these token counts as the pacing signal and stay conservative.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG = PROJECT_ROOT / "docs" / "BUDGET_LOG.md"
HEADER = (
    "# Журнал расхода бюджета\n\n"
    "Эмпирика для порогов из skill `slava-budget-pacing`: сколько на самом деле\n"
    "стоит единица работы. Заполняется `python3 scripts/budget_log.py --mark \"...\"`.\n\n"
    "`Контекст` — размер окна на момент записи: одна и та же задача в конце\n"
    "длинной сессии дороже, чем в начале, потому что окно пересылается целиком.\n\n"
    "| Время | Единица работы | Токенов | Вызовов | Контекст | Мин |\n"
    "| --- | --- | --- | --- | --- | --- |\n"
)


def transcript_path() -> Path | None:
    """Newest transcript for this project directory.

    The directory name is the project path with every non-alphanumeric
    character replaced by a dash — note that underscores are replaced too, so
    `SLAVA_dev` becomes `SLAVA-dev`. Falling back to a scan keeps this working
    if that convention ever changes.
    """
    projects = Path.home() / ".claude" / "projects"
    if not projects.is_dir():
        return None
    slug = "".join(c if c.isalnum() else "-" for c in str(PROJECT_ROOT))
    candidates = [projects / slug]
    if not candidates[0].is_dir():
        candidates = [d for d in projects.iterdir() if d.is_dir() and d.name.endswith(slug.split("-")[-1])]
    files = [f for d in candidates if d.is_dir() for f in d.glob("*.jsonl")]
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)


def totals(path: Path) -> dict:
    """Cumulative spend and the most recent context size.

    Context is the last response's input side (fresh input + cache reads + cache
    writes) — that is what the model was actually carrying at that point.
    """
    spent = calls = context = 0
    for line in path.read_text(errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        calls += 1
        window = (
            usage.get("input_tokens", 0)
            + usage.get("cache_read_input_tokens", 0)
            + usage.get("cache_creation_input_tokens", 0)
        )
        # Cache reads are the bulk of every call and are what makes a long
        # session expensive, so they belong in "spent" — this is a consumption
        # estimate, not a billing figure.
        spent += window + usage.get("output_tokens", 0)
        context = window
    return {"spent": spent, "calls": calls, "context": context}


def previous_mark() -> dict:
    state = PROJECT_ROOT / "docs" / ".budget_log_state.json"
    if state.exists():
        try:
            return json.loads(state.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def save_mark(data: dict) -> None:
    (PROJECT_ROOT / "docs" / ".budget_log_state.json").write_text(json.dumps(data))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mark", help="Название завершённой единицы работы")
    args = parser.parse_args()

    path = transcript_path()
    if path is None:
        raise SystemExit("Транскрипт не найден — считать нечего.")
    now = totals(path)

    if not args.mark:
        print(f"транскрипт: {path.name}")
        print(f"израсходовано с начала сессии: {now['spent'] / 1000:.0f}k токенов "
              f"за {now['calls']} вызовов")
        print(f"контекст сейчас: {now['context'] / 1000:.0f}k")
        return

    before = previous_mark()
    delta_spent = now["spent"] - before.get("spent", 0)
    delta_calls = now["calls"] - before.get("calls", 0)
    minutes = int((time.time() - before.get("at", time.time())) / 60)

    if not LOG.exists():
        LOG.write_text(HEADER)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(
            f"| {time.strftime('%d.%m %H:%M')} | {args.mark} | "
            f"{delta_spent / 1000:.0f}k | {delta_calls} | "
            f"{now['context'] / 1000:.0f}k | {minutes} |\n"
        )
    save_mark({"spent": now["spent"], "calls": now["calls"], "at": time.time()})
    print(f"записано: {args.mark} — {delta_spent / 1000:.0f}k токенов, "
          f"{delta_calls} вызовов, контекст {now['context'] / 1000:.0f}k")


if __name__ == "__main__":
    main()
