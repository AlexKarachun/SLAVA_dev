# RUNBOOK — как пройти весь сбор заново, на полном наборе сцен

Пошаговая инструкция: от чистой машины до таблиц Δlang. Пилот v0 (20 сцен)
этим путём уже пройден и заморожен (`slava-pilot-v0`); здесь тот же путь для
масштабирования на полный набор из `task.md` («Потом полный набор»: 120–180
задач × 12–13 вариантов).

Что уже готово и не требует повторения: `data/full_set/` — 390 записей LIBERO
по 130 уникальным задачам (все 5 suite) + 22 сцены SimplerEnv, собранные с
`--settle-steps 40`. То есть **этап D1 для полного набора уже выполнен**, шаг 2
ниже нужен только если вы дособираете новые сцены.

Порядок обязателен: каждый этап потребляет замороженный выход предыдущего.
`task.md` — контракт по всем структурам данных; при расхождении прав он, а не
этот файл.

---

## 0. Проверка окружения (5 минут, без GPU)

```bash
python3 -m unittest discover -s tests -v      # 37 тестов, без pip install
python3 scripts/validate_inventory.py
python3 scripts/validate_frames.py
```

Тесты не должны требовать установки чего-либо: они на stdlib намеренно, чтобы
их можно было прогнать на любой машине до всякой настройки. Если они падают —
дальше не идти, это контракт данных, а не стиль.

## 1. Установка (нужна только на новой машине)

```bash
git clone https://github.com/AlexKarachun/SLAVA_dev.git && cd SLAVA_dev
bash scripts/bootstrap.sh          # D1-D4 + два env-worker'а (LIBERO, SimplerEnv)
bash scripts/bootstrap_models.sh   # окружения пяти моделей (нужен CUDA)
```

Сторонние репозитории (LIBERO, SimplerEnv, чекпойнты моделей) кладутся **рядом**
с этим репозиторием, не внутрь; переопределяется `SLAVA_DEPS_DIR`. Абсолютных
путей в коде быть не должно — если нашли, это баг.

`bootstrap.sh` в конце проверяет импорты оркестратора и обоих env-worker'ов —
он должен упасть на установке, а не в середине многочасового прогона.

**Если GPU не Tesla V100** — обязательно прочитайте раздел «Porting to different
hardware» в `.claude/skills/slava-model-rollouts/SKILL.md`: часть фиксов в коде
(отключённый cuDNN, форсированный float32, пин torch) существуют только из-за
отсутствия bf16 на Volta и на новых картах превращаются в беспричинное
замедление.

## 2. D1 — сбор сцен (только если нужны новые сцены)

```bash
conda run -n slava-libero  python scripts/collect_libero.py  --settle-steps 40
conda run -n slava-simpler python scripts/collect_simpler.py --settle-steps 40
python3 scripts/validate_inventory.py
```

**`--settle-steps` обязателен и не имеет разумного значения по умолчанию.**
Коллекторы по умолчанию ставят 0, и пилот v0 был собран именно так — то есть и
рендеры, и `pose_xyz` там сняты, пока объекты ещё падают. Для `data/full_set/`
использовано 40. Значение пишется в `source.settle_steps` каждой записи;
**сравнивая сцены между коллекциями, всегда сверяйте это поле** — 0 и 40 дают
физически разные данные, и разница видна глазом.

Коллекторы работают в resume-режиме: повторный запуск дособирает недостающее,
не перезаписывая уже собранное.

## 3. D2 — словарь объектов

Каждый новый `raw_name` должен получить строку в `data/object_lexicon.csv`.
Проверить, чего не хватает:

```bash
python3 - <<'EOF'
import json, csv, glob
raw = {o["raw_name"] for f in glob.glob("data/full_set/*_inventory.jsonl")
       for r in map(json.loads, open(f)) for o in r["objects_raw"]}
lex = {r["raw_name"] for r in csv.DictReader(open("data/object_lexicon.csv"))}
print(sorted(raw - lex))
EOF
```

На момент написания не хватает 14 записей (`black_book`, `microwave`,
`moka_pot`, `white_cabinet`, …). Правила заполнения (порядок источников
истины, recoverability, согласование рода, `usable_v0`) — skill
`slava-object-lexicon`. Порядок проверки имени объекта: реальный рендер →
`raw_name`/`sim_handle` → семантика BDDL → HOPE mesh/texture → только потом
решение.

Визуальный контроль:

```bash
python3 scripts/generate_screenshot_sheet.py --mode small
python3 scripts/generate_visibility_review.py     # разметка видимости в браузере
python3 scripts/apply_visibility_review.py path/to/visibility_corrections.json
```

## 4. D3 — отбор сцен под квоты

Разметить `quota_eligibility` (девять флагов) и отобрать манифест так, чтобы
все квоты `task.md` были выполнены. Операционные правила и мнемоники — skill
`slava-quota-eligibility` и раздел «Мнемонические правила разметки квот» в
`AGENTS.md`. Результат — замороженный манифест по образцу
`data/selected_tasks_v0.jsonl` (у D3 нет своей схемы: контракт — тот же
`schemas/task_inventory.schema.json`).

```bash
python3 scripts/validate_inventory.py
```

## 5. D4 — grounded frames и варианты инструкций

```bash
python3 scripts/build_frames_v0.py       # LLM draft из манифеста + лексикона
python3 scripts/validate_frames.py
```

Дальше по порядку, каждый шаг обязателен:

1. **Роли и слоты** — `target`/`reference`/`distractor`/`background`,
   `slots.forbidden`, `success_predicates`. Составные объекты (ящики шкафа)
   именуются буквально по BDDL-региону, а не выдуманной схемой — skill
   `slava-scene-roles`.
2. **Tier-1 варианты** — одна языковая ось на вариант, лаконичность промпта;
   skill `slava-instruction-variants`.
3. **`mt_russian`** — реальный MT-прогон, сырой вывод, **редактировать
   запрещено** (правило `task.md`):
   ```bash
   fish -c '.venv-tokenizers/bin/python scripts/run_mt_translate.py'
   ```
   Ключ только через переменную окружения `DEEPL_API_KEY`, никогда в чат, код
   или командную строку. У пользователя shell — fish, где `set -Ux` невидим
   для bash/zsh-процессов, отсюда обёртка `fish -c`. См. skill
   `slava-mt-russian`.
4. **`token_len`** — реальные токенизаторы, не эвристика:
   ```bash
   .venv-tokenizers/bin/python scripts/compute_token_len.py
   ```
   Четыре ключа/чекпойнта заданы в `src/slava_inventory/frames_schema.py`
   (`TOKEN_LEN_CHECKPOINTS`). PaliGemma — gated, нужен HF-аккаунт с принятой
   лицензией. См. skill `slava-token-len`.
5. **Native check** — `data/frames_review.html`, пороги
   naturalness/equivalence/ambiguity `>= 4`, шкала `ambiguity`: выше = чётче.
   Для пилота v0 пользователь засчитал неформальный просмотр; **на полном
   наборе это надо подтвердить заново**, см. skill `slava-native-check`.
   ```bash
   python3 scripts/generate_frames_review.py
   python3 scripts/apply_frames_review.py path/to/frames_review_corrections.json
   ```
6. **Экспорт промптов и заморозка**:
   ```bash
   python3 scripts/export_prompts.py
   python3 scripts/validate_frames.py
   git tag slava-<name>            # freeze только по явному решению
   ```

Регенерация `build_frames_v0.py` сбрасывает `native_check` в `pending` и
`mt_russian` в `null` — **не запускайте её на замороженном наборе** без
причины.

## 6. D5 — прогоны моделей (нужен GPU)

Сначала дым-тест: 2 сцены на модель, только `en_canonical`.

```bash
conda run -n slava-notebook python scripts/run_rollouts.py --smoke-test
```

Затем полный прогон. Resume по `run_id` включён всегда — повторный запуск
досчитывает недостающее и не портит уже собранное.

```bash
conda run -n slava-notebook python scripts/run_rollouts.py
# конкретные модели:
conda run -n slava-notebook python scripts/run_rollouts.py --models pi0 pi05 smolvla
```

**Несколько GPU.** Шардинг round-robin; каждый шард — отдельный процесс со
своими портами, иначе экземпляры env-worker'ов подерутся за общее состояние:

```bash
CUDA_VISIBLE_DEVICES=0 SLAVA_LIBERO_PORT=8701 SLAVA_MODEL_PORT_PI0=8804 \
  conda run -n slava-notebook python scripts/run_rollouts.py \
  --models pi0 --num-shards 2 --shard-index 0 &
CUDA_VISIBLE_DEVICES=1 SLAVA_LIBERO_PORT=8711 SLAVA_MODEL_PORT_PI0=8814 \
  conda run -n slava-notebook python scripts/run_rollouts.py \
  --models pi0 --num-shards 2 --shard-index 1 &
```

Что проверить до того, как доверять числам (все три ловили реальные баги):

- **Распределение входа, а не только выход.** Сравните реальные наблюдения с
  `q01/q99` из собственных `norm_stats` чекпойнта. Так были найдены и мировая
  система координат вместо базовой, и перепутанные камеры.
- **Не замерла ли модель.** md5 каждого сохранённого кадра и самая длинная
  серия одинаковых хэшей: модель, ушедшая в ступор, даёт честный SR=0% без
  единой попытки заземления — в отчёте это читается совсем не так, как
  «пыталась и не смогла».
- **Пост-обработка действий у вендора.** Смотрите их *eval-луп*, а не
  quick-start: у OpenVLA-OFT там `normalize_gripper_action` +
  `invert_gripper_action`, без которых гриппер не закрывается никогда.

## 7. Метрики и отчёт (без GPU)

```bash
python3 scripts/generate_report_compact.py --output docs/report.html
python3 scripts/generate_rollout_report.py --for-pages --output docs/rollout_report.html
```

Если менялись правила разметки — пересчитать метки из сырых логов, а не
править руками:

```bash
python3 scripts/relabel_rollouts.py            # dry run: покажет таблицу переходов
python3 scripts/relabel_rollouts.py --write
```

**Исключения из метрик объявляются в `data/rollout_provenance.json`** — с
причиной и условием снятия. Не выводите валидность из mtime файлов и не
«чините» данные, трогая временные метки: ровно это давало разный состав
моделей на разных машинах для одних и тех же данных.

Что считается и как:

- SR — из нативного `env.check_success()` / `info["success"]`, не из нашей
  реализации предикатов.
- Δlang<sub>v</sub> = gap<sub>v</sub> − gap<sub>en_paraphrase</sub>, всё —
  **на пересечении сцен** anchor ∩ control ∩ variant. Иначе разница в составе
  сцен читается как языковой эффект (`ru_case_swap` осмыслен лишь на части
  сцен).
- CI по SR — Уилсон; по Δlang — парный бутстрап по сценам; p — точный
  Мак-Немар против `en_canonical`. Прочерк в p значит «нет дискордантных пар»,
  то есть данных для суждения нет — это не «различий нет».
- Пулинг моделей в один Δlang не делается намеренно: модели с SR≈0 во всех
  языках дают Δlang≈0 механически и размывают остальных.

## 8. Обязательное перед публикацией

**Ручная валидация первых 100 роллаутов** (`task.md`): проверить точность
авторазметки, прежде чем доверять ей на всём массиве. Не пройдена до сих пор.
Особое внимание — разделению `relation_binding_error` и
`reference_grounding_error`: по одному сигналу первого контакта они
неразличимы, и авторазметчик по умолчанию ставит первое.

---

## Куда смотреть, когда что-то не так

| Симптом | Где написано |
| --- | --- |
| SR=0% у модели, которая по статье работает | `slava-model-rollouts` → «Debugging low SR» |
| Специфика OpenVLA-OFT / pi0 / pi0.5 / SmolVLA / GreenVLA | одноимённые `slava-*` skills |
| Метрика подозрительно коррелирует со средой или моделью | `slava-model-rollouts` → «Data-integrity audit» |
| Новая машина, другая GPU | `slava-model-rollouts` → «Porting to different hardware» |
| Правила полей, квот, схем | `task.md` (контракт), `AGENTS.md` (как с ним работать) |
