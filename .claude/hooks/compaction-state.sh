#!/usr/bin/env bash
# PreCompact / PostCompact: keep docs/WORKLOG.md load-bearing.
#
# Прежняя версия отдавала hookSpecificOutput.additionalContext — поле, которого
# схема для PreCompact/PostCompact не принимает, поэтому оба хука падали и
# ничего не делали (поймано на сжатии 08.08.2026). Из поддерживаемых полей у
# этих событий есть systemMessage, и он виден и пользователю, и агенту.
#
# Но полагаться на текст-напоминание всё равно ненадёжно: перед сжатием ходов
# уже может не остаться. Поэтому PreCompact сам снимает фактический снимок
# состояния в файл — он переживает сжатие независимо от того, успел агент
# что-то дописать или нет.
set -u

event="${1:-PostCompact}"
root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
snapshot="$root/docs/COMPACTION_SNAPSHOT.md"

emit() {
  /usr/bin/python3 -c '
import json, sys
print(json.dumps({"systemMessage": sys.argv[1], "suppressOutput": True}))
' "$1"
}

if [ "$event" = "PreCompact" ]; then
  {
    echo "# Снимок состояния перед сжатием контекста"
    echo
    echo "Файл перезаписывается хуком PreCompact автоматически. Это факты на"
    echo "момент сжатия; смысл работы — в docs/WORKLOG.md."
    echo
    echo "Снят: $(date '+%Y-%m-%d %H:%M:%S %Z')"
    echo
    echo '## Ветка и последние коммиты'
    echo
    echo '```'
    git -C "$root" branch --show-current 2>/dev/null
    git -C "$root" log --oneline -5 2>/dev/null
    echo '```'
    echo
    echo '## Незакоммиченное'
    echo
    echo '```'
    git -C "$root" status --short 2>/dev/null || echo '(git недоступен)'
    echo '```'
  } > "$snapshot"
  emit "Контекст сжимается. Снимок git-состояния записан в docs/COMPACTION_SNAPSHOT.md. Живое состояние работы веди в docs/WORKLOG.md (правила — skill slava-long-sessions)."
else
  emit "Контекст был сжат. Прочитай docs/WORKLOG.md и docs/COMPACTION_SNAPSHOT.md, сверь с реальностью (git status, живы ли фоновые процессы). Разошлось — верь фактам и сразу почини WORKLOG.md."
fi
