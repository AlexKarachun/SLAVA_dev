# SLAVA_dev

SLAVA (*Slot-Level Attribution for VLA*) — исследовательский проект о том, как
VLA-модели понимают и исполняют инструкции на русском языке.

Актуальное описание полей `object_lexicon.csv` и `task_inventory.jsonl`:
[`docs/DATA_SCHEMAS.md`](docs/DATA_SCHEMAS.md).


## Развёртывание на сервере

На машине должны быть установлены Git, Conda/Miniforge и графические библиотеки
для MuJoCo/SAPIEN.

```bash
git clone https://github.com/AlexKrachun/SLAVA_dev.git
cd SLAVA_dev
bash scripts/bootstrap.sh
```

## Сбор дополнительных SimplerEnv-сцен

Collector работает в resume-режиме. Следующая команда добавляет недостающие
episode IDs `1, 4, 12, 20, 23` для задач с морковью и двумя кубиками, не
перезаписывая существующие `0, 8, 16`:

```bash
conda run --no-capture-output -n slava-simpler \
  python scripts/collect_simpler.py \
  --tasks widowx_carrot_on_plate widowx_stack_cube \
  --fail-fast
```

После сбора выполните в notebook раздел 3 для безопасного merge с сохранением
human review, затем пройдите новые сцены в разделах 4, 9 и 10.

## Screenshot sheet

```bash
python scripts/generate_screenshot_sheet.py --mode small
python scripts/generate_screenshot_sheet.py --mode full
python scripts/generate_screenshot_sheet.py \
  --mode small \
  --lexicon path/to/object_lexicon.csv
```

Результаты создаются в `data/screenshot_sheet_small.html` и
`data/screenshot_sheet_full.html`.

## Проверка inventory

Все source и merged inventories используют строгую схему
`schemas/task_inventory.schema.json`. Проверить их можно одной командой:

```bash
python scripts/validate_inventory.py
```

## Строим html по отобранным в v0 сценам

```bash
python scripts/generate_selected_scenes.py
```

Это широкая галерея по всем `usable_for_slava=true` кандидатам
(`docs/index.html`, GitHub Pages). Отдельный компактный лист по замороженным 20
задачам D3 (`data/selected_tasks_v0.jsonl`) содержит изображения, квоты и
сводную таблицу заполненности квот, но не выводит lexicon-таблицы под сценами:

```bash
python scripts/generate_selected_scenes.py \
  --input data/selected_tasks_v0.jsonl \
  --output data/selected_tasks_v0.html \
  --frozen-set
```

## Grounded semantic frames v0.2 (D4)

`data/pilot_v0_release/frames_v0.jsonl` — по одной записи на каждую из 20 задач D3
(`data/selected_tasks_v0.jsonl`): grounded `target`/`reference`/`relation`/
`forbidden` slots и Tier-1 instruction variants (`en_canonical`,
`en_paraphrase`, `mt_russian`, `ru_literal`, `ru_free_order`,
`ru_case_swap`/`axis_na`, `ru_negation`/`axis_na`, `code_switch`).
Пилот v0 заморожен (`validation.native_check="passed"`, tag `slava-pilot-v0`):
RU-текст был LLM draft, native check пройден — пользователь лично
просмотрел RU-переформулировки и подтвердил LLM-draft оценки как
human-verified; `mt_russian` — сырой MT (DeepL API), не LLM draft, и его
нельзя редактировать/улучшать.

```bash
python scripts/build_frames_v0.py   # регенерирует data/pilot_v0_release/frames_v0.jsonl из
                                     # selected_tasks_v0.jsonl + object_lexicon.csv
python scripts/validate_frames.py   # схема data/pilot_v0_release/frames_v0.schema.json
```

`token_len` считается реальными токенизаторами (не эвристикой) в отдельном
venv — тяжёлая зависимость `transformers`, не часть основного pipeline:

```bash
python3 -m venv .venv-tokenizers
.venv-tokenizers/bin/python -m pip install -r requirements-tokenizers.txt
.venv-tokenizers/bin/python scripts/compute_token_len.py
```

`google/paligemma-3b-pt-224` — gated-репозиторий на HuggingFace (нужен
аккаунт с принятой лицензией и `huggingface-cli login`). Подробности и
список токенизаторов — в skill `slava-token-len`.

`mt_russian` — сырой машинный перевод `en_canonical` (DeepL API, без
редактуры — см. правило в `task.md`). Ключ передаётся через переменную
окружения `DEEPL_API_KEY`, никогда не в командной строке или коде:

```bash
# fish: ключ хранится как universal variable, видна только fish-процессам
fish -c '.venv-tokenizers/bin/python scripts/run_mt_translate.py'
.venv-tokenizers/bin/python scripts/compute_token_len.py   # добавит колонку mt_russian
python3 scripts/validate_frames.py
```

Подробности (fish `set -Ux` vs bash/zsh окружение, DeepL header-based auth,
free-tier `api-free.deepl.com` хост) — в skill `slava-mt-russian`.

Экспорт плоских prompts для первых roll-out'ов (JSONL, одна строка на
`(task_uid, variant)`, 6 primary-вариантов из "Сначала затравка" в
`task.md` + `mt_russian`):

```bash
python scripts/export_prompts.py
```

Результат — `data/pilot_v0_release/prompts_v0.jsonl`. Каждая строка несёт reset-metadata
(`bddl_file`/`init_state_id` или `episode_id`/`reset_seed`/`gym_env_name`) и
`target_object`/`reference_object`/`forbidden_objects`/`success_predicates`
для авторазметки роллаутов (`rollout_annotations.jsonl` из `task.md`), а не
только текст инструкции.

Native check и ревью грамматики/ролей объектов удобно делать в редактируемом
дашборде `data/frames_review.html`: рендеры, роли объектов
(target/reference/distractor/forbidden/background с одной кнопкой на объект),
action/relation, текст каждого Tier-1 варианта и его naturalness/equivalence/
ambiguity (1–5). Правки накапливаются в браузере и выгружаются кнопкой
**Download corrections** в `frames_review_corrections.json`.

```bash
python scripts/generate_frames_review.py
python scripts/apply_frames_review.py path/to/frames_review_corrections.json
```

## Ревью видимости объектов

`data/visibility_review.html` — редактируемый дашборд по всем сценам
inventory: agentview/wrist рендеры и статус `visible_agentview`/`visible_wrist`
для каждого объекта, с фильтрами по suite/поиску/только-pending/только
AI-flagged. Изменения статуса накапливаются в браузере и выгружаются кнопкой
**Download corrections** в `visibility_corrections.json`.

```bash
python scripts/generate_visibility_review.py \
  --hints path/to/review_hints.json   # опционально: AI-подсказки для сложных случаев

python scripts/apply_visibility_review.py path/to/visibility_corrections.json

python scripts/sync_selected_tasks_visibility.py   # прокинуть обновлённую
                                                     # видимость в selected_tasks_v0.jsonl
```
