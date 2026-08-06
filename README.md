# SLAVA_dev

SLAVA (*Slot-Level Attribution for VLA*) — исследовательский проект о том, как
Vision-Language-Action (VLA) модели понимают и исполняют инструкции на
русском языке, и о том, где именно рвётся связь между «моделью понятно» и
«модель делает» (H-binding-гипотеза).

Полная научная постановка, схемы данных, квоты и процесс — в [`task.md`](task.md)
(внешний источник истины пользователя; код и данные должны ему
соответствовать, а не наоборот). Этот README — навигация по репозиторию:
что где лежит и как это запустить. Инструкции для AI-агентов, работающих в
этом репозитории (архитектурные инварианты, известные грабли, история
находок) — в [`AGENTS.md`](AGENTS.md) и `.claude/skills/slava-*`.

**Как пройти весь сбор заново (в т.ч. на полном наборе сцен):**
[`docs/RUNBOOK.md`](docs/RUNBOOK.md) — пошагово, от чистой машины до таблиц Δlang.

## Пайплайн одним взглядом

```
D1  task_inventory.jsonl      сбор кандидатных сцен (LIBERO + SimplerEnv)
D2  object_lexicon.csv        словарь физических типов объектов
D3  selected_tasks_v0.jsonl   заморозка 20 сцен под квоты v0 (16 LIBERO + 4 SimplerEnv)
D4  frames_v0.jsonl           grounded target/reference/relation/forbidden +
                               RU/EN instruction variants (заморожено, tag slava-pilot-v0)
D5  rollout_annotations.jsonl прогон 5 VLA-моделей × 127 промптов в симуляторе,
                               авторазметка успеха/провала
```

Каждый этап — отдельный раздел ниже, с самодостаточными командами.

## Развёртывание

Нужны Git, Conda/Miniforge, графические библиотеки для MuJoCo/SAPIEN, и (для
D5) NVIDIA GPU.

```bash
git clone https://github.com/AlexKrachun/SLAVA_dev.git
cd SLAVA_dev

# D1-D4: окружения для сбора/разметки данных (slava-notebook, slava-libero, slava-simpler)
bash scripts/bootstrap.sh

# D5: окружения для 5 VLA-моделей (slava-greenvla, slava-openvla, slava-lerobot)
# — отдельный скрипт, т.к. у моделей несовместимые друг с другом версии
# python/torch. См. предупреждение в самом файле — реконструирован из
# истории реальной отладочной сессии, не самостоятельная чистая проверка
# end-to-end на новой машине.
bash scripts/bootstrap_models.sh
```

## Репозиторий по разделам

| Путь | Что это |
| --- | --- |
| [`task.md`](task.md) | Полная научная постановка — контракт, от которого код/данные не должны отходить молча |
| [`AGENTS.md`](AGENTS.md) | Гайд для AI-агентов: архитектура, инварианты, история находок |
| [`schemas/`](schemas) | JSON Schema для `task_inventory.jsonl` |
| [`src/slava_inventory/`](src/slava_inventory) | Общий код D1-D4: схемы фреймов, IO, notebook-виджеты |
| [`src/slava_rollout/`](src/slava_rollout) | Общий код D5: env-worker'ы, model-клиенты, авторазметка, схема аннотаций |
| [`scripts/`](scripts) | Все точки входа (по одному скрипту на шаг пайплайна, см. таблицы ниже) |
| [`scripts/model_servers/`](scripts/model_servers) | HTTP model-серверы для 5 VLA-моделей |
| [`data/`](data) | Датасеты D1-D4 (inventory, lexicon, frames, prompts) |
| [`notebooks/`](notebooks) | Интерактивный сбор/ревью (01) и дашборд камер роллаутов (02) |
| [`docs/`](docs) | Публикуемые артефакты (GitHub Pages): галерея сцен, отчёт по роллаутам |
| `rollouts/` | **Не в git** (гигабайты PNG) — вывод `run_rollouts.py`, см. раздел D5 ниже |

## D1-D2: Inventory и словарь объектов

`data/task_inventory.jsonl` — воспроизводимые сцены LIBERO/SimplerEnv,
`data/object_lexicon.csv` — физические типы объектов на них. Схема обоих —
[`docs/DATA_SCHEMAS.md`](docs/DATA_SCHEMAS.md); строгая JSON Schema для
inventory — [`schemas/task_inventory.schema.json`](schemas/task_inventory.schema.json).

```bash
python scripts/validate_inventory.py       # проверка обоих файлов против схемы
python scripts/generate_screenshot_sheet.py --mode small   # обзорный лист по всем сценам
```

Добор дополнительных SimplerEnv-сцен (resume-режим, не перезаписывает уже
собранное):

```bash
conda run --no-capture-output -n slava-simpler \
  python scripts/collect_simpler.py \
  --tasks widowx_carrot_on_plate widowx_stack_cube --fail-fast
```

## D3: Отбор сцен под квоты v0

`data/selected_tasks_v0.jsonl` — заморозка 20 сцен (16 LIBERO + 4 SimplerEnv),
удовлетворяющих квотам `task.md`. Тот же JSON Schema, что у D1 (`usable_for_slava=true`
подмножество, отдельной схемы нет).

```bash
python scripts/generate_selected_scenes.py \
  --input data/selected_tasks_v0.jsonl \
  --output data/selected_tasks_v0.html --frozen-set
```

Разметка видимости объектов (используется квотами D3):

```bash
python scripts/generate_visibility_review.py    # -> data/visibility_review.html, ревью в браузере
python scripts/apply_visibility_review.py path/to/visibility_corrections.json
python scripts/sync_selected_tasks_visibility.py
```

## D4: Grounded semantic frames (заморожено, tag `slava-pilot-v0`)

`data/pilot_v0_release/frames_v0.jsonl` — по одной записи на каждую из 20 задач D3:
grounded `target`/`reference`/`relation`/`forbidden` слоты + 8 Tier-1
instruction variants (`en_canonical`, `en_paraphrase`, `mt_russian`,
`ru_literal`, `ru_free_order`, `ru_case_swap`, `ru_negation`, `code_switch`).
Схема — [`data/pilot_v0_release/frames_v0.schema.json`](data/pilot_v0_release/frames_v0.schema.json).
Правила авторинга вариантов — skill `slava-instruction-variants`.

```bash
python scripts/build_frames_v0.py      # регенерирует frames_v0.jsonl из selected_tasks_v0.jsonl + lexicon
python scripts/validate_frames.py      # проверка против схемы
```

`token_len` — реальные токенизаторы (Qwen3-VL, OpenVLA-OFT, PaliGemma,
SmolVLM2), не эвристика; отдельный venv из-за тяжёлой зависимости
`transformers`:

```bash
python3 -m venv .venv-tokenizers
.venv-tokenizers/bin/python -m pip install -r requirements-tokenizers.txt
.venv-tokenizers/bin/python scripts/compute_token_len.py
```

`google/paligemma-3b-pt-224` — gated-репозиторий (нужен `huggingface-cli login`
с принятой лицензией). Подробности — skill `slava-token-len`.

`mt_russian` — сырой машинный перевод (DeepL API, без редактуры — правило
`task.md`). Ключ — только через переменную окружения `DEEPL_API_KEY`, никогда
в командной строке/коде:

```bash
.venv-tokenizers/bin/python scripts/run_mt_translate.py
.venv-tokenizers/bin/python scripts/compute_token_len.py   # пересчёт с новой колонкой
python3 scripts/validate_frames.py
```

Подробности провайдера/авторизации — skill `slava-mt-russian`.

Экспорт плоских промптов для роллаутов (JSONL, одна строка на
`(task_uid, variant)`, включая reset-metadata и success-predicates для
авторазметки):

```bash
python scripts/export_prompts.py    # -> data/pilot_v0_release/prompts_v0.jsonl
```

Native-check / ревью текста — редактируемый дашборд:

```bash
python scripts/generate_frames_review.py    # -> data/frames_review.html
python scripts/apply_frames_review.py path/to/frames_review_corrections.json
```

## D5: Model rollouts

Прогон 5 VLA-моделей на `data/pilot_v0_release/prompts_v0.jsonl` в закрытом цикле
(closed-loop) в симуляторе, с авторазметкой успеха и типа ошибки.

### Модели и среды

| Модель | Backbone | Среда(ы) | Чекпойнт |
| --- | --- | --- | --- |
| GreenVLA-R0 | Qwen3-VL-4B-Instruct | SimplerEnv | `SberRoboticsCenter/GreenVLA-5b-base-stride-1` |
| GreenVLA-R1 (bridge) | Qwen3-VL-4B-Instruct | SimplerEnv | `SberRoboticsCenter/GreenVLA-5b-stride-1-R1-bridge` |
| GreenVLA-R2 (bridge, RL-aligned) | Qwen3-VL-4B-Instruct | SimplerEnv | `SberRoboticsCenter/GreenVLA-5b-stride-1-R2-bridge` |
| OpenVLA-OFT | Prismatic (openvla-7b) | LIBERO | `moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10` |
| pi0 | PaliGemma | LIBERO / SimplerEnv | `lerobot/pi0_libero_finetuned` / `lerobot/pi0_base` (zero-shot) |
| pi0.5 | PaliGemma | LIBERO / SimplerEnv | `lerobot/pi05_libero_finetuned` / `lerobot/pi05_base` (zero-shot) |
| SmolVLA | SmolVLM2-500M | LIBERO / SimplerEnv | `HuggingFaceVLA/smolvla_libero` / `lerobot/smolvla_base` (zero-shot) |

Полный список актуален в коде: `MODEL_REGISTRY` в
[`src/slava_rollout/schema.py`](src/slava_rollout/schema.py). GreenVLA
считается тремя отдельными моделями (curriculum-стадии R0→R1→R2, разные
чекпойнты одного backbone), а не одной — так же считает их и код.

### Архитектура: env-worker + model-server + оркестратор

```
run_rollouts.py (оркестратор, env slava-notebook)
   │
   ├──> env-worker (HTTP, LIBERO:8701 / SimplerEnv:8702)  — свой conda env,
   │    /reset /step — рендер, физика, success-детекция    рендер-стек
   │
   └──> model-server (HTTP, порт на модель) — свой conda env на модель,
        /predict /predict_chunk — инференс                несовместимые версии
```

Один env-worker на среду обслуживает **все** модели этой среды (LIBERO-env —
тонкая обёртка вокруг `libero.libero.envs.OffScreenRenderEnv`, которую и
lerobot, и наш собственный код используют одинаково). Каждая модель — свой
model-server в своём conda env, т.к. пять моделей несовместимы друг с другом
по python/torch версиям (см. `scripts/bootstrap_models.sh`). Оркестратор
поднимает/останавливает процессы по одному, чтобы не держать в GPU-памяти
больше одной модели разом.

### Запуск

```bash
# быстрая проверка всей цепочки: 2 сцены/модель, только en_canonical
conda run -n slava-notebook python scripts/run_rollouts.py --smoke-test

# полный прогон, все модели, все 127 промптов
conda run -n slava-notebook python scripts/run_rollouts.py

# одна модель (например, после фикса — resume безопасен, уже готовые
# эпизоды пропускаются по run_id)
conda run -n slava-notebook python scripts/run_rollouts.py --models pi0 pi05

# шардинг по нескольким GPU параллельно
CUDA_VISIBLE_DEVICES=0 conda run -n slava-notebook python scripts/run_rollouts.py \
  --num-shards 2 --shard-index 0
CUDA_VISIBLE_DEVICES=1 conda run -n slava-notebook python scripts/run_rollouts.py \
  --num-shards 2 --shard-index 1
```

Вывод — `rollouts/rollout_annotations.jsonl` (одна строка на эпизод, схема —
`ROLLOUT_ANNOTATION_FIELDS` в `src/slava_rollout/schema.py`) и
`rollouts/episodes/<run_id>/` (PNG-кадры camera по шагам + `steps.jsonl`).
**`rollouts/` не в git** — гигабайты бинарных данных, полностью
регенерируется этой командой.

### Отчёт

```bash
python scripts/generate_rollout_report.py --output data/rollout_report.html
# самодостаточная версия для публикации (копирует камеры рядом с HTML,
# не ссылается на rollouts/, которого нет в git):
python scripts/generate_rollout_report.py --output docs/rollout_report.html --for-pages
```

Таблицы "behavioral pilot" (SR / first-contact accuracy / wrong-object rate /
forbidden touch по каждому из 8 вариантов) и "cleaned language effect"
(Δlang — языковой эффект отдельно от instruction-string OOD, главная
метрика пилота) — см. `task.md`, разделы "Auto-labeling" и "Failure labels"
за точным контрактом полей и правилами разметки.

Интерактивный просмотр всех камерных записей одним запуском ячейки —
`notebooks/02_rollout_camera_dashboard.ipynb`.

## Известные ограничения на момент этой версии

- **Ручная валидация первых 100 rollouts** (обязательное требование `task.md`)
  ещё не проведена — доверять авторазметке `failure_type_auto` в масштабе
  стоит только после неё.
- **Подозрительно низкий SR у большинства моделей — главный открытый
  вопрос.** Здоровые результаты только у OpenVLA-OFT (74/99) и GreenVLA-R2
  (6/28). У GreenVLA-R0/R1, pi0, pi0.5, SmolVLA — SR около нуля, заметно
  ниже заявленного авторами. Несколько реальных багов уже найдены и
  исправлены (см. skills), но как минимум один системный, судя по всему,
  остаётся: GreenVLA-R0 даёт 0/10 на задаче `eggplant`, для которой авторы
  заявляют 88.5% — ноль на самой лёгкой задаче нельзя объяснить слабостью
  модели. Актуальная главная зацепка (бинаризация гриппера, по аналогии с
  уже подтверждённым багом OpenVLA-OFT) описана в
  `.claude/skills/slava-greenvla`.
- **Что исключено из метрик — объявлено в `data/rollout_provenance.json`.**
  Сейчас там одно правило: 56 эпизодов pi0/pi0.5 на SimplerEnv, снятых до
  правки распределения камер в `lerobot_server.py`. В метриках отчёта —
  494 эпизода из 550. Файл читается напрямую и правится вручную: раньше
  валидность выводилась из mtime файлов, что давало **разный состав моделей
  на разных машинах** для одних и тех же данных (подробности —
  `src/slava_rollout/provenance.py`).
- **Данные, снятые до 2026-08-06, несут ещё один конфаунд у pi0/pi0.5/SmolVLA:**
  очередь действий политики не сбрасывалась между эпизодами, поэтому хвост
  чанка предыдущего эпизода доигрывался в начале следующего — а эпизоды идут
  сгруппированно по вариантам инструкции. Исправлено (`/reset` у model-серверов),
  но затронутые эпизоды надо переснять перед использованием их вариантных
  сравнений. См. `.claude/skills/slava-lerobot-policies`.
- **Покрытие**: полное у всех моделей, кроме SmolVLA (114 из 127). Точные
  цифры — в `docs/rollout_report.html`.

Подробная история находок (все реальные баги, которые были найдены и
исправлены в ходе отладки — camera-swap, rotation representation,
action-truncation, device-mismatch и т.д.) — в `.claude/skills/slava-*`,
по одному skill на модель/тему.
