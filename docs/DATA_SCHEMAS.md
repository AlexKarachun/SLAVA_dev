# Схемы данных SLAVA

Этот файл описывает актуальные контракты:

- [`data/object_lexicon.csv`](../data/object_lexicon.csv) — словарь физических
  типов объектов;
- [`data/task_inventory.jsonl`](../data/task_inventory.jsonl) — список
  воспроизводимых сцен.

Машиночитаемая строгая схема inventory находится в
[`schemas/task_inventory.schema.json`](../schemas/task_inventory.schema.json).
Список и порядок колонок lexicon задаются константой `LEXICON_COLUMNS` в
[`src/slava_inventory/io_utils.py`](../src/slava_inventory/io_utils.py).

## Как связаны lexicon и inventory

```text
task_inventory.jsonl
  objects_raw[].raw_name
            │
            └── object_lexicon.csv.raw_name
```

`objects_raw[].raw_name` используется как ключ соединения. Один тип ассета
имеет одну строку lexicon, но может встречаться во многих сценах и иметь разные
`sim_handle`, позы и значения видимости.

Важно различать:

- `object_lexicon.csv:usable_v0` — пригоден ли тип объекта для v0;
- `task_inventory.jsonl:usable_for_slava` — пригодна ли конкретная сцена;
- `task_inventory.jsonl:quota_eligibility` — какие квоты можно реализовать в
  конкретной сцене.

## Object lexicon

### Формат

Lexicon хранится в CSV с UTF-8-кодировкой. Одна строка соответствует одному
уникальному `raw_name`. Порядок колонок является частью контракта:

```csv
raw_name,category_en,category_ru,semantic_subtype_en,semantic_subtype_ru,canonical_name_en,canonical_name_ru,visual_attributes_en,visual_attributes_ru,semantic_identity_visually_recoverable,color_en,color_ru,allowed_synonyms_ru,usable_v0,notes
```

Пример:

```csv
tomato_sauce,can,банка,tomato sauce,томатный соус,tomato sauce can,банка томатного соуса,red cylindrical can with a tomato label,красная цилиндрическая банка с этикеткой с помидором,no,red,красная,консервная банка с томатным соусом,yes,
```

### Поля lexicon

| Поле | Обязательное | Что хранится |
| --- | --- | --- |
| `raw_name` | да | Стабильное имя типа ассета из среды. Это ключ строки и внешний ключ для `objects_raw[].raw_name`. Например, `tomato_sauce`. |
| `category_en` | да | Широкий класс или форм-фактор на английском: `can`, `bottle`, `carton`, `cube`. |
| `category_ru` | да | Тот же широкий класс по-русски: `банка`, `бутылка`, `пакет`, `кубик`. |
| `semantic_subtype_en` | да | Конкретный семантический подтип или содержимое из metadata на английском: `tomato sauce`, `milk`, `barbecue sauce`. |
| `semantic_subtype_ru` | да | Тот же семантический подтип по-русски: `томатный соус`, `молоко`, `соус барбекю`. |
| `canonical_name_en` | да | Естественное полное английское название объекта, основной кандидат для инструкции: `tomato sauce can`. |
| `canonical_name_ru` | да | Естественное полное русское название объекта: `банка томатного соуса`. |
| `visual_attributes_en` | да | Наблюдаемые визуальные признаки на английском: форма, цвет, крышка, этикетка и другие устойчивые детали. Не должно требовать знания содержимого упаковки. |
| `visual_attributes_ru` | да | То же визуальное описание по-русски. Например, `красная цилиндрическая банка с этикеткой с помидором`. |
| `semantic_identity_visually_recoverable` | да | Можно ли надежно определить `semantic_subtype` по облику ассета. Допустимо: `yes`, `no`, `review`. Это prior для ассета; окончательное решение зависит и от ракурса сцены. |
| `color_en` | нет | Краткое обозначение основного цвета на английском. Сохранено отдельно для фильтров и color-binding тестов. |
| `color_ru` | нет | Согласованная русская форма цвета для `canonical_name_ru`, например `красная`. |
| `allowed_synonyms_ru` | нет | Разрешенный русский синоним того же физического объекта. Не более широкий класс и не только название содержимого. |
| `usable_v0` | да | Решение о пригодности типа объекта: `yes`, `no` или `review`. |
| `notes` | нет | Свободный комментарий о переводе, визуальной неоднозначности или ограничениях использования. |

В русских полях lexicon используется `е`, а не `ё`.

### `semantic_identity_visually_recoverable` и `referring_strategy`

Эти понятия связаны, но находятся на разных уровнях:

- `semantic_identity_visually_recoverable` — характеристика ассета в lexicon;
- `referring_strategy` — решение для конкретной будущей инструкции и сцены.

Предполагаемые значения `referring_strategy`:

- `semantic_subtype` — объект называем по семантическому типу, например
  `банка томатного соуса`;
- `visual_attributes` — объект называем по наблюдаемым признакам, например
  `красная банка с этикеткой с помидором`.

`referring_strategy` пока не входит ни в lexicon, ни в inventory. Его следует
добавить в контракт selected-task/instruction manifest на этапе авторинга
инструкций.

## Task inventory v1.1

### Формат JSONL

Inventory хранится в JSONL: каждая строка файла является отдельным полноценным
JSON-объектом. Одна запись означает одну воспроизводимую сцену
`task × init state`, а не задачу вообще и не rollout/trajectory.

Все перечисленные поля обязательны. Неизвестные дополнительные поля строгой
схемой запрещены.

```json
{
  "task_uid": "libero_spatial__put_the_cream_cheese_in_the_bowl__init000",
  "suite": "libero_spatial",
  "task_id": 3,
  "canonical_en": "put the cream cheese in the bowl",
  "source": {
    "environment": "LIBERO",
    "commit": "8f1084e3132a39270c3a13ebe37270a43ece2a01",
    "task_name": "put_the_cream_cheese_in_the_bowl",
    "bddl_file": "libero/libero/bddl_files/libero_spatial/example.bddl",
    "init_state_id": 0
  },
  "images": {
    "agentview_rgb": "images/libero/example_agentview.png",
    "wrist_rgb": "images/libero/example_wrist.png"
  },
  "objects_raw": [
    {
      "sim_handle": "cream_cheese_1",
      "raw_name": "cream_cheese",
      "pose_xyz": [0.1, -0.2, 0.9],
      "visible_agentview": true,
      "visible_wrist": "visible_partial"
    },
    {
      "sim_handle": "akita_black_bowl_1",
      "raw_name": "akita_black_bowl",
      "pose_xyz": [0.2, -0.1, 0.9],
      "visible_agentview": true,
      "visible_wrist": true
    }
  ],
  "success_predicates": [],
  "candidate_slots": {
    "action": "place",
    "target": "cream_cheese_1",
    "reference": "akita_black_bowl_1",
    "relation": "in",
    "forbidden_candidates": []
  },
  "quota_eligibility": {
    "spatial_relation": false,
    "pick_with_distractors": false,
    "container": true,
    "surface": false,
    "has_distractor": false,
    "same_category_distractor": false,
    "same_color_distractor": false,
    "ru_case_swap": false,
    "ru_negation": false
  },
  "usable_for_slava": null,
  "notes": ""
}
```

### Верхний уровень

| Поле | Тип | Что хранится |
| --- | --- | --- |
| `task_uid` | `string` | Стабильный уникальный идентификатор сцены. Включает задачу и конкретный init/episode. |
| `suite` | `string` | Набор задач: например, `libero_spatial`, `libero_object`, `libero_goal`, `simpler_bridge`. |
| `task_id` | `integer` | Индекс исходной задачи внутри suite. Не идентифицирует сцену без `task_uid`. |
| `canonical_en` | `string` | Исходная каноническая английская инструкция среды. |
| `source` | `object` | Данные для воспроизведения сцены. Структура зависит от `environment`. |
| `images` | `object` | Репозиторные пути к стартовым RGB-рендерам. |
| `objects_raw` | `array<object>` | Реальные физические объекты сцены, их handles, начальные позы и ручная оценка видимости. |
| `success_predicates` | `array` | Исходные условия успеха среды. В v1.1 внутренний формат элементов намеренно не ограничен JSON Schema. |
| `candidate_slots` | `object` | Предварительное заземление ролей инструкции на sim handles. Может быть не заполнено во время review. |
| `quota_eligibility` | `object` | Ручная оценка применимости девяти квот v0 для этой сцены. |
| `usable_for_slava` | `boolean \| null` | Решение по сцене: `true` — допущена, `false` — исключена, `null` — еще не проверена. |
| `notes` | `string` | Свободный комментарий о конкретной сцене. |

### `source` для LIBERO

| Поле | Тип | Что хранится |
| --- | --- | --- |
| `environment` | `"LIBERO"` | Дискриминатор варианта `source`. |
| `commit` | `string` | Закрепленный Git commit среды, с которым сцена воспроизводится. |
| `task_name` | `string` | Каноническое имя задачи LIBERO. |
| `bddl_file` | `string` | Репозиторно-относительный путь к BDDL-файлу задачи. Абсолютные машинные пути запрещены. |
| `init_state_id` | `integer` | Индекс начального состояния внутри задачи. |

### `source` для SimplerEnv

| Поле | Тип | Что хранится |
| --- | --- | --- |
| `environment` | `"SimplerEnv"` | Дискриминатор варианта `source`. |
| `commit` | `string` | Закрепленный Git commit SimplerEnv. |
| `task_name` | `string` | Внутреннее стабильное имя задачи проекта. |
| `gym_env_name` | `string` | Зарегистрированное Gym environment name. |
| `episode_id` | `integer` | Выбранный episode/init-state identifier. |
| `reset_seed` | `integer` | Seed, переданный при reset среды. |

### `images`

| Поле | Тип | Что хранится |
| --- | --- | --- |
| `agentview_rgb` | `string` | Обязательный repository-relative путь к изображению с основной камеры. |
| `wrist_rgb` | `string \| null` | Путь к wrist-изображению. Для используемого SimplerEnv WidowX всегда `null`, потому что камеры нет. |

### `objects_raw[]`

| Поле | Тип | Что хранится |
| --- | --- | --- |
| `sim_handle` | `string` | Уникальный handle конкретного экземпляра объекта в этой сцене, например `cream_cheese_1`. Используется в semantic slots и predicates. |
| `raw_name` | `string` | Тип ассета без индекса экземпляра, например `cream_cheese`. Используется для соединения с lexicon. |
| `pose_xyz` | `[number, number, number]` | Начальная мировая позиция объекта `[x, y, z]`. Это не orientation и не полный pose. |
| `visible_agentview` | visibility | Результат ручной проверки объекта на основной камере. |
| `visible_wrist` | visibility | Результат ручной проверки объекта на wrist-камере. Для SimplerEnv WidowX всегда `null`. |

Допустимые visibility-значения:

| Значение | Смысл |
| --- | --- |
| `true` | Объект уверенно виден и распознаваем. |
| `"visible_partial"` | Объект виден частично, но остается распознаваемым. |
| `false` | Объект не виден или недостаточно распознаваем. |
| `null` | Видимость еще не проверена либо соответствующей камеры нет. |

Технические dummy-объекты в `objects_raw` запрещены.

### `candidate_slots`

Поля `target`, `reference` и `forbidden_candidates` содержат `sim_handle`, а не
`raw_name`, потому что они указывают на конкретный экземпляр объекта в сцене.

| Поле | Тип | Что хранится |
| --- | --- | --- |
| `action` | `string \| null` | Нормализованное действие-кандидат: например, `pick`, `place`, `open`, `push`, `stack`. |
| `target` | `string \| null` | Handle объекта, над которым робот должен выполнить основное действие. |
| `reference` | `string \| null` | Handle объекта или области, относительно которых задано целевое положение/отношение. |
| `relation` | `string \| null` | Нормализованное отношение: например, `in`, `on`, `left_of`, `right_of`, `next_to`. |
| `forbidden_candidates` | `array<string>` | Handles реально присутствующих объектов, которые могут служить неправильными альтернативами target. Пустой список означает, что кандидаты пока не указаны или отсутствуют. |

### `quota_eligibility`

Каждое поле имеет тип `boolean | null`:

- `true` — квоту можно честно реализовать в сцене;
- `false` — квота неприменима;
- `null` — применимость еще не проверена.

| Поле | Что означает `true` |
| --- | --- |
| `spatial_relation` | Сцена подходит для задачи с отношением `left/right/on/next_to`. |
| `pick_with_distractors` | Можно проверить выбор правильного объекта среди distractors. |
| `container` | Есть естественная задача `put X in drawer/bowl/basket/sink`. |
| `surface` | Есть естественная задача `put X on plate/tray/table`. |
| `has_distractor` | В сцене есть хотя бы один правдоподобный неправильный объект. |
| `same_category_distractor` | Есть distractor той же общей категории, что и target, например две бутылки или два кубика. |
| `same_color_distractor` | Есть distractor того же цвета, что и target. |
| `ru_case_swap` | Есть два разных объекта с физически обратимыми ролями target/reference; после перестановки ролей обратная команда остается осмысленной и проверяемой. |
| `ru_negation` | Есть реальный forbidden object, позволяющий естественную конструкцию `не X, а Y`; выбор forbidden можно однозначно считать ошибкой. |

## Проверка данных

Inventory:

```bash
python scripts/validate_inventory.py
```

Lexicon проверяется при сохранении из notebook UI и при запуске HTML-генераторов:

```bash
python scripts/generate_screenshot_sheet.py --mode small
python scripts/generate_selected_scenes.py
```

