# Контекст проекта SLAVA для LLM-агентов

Этот документ — основной handoff для работы с репозиторием. Перед изменениями
прочитайте его полностью, затем `AGENTS.md` и проверьте `git status`.

## Научная цель

SLAVA расшифровывается как *Slot-Level Attribution for VLA*. Проект исследует
падение качества Vision-Language-Action моделей на неанглийских, в первую
очередь русских, инструкциях.

Главная гипотеза: action fine-tuning может не уничтожать понимание русского
языка полностью. Семантические слоты инструкции могут оставаться декодируемыми
во внутренних состояниях модели, но переставать причинно влиять на action head.
Это явление мы называем cross-lingual action-binding collapse.

Основные альтернативные объяснения:

- `H-understanding`: модель не извлекает смысл русской инструкции;
- `H-grounding`: смысл извлечён, но не связан с объектами и отношениями сцены;
- `H-binding`: смысл извлечён и заземлён, но action head его не использует.

Будущий экспериментальный план включает контролируемые EN/RU/code-switch
минимальные пары, behavioral evaluation, slot probes, oracle recovery curves,
pointing-vs-action comparisons, base-to-VLA causal patching и targeted repair.

## Текущий этап

Сейчас проект находится на environment-first этапе построения benchmark.
Сначала должны быть проверены реальные сцены симуляторов, изображения, объекты и
лексикон. Русские инструкции нельзя начинать до утверждения scene inventory,
screenshot review, object lexicon и selected-task manifest.

Правильный порядок работы:

```text
task + init state
→ RGB renders
→ реальные sim objects, handles и poses
→ ручная проверка видимости
→ object lexicon
→ отбор сцен
→ grounded semantic frames
→ EN/RU/code-switch variants
→ schema validation и native check
→ freeze v0
→ model rollouts
```

Уже собраны 102 candidate-сцены и их изображения. Следующие обязательные шаги:

1. закончить полный human review сцен;
2. заполнить `object_lexicon.csv`;
3. выбрать 20 сцен: ориентир 16 LIBERO + 4 SimplerEnv;
4. создать и утвердить `selected_tasks_v0.jsonl`;
5. только затем размечать frames и писать языковые варианты.

## Единица данных

Не смешивайте три разных сущности:

- `task` — исходная задача benchmark;
- `scene` — конкретный `task × init state`;
- `trajectory` или `rollout` — последовательность действий в сцене.

Одна строка inventory — одна воспроизводимая сцена, не траектория.

Candidate pool фиксирован:

| Источник | Задачи | Варианты | Сцен |
|---|---:|---:|---:|
| `libero_spatial` | 10 | init states `0, 17, 34` | 30 |
| `libero_object` | 10 | init states `0, 17, 34` | 30 |
| `libero_goal` | 10 | init states `0, 17, 34` | 30 |
| SimplerEnv Bridge | 4 | episode ids `0, 8, 16` | 12 |
| Всего | 34 | — | 102 |

`task_id` — индекс исходной задачи внутри suite. Он не является уникальным
идентификатором сцены. Полную сцену идентифицирует `task_uid` вместе с полями
воспроизводимости внутри `source`.

## Неизменяемые решения

- Candidate inventory содержит ровно 102 сцены: 90 LIBERO + 12 SimplerEnv.
- LIBERO использует только suites spatial/object/goal и init ids `0,17,34`.
- SimplerEnv использует четыре закреплённые `widowx_*` задачи и episode ids
  `0,8,16` при `reset_seed=0`.
- LIBERO рендерится сразу после `set_init_state`; `settle_steps` всегда равен 0.
- У используемого SimplerEnv WidowX нет wrist camera; `wrist_rgb` всегда `null`.
- При merge и regeneration нужно сохранять human review fields.
- Portable manifest не должен содержать машинно-зависимые пути вроде
  `/workspace/...`.
- Нельзя молча менять pinned commits или состав candidate pool.
- LIBERO HDF5 demonstrations не нужны collectors. Bootstrap загружает их только
  для будущей работы с моделями и траекториями.

## Воспроизводимость сред

Закреплённые внешние репозитории:

- LIBERO: `8f1084e3132a39270c3a13ebe37270a43ece2a01`;
- SimplerEnv: `06accaca93535902d408da4855f21cece12bceb7`.

Стандартная структура:

```text
parent-directory/
├── SLAVA_dev/
├── LIBERO/
└── SimplerEnv/
```

При другом расположении используется `SLAVA_DEPS_DIR`. Корни отдельных сред
можно задать через `LIBERO_ROOT` и `SIMPLERENV_ROOT`.

Три Conda-окружения намеренно разделены из-за несовместимых зависимостей:

| Окружение | Назначение | Python |
|---|---|---:|
| `slava-notebook` | notebook, pandas, widgets, JSONL/CSV | 3.11 |
| `slava-libero` | LIBERO, robosuite, MuJoCo | 3.8.13 |
| `slava-simpler` | SimplerEnv, SAPIEN | 3.10 |

Notebook запускает collectors через `conda run`; менять kernel между
симуляторами не нужно.

## Структура данных

```text
data/
├── libero_inventory.jsonl
├── simpler_inventory.jsonl
├── task_inventory.jsonl
├── object_lexicon.csv
├── screenshot_sheet_small.html
├── screenshot_sheet_full.html
├── collection_errors.jsonl       # только если были ошибки
└── images/
    ├── libero/
    └── simpler/
```

Все три inventory JSONL используют одну строгую схему v1.0:
[`schemas/task_inventory.schema.json`](schemas/task_inventory.schema.json).
Лишние поля запрещены. Верхний уровень каждой строки содержит ровно:

- `task_uid`: стабильный уникальный идентификатор сцены;
- `suite`, `task_id`, `canonical_en`: исходная задача и инструкция;
- `source`: среда, commit и source-specific metadata;
- `images`: пути относительно `data/`;
- `objects_raw`: sim handles, raw names, XYZ poses и видимость;
- `success_predicates`: проверяемые условия успеха;
- `candidate_slots`: будущие action/target/reference/relation;
- `usable_for_slava`, `notes`: человеческая оценка.

Для LIBERO `source` содержит `environment`, `commit`, `task_name`, `bddl_file`
и `init_state_id`. Для SimplerEnv он содержит `environment`, `commit`,
`task_name`, `gym_env_name`, `episode_id` и `reset_seed`.

Каждый элемент `objects_raw` содержит только `sim_handle`, `raw_name`,
`pose_xyz`, `visible_agentview` и `visible_wrist`. Выбор v0 и расширенная review
metadata не добавляются в inventory: они должны жить в отдельном
`selected_tasks_v0.jsonl`.

Допустимые значения `visible_agentview` и `visible_wrist`:

- `true`: объект уверенно виден;
- `"visible_partial"`: виден частично, но распознаваем;
- `false`: не виден или не распознаваем;
- `null`: ещё не проверен либо соответствующей камеры нет.

Source inventories являются выходами collectors. `task_inventory.jsonl` — их
объединение с сохраняемой человеческой разметкой.

Проверка всех inventory:

```bash
python scripts/validate_inventory.py
```

Collectors валидируют каждую запись до сохранения; merge и notebook export
валидируют весь набор. Поэтому legacy или случайные дополнительные поля не могут
незаметно вернуться в данные.

## Основные компоненты

- `scripts/bootstrap.sh`: установка сред и smoke tests;
- `scripts/collect_libero.py`: сбор 90 LIBERO-сцен;
- `scripts/collect_simpler.py`: сбор 12 SimplerEnv-сцен;
- `scripts/configure_libero.py`: неинтерактивная настройка LIBERO paths;
- `scripts/generate_screenshot_sheet.py`: HTML-визуализация inventory;
- `scripts/validate_inventory.py`: строгая проверка всех inventory;
- `src/slava_inventory/schema.py`: runtime validation и normalization;
- `src/slava_inventory/io_utils.py`: безопасная работа с JSONL/CSV и merge;
- `src/slava_inventory/notebook_ui.py`: формы visibility, scene и lexicon review;
- `notebooks/01_collect_and_review_inventory.ipynb`: главная точка ручной работы.

Collectors по умолчанию не перезаписывают существующие сцены. Не включайте
`OVERWRITE_EXISTING`, если не требуется полный повторный рендер. При повторном
merge сохраняются `usable_for_slava`, `notes`, `candidate_slots` и object
visibility.

## Object lexicon и выбор v0

`object_lexicon.csv` связывает сырые имена ассетов с английскими и русскими
названиями, цветами, синонимами и флагом `usable_v0`. Разные физические категории
нельзя объединять только из-за похожего перевода.

Сцена подходит для v0, если объекты хорошо видны, естественно называются
по-русски, имеют ясные target/reference и проверяемый success predicate. Наличие
distractors желательно для измерения wrong-object и negation failures.

Пилотный selected set должен содержать около 20 сцен: 16 LIBERO и 4
SimplerEnv. Финальный выбор делает пользователь после screenshot review.

## Следующие артефакты после отбора

После утверждения `selected_tasks_v0.jsonl` планируются:

- `frames_v0.jsonl` с grounded semantic slots;
- Tier-1 variants: `en_canonical`, `en_paraphrase`, `mt_russian`, `ru_literal`,
  `ru_free_order`, `ru_case_swap`, `ru_negation`, `code_switch`;
- `axis_na` с причиной для неприменимых осей;
- `validate_frames.py`;
- native check naturalness/equivalence/ambiguity;
- `export_prompts.py`;
- rollout logger и behavioral metrics.

Основная behavioral метрика будущего пилота:

```text
Δlang = gap(RU axis) − gap(EN paraphrase)
```

Она отделяет собственно языковой эффект от общей хрупкости к непривычной строке
инструкции.

## Правила работы агента

Перед изменениями:

1. прочитайте этот файл и `AGENTS.md`;
2. выполните `git status`;
3. учитывайте, что рабочее дерево может содержать изменения пользователя;
4. не уничтожайте и не сбрасывайте human annotations;
5. после изменений выполняйте проверки, пропорциональные риску.

Особенно важно сохранять и отправлять в Git `data/task_inventory.jsonl`,
`data/object_lexicon.csv` и `data/images`: локальные рендеры нельзя восстановить
обычным `git clone`, пока они не закоммичены.
