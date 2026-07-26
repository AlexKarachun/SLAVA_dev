# SLAVA_dev: контекст и инструкции для агентов

Это единый handoff по проекту. Перед изменениями прочитайте файл полностью,
затем [`README.md`](README.md), проверьте `git status` и изучите затрагиваемые
данные и код. Рабочее дерево может содержать незавершенные изменения
пользователя — сохраняйте их и не сбрасывайте.

Новые прямые пожелания пользователя имеют приоритет над рабочими предпочтениями
из этого файла. Если пользователь меняет прежнее решение, не защищайте старый
процесс ради процесса: адаптируйте реализацию, а связанные schema, документацию,
валидаторы и артефакты приведите в согласованное состояние. Неизменяемые
научные или data-contract решения меняйте только осознанно и явно.

## Как помогать пользователю

Пользователь ведет исследовательский проект и предпочитает совместную,
практическую работу.

- По умолчанию общайтесь по-русски.
- Сначала сообщайте конкретный результат или диагноз, затем необходимые детали.
- Объясняйте поля и решения на реальных примерах из SLAVA, а не только
  абстрактными определениями.
- Для ручной разметки предпочитайте удобные визуальные интерфейсы: карточки,
  изображения, фильтры, счетчики, checkbox dashboard.
- Если два интерфейса показывают разные результаты, программно сравните их на
  одних данных и устраните расхождение в источнике, а не объясняйте его
  предположениями.
- Для запросов на изменение реализуйте и проверяйте результат самостоятельно,
  если не требуется новое содержательное решение пользователя.
- Если выбор действительно влияет на научный смысл или ломает data contract,
  кратко покажите конфликт и предложите безопасный вариант. Не добавляйте
  дублирующее поле только ради похожего названия.
- По запросу давайте готовые, scoped команды `git add`, `git commit` и
  `git push`. Не включайте в `git add` посторонние пользовательские изменения.
- Не перегружайте ответ внутренними шагами. Указывайте измененные файлы,
  проверенный результат и существенные ограничения.
- В русских полях [`data/object_lexicon.csv`](data/object_lexicon.csv)
  используется `е`, а не `ё`. Это локальное правило лексикона, не обязательный
  стиль всей переписки или документации.

Эти предпочтения не являются жестким интерфейсным контрактом. Следуйте более
свежим пожеланиям пользователя по стилю, процессу и форме результата.

## Источники истины

Не дублируйте быстро меняющиеся статусы в документации без необходимости.
Проверяйте фактическое состояние здесь:

- candidate scenes и human scene review:
  [`data/task_inventory.jsonl`](data/task_inventory.jsonl);
- object names и объектный `usable_v0`:
  [`data/object_lexicon.csv`](data/object_lexicon.csv);
- визуальный review:
  [`data/screenshot_sheet_small.html`](data/screenshot_sheet_small.html),
  [`data/screenshot_sheet_full.html`](data/screenshot_sheet_full.html);
- интерактивный review и top-20 selection:
  [`notebooks/01_collect_and_review_inventory.ipynb`](notebooks/01_collect_and_review_inventory.ipynb);
- canonical inventory contract:
  [`schemas/task_inventory.schema.json`](schemas/task_inventory.schema.json);
- подробный research и benchmark plan: [`task.md`](task.md);
- deployment и pinned dependencies: [`scripts/bootstrap.sh`](scripts/bootstrap.sh).

Текущая работа находится на environment-first этапе: candidate inventory,
рендеры и lexicon используются для ручного отбора сцен. Русский instruction
authoring начинается только после утверждения scene review, lexicon и
selected-task manifest. Готовность этапа определяйте по артефактам, а не по
устаревающему текстовому счетчику.

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

Экспериментальный дизайн, behavioral metrics, probes, oracle ladder, causal
patching и repair plan описаны в [`task.md`](task.md).

## Порядок построения benchmark

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

Не начинайте русский instruction authoring до утверждения scene inventory,
screenshot review, object lexicon и selected-task manifest.

## Единица данных

Не смешивайте:

- `task` — исходную задачу benchmark;
- `scene` — конкретный `task × init state`;
- `trajectory` или `rollout` — последовательность действий в сцене.

Одна строка inventory — одна воспроизводимая сцена, не траектория. `task_id`
индексирует задачу внутри suite и сам по себе не идентифицирует сцену.
Стабильный идентификатор — `task_uid` вместе с reproducibility metadata в
`source`.

## Неизменяемые решения

- Candidate inventory содержит 102 сцены: 90 LIBERO и 12 SimplerEnv.
- LIBERO использует suites spatial/object/goal и init ids `0, 17, 34`.
- SimplerEnv использует закрепленные `widowx_*` задачи и episode ids
  `0, 8, 16` при `reset_seed=0`.
- LIBERO рендерится сразу после `set_init_state`; `settle_steps` остается 0.
- У используемого SimplerEnv WidowX нет wrist camera; `wrist_rgb` остается
  `null`. В визуальных фильтрах отсутствие камеры трактуется как `N/A`, а не как
  невидимость.
- При merge и regeneration сохраняются human review fields.
- Portable manifest хранит repository-relative paths и pinned commits, но не
  машинно-зависимые пути вроде `/workspace/...`.
- Pinned commits и candidate pool нельзя менять молча. Commits установки заданы
  в [`scripts/bootstrap.sh`](scripts/bootstrap.sh), commits записей — в
  `source.commit`.
- LIBERO HDF5 demonstrations не нужны scene collectors. Bootstrap загружает их
  для будущей model/trajectory работы.

Если пользователь явно решает изменить один из этих пунктов, оформите это как
согласованную миграцию: код, schema, данные, validation и документация должны
измениться вместе.

## Canonical inventory contract

Все source и merged inventories обязаны проходить
[`schemas/task_inventory.schema.json`](schemas/task_inventory.schema.json).
Лишние ad-hoc поля запрещены.

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
`visible_agentview` и `visible_wrist`. Visibility принимает:

- `true` — уверенно виден;
- `"visible_partial"` — частично виден, но распознаваем;
- `false` — не виден или не распознаваем;
- `null` — не проверен либо камеры нет.

Не смешивайте два уровня пригодности:

- `object_lexicon.csv: usable_v0` — подходит ли категория физического объекта;
- `task_inventory.jsonl: usable_for_slava` — human decision для конкретной
  сцены.

Выбор финального v0 set и расширенная selection metadata должны жить в
selected-task manifest согласно [`task.md`](task.md), а не в случайных новых
inventory fields.

Проверка:

```bash
python scripts/validate_inventory.py
```

Collectors валидируют записи до сохранения. Не включайте `OVERWRITE_EXISTING`
без необходимости полного ререндера. Merge должен сохранять
`usable_for_slava`, `notes`, `candidate_slots` и object visibility.

## Object lexicon

[`data/object_lexicon.csv`](data/object_lexicon.csv) связывает `raw_name` ассета
с каноническими EN/RU-названиями, цветом, допустимым русским синонимом и
объектным `usable_v0`.

Правила:

- `category_ru` — основное имя для авторинга;
- `color_ru` согласуется с `category_ru`;
- `allowed_synonyms_ru` обозначает тот же физический объект, а не его содержимое
  или более широкую категорию;
- синоним нельзя механически соединять с `color_ru`, если у него другой род;
- в русских полях используется `е`, а не `ё`;
- похожий перевод не позволяет объединять разные физические категории.

Small screenshot sheet объединяет inventory и lexicon. Фильтр `usable_v0`
учитывает все `objects_raw`, включая фоновые объекты, поэтому он является
диагностикой, а не единственным правилом выбора сцены.

Dashboard и screenshot sheet при одинаковых фильтрах обязаны возвращать
одинаковый набор `task_uid`. Для SimplerEnv wrist-filter пропускается как `N/A`.
При изменении filter semantics добавьте программную проверку их эквивалентности.

## Основные точки входа

- collectors: [`scripts/collect_libero.py`](scripts/collect_libero.py),
  [`scripts/collect_simpler.py`](scripts/collect_simpler.py);
- merge и safe JSONL/CSV I/O:
  [`src/slava_inventory/io_utils.py`](src/slava_inventory/io_utils.py);
- schema runtime:
  [`src/slava_inventory/schema.py`](src/slava_inventory/schema.py);
- notebook UI:
  [`src/slava_inventory/notebook_ui.py`](src/slava_inventory/notebook_ui.py);
- HTML review:
  [`scripts/generate_screenshot_sheet.py`](scripts/generate_screenshot_sheet.py);
- validation: [`scripts/validate_inventory.py`](scripts/validate_inventory.py).

После изменений выполняйте проверки, пропорциональные риску. Особенно берегите
`data/task_inventory.jsonl`, `data/object_lexicon.csv` и `data/images`: human
annotations и локальные рендеры нельзя восстанавливать ценой их перезаписи.
