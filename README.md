# SLAVA_dev

Этот репозиторий собирает воспроизводимый каталог робототехнических сцен из
[LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO) и
[SimplerEnv](https://github.com/simpler-env/SimplerEnv). Это не датасет
траекторий: одна строка inventory — одна конкретная сцена `task × init state`,
которую можно заново развернуть в симуляторе, показать человеку и позднее
использовать для запуска модели.

Главная точка входа —
[`notebooks/01_collect_and_review_inventory.ipynb`](notebooks/01_collect_and_review_inventory.ipynb).

## Быстрое восстановление на новом сервере

На машине должны быть Git, Conda/Miniforge и графические библиотеки, необходимые
MuJoCo/SAPIEN. На подготовленном Vast.ai image достаточно выполнить:

```bash
git clone https://github.com/AlexKrachun/SLAVA_dev.git
cd SLAVA_dev
bash scripts/bootstrap.sh
```

`bootstrap.sh` можно запускать повторно. Он:

1. клонирует рядом с `SLAVA_dev` зафиксированные версии LIBERO и SimplerEnv;
2. инициализирует submodules SimplerEnv;
3. создаёт три изолированных Conda-окружения;
4. устанавливает совместимые зависимости;
5. без интерактивных вопросов создаёт `~/.libero/config.yaml`;
6. проверяет импорты и рендерит по одной временной сцене каждого симулятора.

После этого в VS Code Remote SSH:

1. убедитесь, что расширения **Python** и **Jupyter** от Microsoft установлены
   именно на Remote SSH host;
2. откройте папку `SLAVA_dev` через **File → Open Folder**;
3. откройте `notebooks/01_collect_and_review_inventory.ipynb`;
4. нажмите **Select Kernel** в правом верхнем углу;
5. выберите **Python Environments → slava-notebook**.

Если VS Code не показывает окружение, узнайте точный путь к его Python:

```bash
conda run -n slava-notebook python -c "import sys; print(sys.executable)"
```

Затем в окне выбора kernel используйте **Enter interpreter path** и вставьте
полученный путь. Отдельно запускать `jupyter lab` на сервере не требуется.

По умолчанию структура будет такой:

```text
parent-directory/
├── SLAVA_dev/
├── LIBERO/
└── SimplerEnv/
```

Чтобы держать внешние репозитории в другом месте:

```bash
bash scripts/bootstrap.sh --deps-dir /path/to/robot-repositories
```

При нестандартном каталоге репозиториев перед запуском kernel добавьте в
удалённый shell/VS Code environment переменную
`SLAVA_DEPS_DIR=/path/to/robot-repositories`. При стандартной соседней структуре
она не нужна.

Для быстрой диагностики без тестового рендера есть `--skip-smoke-test`, но после
установки на новую машину лучше хотя бы один раз выполнить полный тест.

Скрипт скачивает исходный код, BDDL-описания, assets и фиксированные начальные
состояния. Большие LIBERO HDF5-файлы с демонстрационными траекториями для этой
задачи не нужны и не скачиваются.

## Почему три Conda-окружения

У LIBERO и SimplerEnv несовместимые версии Python и библиотек, поэтому они
намеренно не устанавливаются в kernel ноутбука:

| Окружение | Назначение | Python |
|---|---|---:|
| `slava-notebook` | pandas, IPython kernel, форма проверки, JSONL/CSV | 3.11 |
| `slava-libero` | LIBERO, robosuite, MuJoCo и рендер LIBERO | 3.8.13 |
| `slava-simpler` | SimplerEnv, ManiSkill2-real2sim и SAPIEN | 3.10 |

Ноутбук запускает collectors через `conda run`, поэтому переключать kernel
вручную между симуляторами не требуется. Для SimplerEnv после editable-install
специально восстанавливаются pins `setuptools<81`, `numpy==1.24.4` и
`opencv-python<4.10`: старый стек SAPIEN несовместим с NumPy 2.x и setuptools,
из которого удалён `pkg_resources`.

Предупреждения GLFW/X11 при headless-рендере допустимы, если smoke test завершился
строкой `Rendering smoke tests passed`. Ошибка EGL/GL или падение smoke test уже
означают, что образ сервера не поддерживает нужный off-screen renderer.

## Что именно собирается

Текущий candidate pool содержит 102 воспроизводимые сцены:

| Источник | Задачи | Варианты на задачу | Всего |
|---|---:|---:|---:|
| `libero_spatial` | 10 | init states `0, 17, 34` | 30 |
| `libero_object` | 10 | init states `0, 17, 34` | 30 |
| `libero_goal` | 10 | init states `0, 17, 34` | 30 |
| SimplerEnv Bridge | 4 | episode ids `0, 8, 16` | 12 |

В LIBERO задача задаётся BDDL-файлом, а конкретная расстановка — вектором из
набора fixed init states. Сцена сохраняется сразу после `set_init_state`, без
нулевых управляющих действий: `render.settle_steps` всегда равен `0`.

В SimplerEnv задача задаётся зарегистрированным `task_name`, а расстановка —
`episode_id` при фиксированном `reset_seed=0`. У используемого WidowX окружения
нет wrist camera, поэтому `images.wrist_rgb` там равен `null`.

Цель первого этапа — глазами проверить 102 кандидата, заполнить лексикон объектов
и выбрать первый сбалансированный v0-набор из 20 сцен: ориентир 16 LIBERO +
4 SimplerEnv. Русские инструкции и языковые вариации создаются только после
утверждения сцен и словаря объектов.

## Работа в ноутбуке

После запуска откройте `notebooks/01_collect_and_review_inventory.ipynb` и
выполняйте ячейки сверху вниз.

1. Конфигурация автоматически находит `SLAVA_dev` и соседние репозитории.
2. Collectors создают рендеры и source inventories. Безопасные defaults не
   запускают тяжёлую пересборку автоматически.
3. Merge создаёт `data/task_inventory.jsonl` и сохраняет уже внесённую человеком
   разметку при повторном сборе.
4. Форма показывает сцену и её объекты. Галочки обновляют поля пригодности,
   отбора и видимости в DataFrame.
5. Экспорт сохраняет DataFrame обратно в JSONL.
6. Отдельный блок создаёт/редактирует `data/object_lexicon.csv`.

Не включайте `OVERWRITE_EXISTING`, если не хотите заново рендерить все сцены.
`FAIL_FAST=True` удобно для диагностики первой ошибки; при обычной массовой
сборке `False` позволяет записать ошибки в `collection_errors.jsonl` и продолжить.

## Результаты и контракт данных

```text
data/
├── libero_inventory.jsonl
├── simpler_inventory.jsonl
├── task_inventory.jsonl
├── object_lexicon.csv
├── collection_errors.jsonl       # появляется только при ошибках
└── images/
    ├── libero/
    └── simpler/
```

Ключевые поля строки `task_inventory.jsonl`:

- `task_uid` — стабильный уникальный идентификатор сцены;
- `source.environment`, `source.commit` — симулятор и точная версия кода;
- `suite`, `task_name`, `task_id` — исходная задача;
- `bddl_file` + `init_state_id` — способ восстановить LIBERO-сцену;
- `gym_env_name`/`task_name` + `episode_id` + `reset_seed` — способ восстановить
  SimplerEnv-сцену;
- `images` — пути относительно каталога `data/`;
- `objects_raw`, `initial_predicates`, `success_predicates` — объекты и условия;
- `usable_for_slava`, `selected_for_v0`, `review_status`, `exclusion_reasons`,
  `notes` — ручная оценка;
- `candidate_slots` — будущие action/target/reference/relation для инструкции.

Для запуска не следует полагаться на абсолютный путь старого сервера. Корень
LIBERO берётся из `LIBERO_ROOT` (или `$SLAVA_DEPS_DIR/LIBERO`), корень SimplerEnv —
из `SIMPLERENV_ROOT` (или `$SLAVA_DEPS_DIR/SimplerEnv`), а `bddl_file` и пути к
изображениям хранятся относительно этих корней. Commit и hashes позволяют
убедиться, что восстановлена именно та сцена.

`object_lexicon.csv` связывает сырые имена симулятора с разрешёнными английскими
и русскими названиями/синонимами. Не объединяйте разные физические категории
только из-за похожего перевода: лексикон должен оставаться проверяемым.

## Контекст для следующего LLM-агента

Задача агента — помогать пользователю сформировать небольшой, воспроизводимый и
вручную проверенный scene inventory для SLAVA. Пользователь впервые работает с
робототехническими датасетами, поэтому изменения надо не только выполнять, но и
объяснять: чем task отличается от scene/init state и trajectory, как сцена
восстанавливается и какие поля обеспечивают воспроизводимость.

Уже принятые решения:

- единица inventory — `task × init state`, а не HDF5 trajectory;
- candidate pool — 90 LIBERO + 12 SimplerEnv;
- LIBERO: только suites spatial/object/goal и init ids `0,17,34`;
- SimplerEnv: четыре `widowx_*` задачи и episode ids `0,8,16`;
- никакие settle steps в LIBERO не выполняются;
- человеческая разметка обязана переживать повторный merge;
- сначала review сцен и object lexicon, затем v0 selection, затем язык;
- ориентир v0 — 20 сцен (16 LIBERO + 4 SimplerEnv), но финальный выбор делает
  пользователь после просмотра.

Перед правками агенту следует прочитать этот README и `AGENTS.md`, проверить
`git status`, не уничтожать ручную разметку и после изменений выполнить
пропорциональные тесты. Не следует молча менять pinned commits или состав 102
кандидатов.

## Перед удалением сервера

На этом Vast.ai instance `/workspace` не является persistent volume. Git clone
на новом сервере восстановит только то, что было закоммичено и отправлено на
GitHub. До удаления машины обязательно проверьте:

```bash
git status
git add README.md AGENTS.md requirements-notebook.txt scripts src notebooks data
git commit -m "Add reproducible SLAVA dataset bootstrap and inventory"
git push origin main
git status
```

Последний `git status` должен показать `working tree clean`, а commit должен быть
виден в GitHub. Особенно проверьте `data/task_inventory.jsonl`,
`data/object_lexicon.csv` и `data/images/`: без push локальные рендеры будут
безвозвратно потеряны вместе с сервером.
