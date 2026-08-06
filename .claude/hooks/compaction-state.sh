#!/usr/bin/env bash
# PreCompact / PostCompact: keep docs/WORKLOG.md load-bearing.
#
# Before compaction: remind the agent to flush live state, because after the
# summary the conversation is a paraphrase of itself. After compaction: point
# at the file, so recovery starts from the record rather than from guesswork.
event="${1:-PostCompact}"
if [ "$event" = "PreCompact" ]; then
  text="Контекст сейчас будет сжат. До этого запиши в docs/WORKLOG.md: что делаем сейчас, следующие действия, живые фоновые процессы, незакоммиченное. Правила — skill slava-long-sessions."
else
  text="Контекст был сжат. Прочитай docs/WORKLOG.md и сверь его с реальностью (git status, git log --oneline -3, живы ли фоновые процессы). Если файл разошёлся с фактами — верь фактам и сразу почини файл."
fi
/usr/bin/python3 -c '
import json, sys
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": sys.argv[1],
        "additionalContext": sys.argv[2],
    },
    "suppressOutput": True,
}))
' "$event" "$text"
