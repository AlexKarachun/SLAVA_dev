# Контекст проекта SLAVA для LLM-агентов

Этот файл — устойчивый handoff по проекту. Перед изменениями также прочитайте
[`AGENTS.md`](AGENTS.md), проверьте `git status` и не перезаписывайте
пользовательскую разметку.

Изменяемые данные и текущий статус не дублируются здесь. Их источники истины:

- candidate scenes: [`data/task_inventory.jsonl`](data/task_inventory.jsonl);
- object names и пригодность для v0:
  [`data/object_lexicon.csv`](data/object_lexicon.csv);
- визуальная проверка:
  [`data/screenshot_sheet_small.html`](data/screenshot_sheet_small.html) и
  [`data/screenshot_sheet_full.html`](data/screenshot_sheet_full.html);
- строгий data contract:
  [`schemas/task_inventory.schema.json`](schemas/task_inventory.schema.json);
- подробный исследовательский и benchmark-план: [`task.md`](task.md).

## Научная цель

SLAVA (*Slot-Level Attribution for VLA*) исследует падение качества
Vision-Language-Action моделей на неанглийских, прежде всего русских,
инструкциях.

Главная гипотеза — *cross-lingual action-binding collapse*: после action
fine-tuning семантические слоты русской инструкции могут оставаться
декодируемыми во внутренних состояниях модели, но перестать причинно влиять на
action head.

Проверяются три объяснения:

- `H-understanding`: модель не извлекает смысл русской инструкции;
- `H-grounding`: смысл извлечен, но не связан с объектами и отношениями сцены;
- `H-binding`: смысл извлечен и заземлен, но action head его не использует.

Экспериментальный дизайн и критерии перехода между гипотезами описаны в
[`task.md`](task.md).

## Текущий этап и порядок работы

Проект строит environment-first benchmark. Фактическую готовность этапов
определяйте по наличию и содержимому артефактов в [`data/`](data), а не по
текстовому статусу в документации.

Обязательный порядок:

```text
task + init state
→ RGB renders
→ реальные sim objects, handles и poses
→ ручная проверка видимости
→ object lexicon
→ отбор сцен и selected-task manifest
→ grounded semantic frames
→ EN/RU/code-switch variants
→ schema validation и native check
→ freeze
→ model rollouts
```

Русские инструкции нельзя начинать до утверждения scene inventory, screenshot
review, object lexicon и selected-task manifest. Требования к отбору, языковым
вариантам и QA находятся в [`task.md`](task.md).

## Единица данных

Не смешивайте:

- `task` — исходную задачу benchmark;
- `scene` — конкретный `task × init state`;
- `trajectory` или `rollout` — последовательность действий в сцене.

Одна строка inventory — одна воспроизводимая сцена, не траектория. `task_id`
индексирует исходную задачу внутри suite и сам по себе не идентифицирует сцену.
Стабильный идентификатор сцены — `task_uid` вместе с metadata воспроизводимости
в `source`.

## Неизменяемые решения

- Candidate inventory содержит 102 сцены: 90 LIBERO и 12 SimplerEnv.
- LIBERO использует suites spatial/object/goal и init ids `0, 17, 34`.
- SimplerEnv использует закрепленные `widowx_*` задачи и episode ids
  `0, 8, 16` при `reset_seed=0`.
- LIBERO рендерится сразу после `set_init_state`; `settle_steps` остается 0.
- У используемого SimplerEnv WidowX нет wrist camera; `wrist_rgb` остается
  `null`.
- При merge и regeneration сохраняются human review fields.
- Portable manifest хранит repository-relative runtime paths и pinned commits,
  но не машинно-зависимые пути вроде `/workspace/...`.
- Pinned commits и состав candidate pool нельзя менять молча. Актуальные
  commits установки заданы в [`scripts/bootstrap.sh`](scripts/bootstrap.sh), а
  commits конкретных записей хранятся в `source.commit` inventory.
- LIBERO HDF5 demonstrations не нужны scene collectors. Их загрузка в
  [`scripts/bootstrap.sh`](scripts/bootstrap.sh) предназначена для будущей
  model/trajectory работы.

## Data contract

Все source и merged inventories обязаны проходить
[`schemas/task_inventory.schema.json`](schemas/task_inventory.schema.json).
Лишние поля запрещены.

Верхний уровень записи:

- `task_uid`;
- `suite`, `task_id`, `canonical_en`;
- `source`;
- `images`;
- `objects_raw`;
- `success_predicates`;
- `candidate_slots`;
- `usable_for_slava`, `notes`.

Каждый `objects_raw` содержит только `sim_handle`, `raw_name`, `pose_xyz`,
`visible_agentview` и `visible_wrist`. Допустимая visibility:

- `true` — уверенно виден;
- `"visible_partial"` — частично виден, но распознаваем;
- `false` — не виден или не распознаваем;
- `null` — не проверен либо камеры нет.

Выбор v0 и расширенная review metadata не добавляются в inventory: они должны
жить в отдельном selected-task manifest согласно [`task.md`](task.md).

Проверка:

```bash
python scripts/validate_inventory.py
```

Collectors валидируют записи до сохранения. При повторном сборе не включайте
`OVERWRITE_EXISTING` без необходимости полного ререндера; merge должен сохранять
`usable_for_slava`, `notes`, `candidate_slots` и object visibility.

## Object lexicon

[`data/object_lexicon.csv`](data/object_lexicon.csv) связывает `raw_name` ассета
с каноническими EN/RU-названиями, цветом, допустимым русским синонимом и
`usable_v0`.

Правила:

- `category_ru` — основное имя для авторинга;
- `color_ru` согласуется с `category_ru`;
- `allowed_synonyms_ru` обозначает тот же физический объект, а не его содержимое
  или более широкую категорию;
- синоним нельзя механически соединять с `color_ru`, если у него другой род;
- в русских полях лексикона используется `е`, а не `ё`;
- похожий перевод не является основанием объединять разные физические категории.

Small screenshot sheet объединяет inventory и lexicon. Его фильтр
`usable_v0` учитывает все `objects_raw`, включая фоновые объекты, поэтому это
диагностика, а не единственное правило отбора сцены.

## Основные точки входа

- развертывание и pinned dependencies:
  [`scripts/bootstrap.sh`](scripts/bootstrap.sh);
- collectors: [`scripts/collect_libero.py`](scripts/collect_libero.py) и
  [`scripts/collect_simpler.py`](scripts/collect_simpler.py);
- merge, review и lexicon UI:
  [`notebooks/01_collect_and_review_inventory.ipynb`](notebooks/01_collect_and_review_inventory.ipynb);
- HTML review:
  [`scripts/generate_screenshot_sheet.py`](scripts/generate_screenshot_sheet.py);
- validation: [`scripts/validate_inventory.py`](scripts/validate_inventory.py),
  [`src/slava_inventory/schema.py`](src/slava_inventory/schema.py);
- safe JSONL/CSV merge:
  [`src/slava_inventory/io_utils.py`](src/slava_inventory/io_utils.py).

После изменений выполняйте проверки, пропорциональные риску. Особенно берегите
`data/task_inventory.jsonl`, `data/object_lexicon.csv` и `data/images`: human
annotations и локальные рендеры нельзя восстанавливать ценой их перезаписи.
