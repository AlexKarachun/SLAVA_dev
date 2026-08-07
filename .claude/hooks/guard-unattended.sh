#!/usr/bin/env bash
# PreToolUse guard: refuse the handful of actions that must never happen
# without a human, whatever the permission mode.
#
# Unattended shifts run with permission prompts disabled — there is nobody to
# approve anything. Hooks, unlike permission rules, are evaluated regardless of
# that mode, so this is the layer that still says no. Deliberately short: it
# blocks what is irreversible or violates a standing project decision, not what
# is merely risky. Everything else is git-revertible.
exec /usr/bin/python3 -c '
import json, re, sys

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool = payload.get("tool_name", "")
tool_input = payload.get("tool_input") or {}

def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    raise SystemExit(0)

# 1. Frozen contract and frozen pilot data (AGENTS.md: task.md is the user"s
#    contract; data/pilot_v0_release is frozen at tag slava-pilot-v0).
if tool in ("Edit", "Write", "NotebookEdit"):
    path = str(tool_input.get("file_path", ""))
    if re.search(r"(^|/)task\.md$", path):
        deny("task.md — контракт пользователя, его нельзя редактировать (AGENTS.md).")
    if "data/pilot_v0_release/" in path:
        deny("Замороженный пилот (tag slava-pilot-v0) не редактируется без человека.")

# 2. Irreversible shell actions.
if tool == "Bash":
    command = str(tool_input.get("command", ""))
    rules = [
        (r"git\s+push\b.*--force|git\s+push\b.*\s-f\b", "force-push переписывает историю — только с человеком."),
        (r"git\s+tag\s+-d|git\s+push\b.*--delete\s+.*slava-pilot-v0", "Тег slava-pilot-v0 не двигается."),
        (r"git\s+reset\s+--hard", "git reset --hard теряет несохранённую работу — не в автономном режиме."),
        (r"\bhf\b.*\brepo\s+delete|huggingface-cli\s+.*delete", "Удаление репозитория на HF необратимо."),
        (r"rm\s+-rf?\s+(/|~|\$HOME)(\s|$)", "Удаление домашней или корневой директории."),
        (r"rm\s+-rf?\s+[^|;&]*rollouts/final", "Финальные пулы эпизодов существуют только локально — не удалять."),
    ]
    for pattern, reason in rules:
        if re.search(pattern, command):
            deny(reason)
sys.exit(0)
'
