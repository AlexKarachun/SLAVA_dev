#!/usr/bin/env bash
# Оркестратор автономной смены: очередь задач → отдельная сессия на задачу.
#
# Почему не одна длинная сессия в tmux, а несколько коротких: контекст
# заполняется, срабатывает компактификация, и после нескольких сжатий инструкции
# заметно теряют силу — это воспроизводимо описано теми, кто уже гонял такие
# смены. Здесь каждая задача получает СВЕЖИЙ контекст (`claude -p`), а связь
# между задачами идёт через файлы: docs/NIGHT_QUEUE.md, docs/WORKLOG.md и git.
#
# Запуск (внутри tmux, см. docs/NIGHT_SHIFT.md):
#   tmux new -s slava
#   bash scripts/night_shift.sh 2>&1 | tee -a rollouts/night_shift.log
#
# Переменные:
#   SLAVA_MAX_TURNS      потолок ходов на задачу (по умолчанию 120)
#   SLAVA_MAX_BUDGET     потолок $ на задачу (по умолчанию пусто = без потолка)
#   SLAVA_SHIFT_HOURS    сколько часов работать (по умолчанию 48)
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
QUEUE="docs/NIGHT_QUEUE.md"
LOGDIR="rollouts/night_shift"
MAX_TURNS="${SLAVA_MAX_TURNS:-120}"
SHIFT_HOURS="${SLAVA_SHIFT_HOURS:-48}"
DEADLINE=$(( $(date +%s) + SHIFT_HOURS * 3600 ))
mkdir -p "$LOGDIR"

log() { echo "[$(date '+%d.%m %H:%M')] $*"; }

next_task() {
  # Первая незакрытая строка очереди: "- [ ] текст"
  grep -n '^- \[ \] ' "$QUEUE" 2>/dev/null | head -1
}

mark_done()    { python3 scripts/night_shift_queue.py --done "$1"; }
mark_blocked() { python3 scripts/night_shift_queue.py --blocked "$1" --reason "$2"; }

while :; do
  [ "$(date +%s)" -ge "$DEADLINE" ] && { log "смена окончена по времени"; break; }

  entry="$(next_task)"
  [ -z "$entry" ] && { log "очередь пуста — работа закончена"; break; }

  line="${entry%%:*}"
  task="${entry#*] }"
  stamp="$(date +%Y%m%d-%H%M%S)"
  head_before="$(git rev-parse HEAD)"
  log "задача (строка $line): $task"

  # Свежая сессия на задачу. Промпт короткий: весь постоянный контекст агент
  # берёт из AGENTS.md и скилов, а состояние — из WORKLOG.
  prompt="Ты работаешь в автономной смене без пользователя. Прочитай docs/WORKLOG.md и следуй skill slava-budget-pacing и slava-long-sessions.
Задача этой сессии: ${task}
Правила: доделать до конца или честно записать, что заблокировано; прогнать python3 -m unittest discover -s tests; закоммитить и запушить; обновить docs/WORKLOG.md; отметить стоимость через python3 scripts/budget_log.py --mark \"${task}\". Ничего сверх этой задачи не начинать."

  budget_arg=()
  [ -n "${SLAVA_MAX_BUDGET:-}" ] && budget_arg=(--max-budget-usd "$SLAVA_MAX_BUDGET")

  claude -p "$prompt" \
    --permission-mode bypassPermissions \
    --max-turns "$MAX_TURNS" \
    "${budget_arg[@]}" \
    > "$LOGDIR/${stamp}.log" 2>&1 </dev/null
  status=$?

  if [ $status -ne 0 ]; then
    tail_out="$(tail -3 "$LOGDIR/${stamp}.log" | tr '\n' ' ')"
    # Упёрлись в лимит — это не ошибка, это ожидание. Ждём и пробуем снова.
    if echo "$tail_out" | grep -qiE 'rate limit|usage limit|quota'; then
      log "лимит исчерпан, ждём 30 минут и повторяем"
      sleep 1800
      continue
    fi
    log "задача завершилась с кодом $status: $tail_out"
    mark_blocked "$line" "выход $status, см. $LOGDIR/${stamp}.log"
    continue
  fi

  # Задача считается сделанной, только если после неё есть новый коммит:
  # «модель сказала, что сделала» — не доказательство.
  if [ "$(git rev-parse HEAD)" != "$head_before" ] && git diff --quiet && git diff --cached --quiet; then
    mark_done "$line"
    log "готово, дерево чистое"
  else
    mark_blocked "$line" "не закоммичено или дерево грязное"
    log "ВНИМАНИЕ: дерево грязное после задачи"
  fi
done

log "смена завершена; итог: git log --oneline, docs/WORKLOG.md, docs/BUDGET_LOG.md"
