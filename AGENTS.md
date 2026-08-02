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

## Главный принцип: это VLA-бенчмарк

SLAVA строится как исследовательский benchmark для
Vision-Language-Action-моделей. При любой реализации и помощи пользователю
исходите из того, что итоговые данные будут связывать визуальное наблюдение,
языковую инструкцию и физическое действие робота.

Это означает:

- названия, атрибуты и инструкции должны описывать то, что VLA действительно
  может увидеть и связать с объектом в модельном RGB-входе;
- не добавляйте языковую или визуальную детализацию, которая не помогает
  выбрать объект, отношение или действие и не проверяется сценой;
- scene selection должен обеспечивать однозначный target, выполнимое действие,
  проверяемый success condition и диагностичные ошибки;
- варианты инструкций должны менять только исследуемую языковую ось, сохраняя
  сцену, задачу и ожидаемое действие контролируемыми;
- схемы и интерфейсы должны поддерживать воспроизводимость, парное сравнение
  инструкций и последующий анализ VLA rollout, а не только быть удобными как
  каталог объектов;
- решения по полям, квотам и валидации оценивайте по их пользе для научной
  валидности VLA-бенчмарка. Если общее software-решение конфликтует с
  benchmark design, явно покажите конфликт и сохраните научный смысл.

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
- редактируемый review видимости объектов (все сцены, все объекты, agent+wrist
  рендеры, статус можно менять прямо в браузере):
  [`data/visibility_review.html`](data/visibility_review.html);
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

## Что находится в `data/` и откуда брать данные

Используйте локальные артефакты в [`data/`](data/) до внешнего поиска или
догадок по имени объекта.

- [`data/task_inventory.jsonl`](data/task_inventory.jsonl) — основной
  объединенный inventory и источник истины. После завершения текущего
  расширения здесь должно быть 117 сцен. Здесь находятся
  `task_uid`, environment metadata, пути к изображениям, реальные sim handles,
  позы, ручная видимость, candidate slots, quota eligibility и решение по
  конкретной сцене `usable_for_slava`.
- [`data/libero_inventory.jsonl`](data/libero_inventory.jsonl) — collector output
  для 95 LIBERO-сцен. Используйте для диагностики и повторного merge, но не
  переносите его поверх human review из объединенного inventory.
- [`data/simpler_inventory.jsonl`](data/simpler_inventory.jsonl) — collector
  output; целевой план содержит 22 SimplerEnv-сцены. У WidowX нет wrist camera,
  поэтому
  `wrist_rgb` и `visible_wrist` остаются `null`.
- [`data/object_lexicon.csv`](data/object_lexicon.csv) — вручную редактируемый
  словарь типов ассетов. Он связывается с inventory по
  `objects_raw[].raw_name`. В нем находятся общий класс, semantic subtype,
  канонические EN/RU-названия, короткие визуальные атрибуты, цвет,
  recoverability, допустимый синоним и объектный `usable_v0`.
- [`data/images/libero/`](data/images/libero/) — реальные стартовые
  `agentview`- и `wrist`-рендеры LIBERO. Для VLA grounding они важнее
  предположений по `raw_name`: описывать нужно то, что действительно видно
  модели в этих изображениях.
- [`data/images/simpler/`](data/images/simpler/) — реальные стартовые
  `agentview`-рендеры SimplerEnv. Wrist-изображений здесь нет.
- [`data/HOPE_3D_models/`](data/HOPE_3D_models/) — исходные HOPE-модели
  продуктовых объектов: mesh, material и texture files. Используйте
  `*/google_16k/texture_map.png` для проверки цвета, формы упаковки, этикетки и
  metadata identity. Полноразмерная текстура не доказывает, что надпись читается
  на VLA-рендере; recoverability оценивайте по фактическим изображениям сцен.
- [`data/libero_bddl/`](data/libero_bddl/) — локальные BDDL-задачи LIBERO для
  suites `libero_spatial`, `libero_object` и `libero_goal`. Здесь можно
  проверить исходную английскую формулировку, состав объектов, regions,
  начальные размещения и success condition. BDDL задает семантику задачи, но не
  заменяет визуальную проверку по render.
- [`data/screenshot_sheet_small.html`](data/screenshot_sheet_small.html) —
  сгенерированный компактный review inventory × lexicon с фильтрами.
- [`data/screenshot_sheet_full.html`](data/screenshot_sheet_full.html) —
  сгенерированный полный просмотр всех inventory fields.

Последние два HTML-файла являются производными артефактами. Их нужно
пересобирать через [`scripts/generate_screenshot_sheet.py`](scripts/generate_screenshot_sheet.py),
а не редактировать вручную.

При проверке названия или описания объекта используйте порядок:

```text
реальный scene render
→ raw_name и sim_handle из task_inventory
→ BDDL task semantics
→ HOPE mesh/texture, если это HOPE-объект
→ только затем содержательное решение для lexicon
```

Для VLA не пишите каталожные описания. `visual_attributes_*` должны содержать
короткие признаки, которые видны на модельном входе и помогают отличить объект:
обычно основной цвет, форм-фактор и максимум один устойчивый различитель.

## Как не затирать изменения пользователя

Рабочее дерево считается совместным и может быть изменено пользователем между
любыми двумя сообщениями. Старое содержимое из контекста разговора не считается
актуальной копией файла.

Перед каждым изменением:

1. Выполните `git status --short`.
2. Для каждого затрагиваемого tracked-файла выполните точечный
   `git diff -- path/to/file` и при необходимости `git diff --cached -- path/to/file`.
3. Проверьте untracked-файлы: они также принадлежат пользователю и не являются
   временными только потому, что отсутствуют в Git.
4. Перечитайте актуальное содержимое файла непосредственно перед patch. Для
   CSV/JSONL дополнительно выведите затрагиваемые строки или записи по
   стабильному ключу (`raw_name`, `task_uid`).

Во время изменения:

- применяйте минимальный patch только к полям и строкам из запроса;
- не пересоздавайте целиком вручную редактируемый CSV, JSONL, notebook или
  Markdown-файл, если можно изменить несколько строк;
- сохраняйте все human review fields и неизвестные текущей задаче правки;
- не восстанавливайте файл из `HEAD`, старого tool output или памяти;
- если пользователь уже изменил те же поля и намерение нельзя надежно вывести
  из запроса, остановитесь и уточните, а не выбирайте одну версию молча;
- перед запуском генератора проверьте, какие производные файлы и каталоги он
  перезаписывает. Не запускайте широкую regeneration только ради несвязанной
  правки.

После изменения:

1. Снова просмотрите `git diff -- path/to/file`.
2. Убедитесь, что diff содержит только запрошенные изменения поверх уже
   существовавших правок.
3. Запустите релевантную валидацию, но не используйте formatter или генератор,
   который механически перепишет несвязанные пользовательские файлы.

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

- Канонический план candidate inventory содержит 117 сцен: 95 LIBERO и 22
  SimplerEnv. До выполнения дополнительного SimplerEnv-рендера локальные
  manifests могут временно содержать прежние 102 сцены; не создавайте
  недостающие строки без реального reset и RGB-render.
- LIBERO использует suites spatial/object/goal и базовые init ids `0, 17, 34`.
  Для `libero_spatial` task 2 дополнительно собраны init ids `1, 2, 3, 4, 5`,
  выбранные для покрытия spatial/surface и distractor-квот.
- SimplerEnv использует закрепленные `widowx_*` задачи и `reset_seed=0`.
  Базовые episode ids всех четырех задач — `0, 8, 16`; для
  `widowx_carrot_on_plate` и `widowx_stack_cube` дополнительно используются
  `1, 4, 12, 20, 23`.
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
- `quota_eligibility`;
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

`quota_eligibility` — фиксированная human-разметка применимости девяти квот v0.
Каждый признак принимает `true`, `false` или `null`; `null` означает, что
применимость еще не проверена. Поле сохраняется при merge/regeneration.

### Мнемонические правила разметки квот

Перед разметкой сверяйте `objects_raw`, BDDL или исходный success condition,
object lexicon и все доступные RGB-ракурсы. Название задачи само по себе
недостаточно. Используйте следующие операционные правила:

- `spatial_relation=true`, если инструкция проверяет отношение
  `left/right/on/next_to`. Не засчитывайте другие отношения вроде `front`,
  `between` или `in` только из-за их пространственной природы; `on` можно
  одновременно засчитать как `surface`, если выполнено правило этой квоты.
- `pick_with_distractors=true`, если робот должен выбрать переносимый target
  среди хотя бы одной видимой правдоподобной альтернативы. Простое наличие
  фоновых объектов не считается.
- `container=true`, если проверяемый результат — естественное
  `put X in drawer/bowl/basket/sink`.
- `surface=true`, если проверяемый результат — естественное
  `put X on plate/tray/table`. Стойки, полотенца и произвольные поверхности сюда
  не включаются.
- `has_distractor=true`, если есть видимый объект или однозначно различимая
  часть объекта, с которыми модель может выполнить правдоподобное, но
  проверяемо неправильное действие. Reference не становится distractor
  автоматически, но может быть неправильной альтернативой при выборе target.
- `same_category_distractor=true`, если такой distractor имеет ту же
  `category_en`, что target. Сравнивайте категорию по lexicon, а не по похожести
  цвета или упаковки.
- `same_color_distractor=true`, если у правдоподобного distractor совпадает
  основной `color_en` target и совпадение подтверждается render. Совпадения
  небольших деталей этикетки недостаточно.
- `ru_case_swap=true`, если target и reference — два физически используемых
  объекта, роли которых можно поменять, а обратная команда останется
  осмысленной, физически выполнимой и проверяемой. Два кубика обычно подходят;
  `предмет → корзина`, `морковь → тарелка` и другие явно асимметричные пары —
  нет.
- `ru_negation=true`, если можно естественно сформулировать `не X, а Y`, оба
  кандидата визуально заземлены, а действие с forbidden-кандидатом можно
  однозначно признать ошибкой. Наличие любого постороннего объекта для этого
  недостаточно.

Эти правила являются проектной памятью. Когда в ходе ручной разметки появляется
новое устойчивое мнемоническое правило, исключение или уточнение, агент должен
сразу записать его в `AGENTS.md`, чтобы следующую итерацию разметки можно было
повторить согласованно. Частные решения для одной сомнительной сцены сначала
помечайте в `notes`; не превращайте их в общее правило без повторяемого
основания.

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
с общим классом, семантическим подтипом, каноническими EN/RU-названиями,
визуальными атрибутами, цветом, допустимым русским синонимом и объектным
`usable_v0`.

Правила:

- `category_en/category_ru` — широкий класс или форм-фактор: `can/банка`,
  `bottle/бутылка`, `carton/пакет`;
- `semantic_subtype_en/semantic_subtype_ru` — содержимое или функциональный
  подтип из metadata: `tomato sauce/томатный соус`;
- `canonical_name_en/canonical_name_ru` — естественное полное имя объекта,
  используемое как основной кандидат для авторинга: `tomato sauce can/банка
  томатного соуса`;
- `visual_attributes_en/visual_attributes_ru` описывают наблюдаемые признаки
  независимо от semantic subtype: форма, основной цвет, этикетка, крышка;
- `semantic_identity_visually_recoverable` принимает `yes`, `no` или `review`
  и показывает, можно ли надежно восстановить semantic subtype по текущему
  визуальному облику ассета;
- `color_ru` согласуется с существительным в `canonical_name_ru`;
- `allowed_synonyms_ru` обозначает тот же физический объект, а не его содержимое
  или более широкую категорию;
- синоним нельзя механически соединять с `color_ru`, если у него другой род;
- в русских полях используется `е`, а не `ё`;
- похожий перевод не позволяет объединять разные физические категории.

`referring_strategy` не является полем object lexicon. Это решение для
конкретной инструкции/сцены: `semantic_subtype`, если подтип считывается в
данном ракурсе, либо `visual_attributes`, если надежнее сослаться на визуальные
признаки. Его нужно хранить в будущем instruction/selected-task manifest.

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
- validation: [`scripts/validate_inventory.py`](scripts/validate_inventory.py);
- редактируемый дашборд по object visibility:
  [`scripts/generate_visibility_review.py`](scripts/generate_visibility_review.py)
  → `data/visibility_review.html`, правки применяются через
  [`scripts/apply_visibility_review.py`](scripts/apply_visibility_review.py), а
  [`scripts/sync_selected_tasks_visibility.py`](scripts/sync_selected_tasks_visibility.py)
  прокидывает обновлённую видимость в `data/selected_tasks_v0.jsonl`.

После изменений выполняйте проверки, пропорциональные риску. Особенно берегите
`data/task_inventory.jsonl`, `data/object_lexicon.csv` и `data/images`: human
annotations и локальные рендеры нельзя восстанавливать ценой их перезаписи.
