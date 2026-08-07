---
name: slava-remote-scene-collection
description: Collect LIBERO/SimplerEnv scenes on a short-lived rented GPU box — minimal install recipe, parallelisation that actually helps, the traps that cost time (osmesa vs egl, forgotten collector script, backgrounding over ssh), and what must be pulled off the machine before it dies. Use when renting a server to render scenes or re-render an inventory, not for model rollouts.
---

# Сбор сцен на арендованном сервере

Записано 08.08.2026 после сбора 896 сцен за ~1.5 часа на vast.ai (RTX 2080 Ti,
32 ядра). Скил про **сцены**, не про роллауты: рендер инвентаря не требует ни
чекпойнтов, ни torch с GPU, и ставится втрое быстрее полного стенда.

Читайте вместе с `slava-model-rollouts` («Starting from nothing») — там общий
рецепт окружений; здесь только то, что специфично для сбора сцен под таймером.

## Порядок, проверенный на практике

Сервер живёт часы, поэтому длинные шаги запускаются первыми и параллельно
всему остальному.

1. **Сразу запустить установку LIBERO фоном** — это самый долгий шаг.
2. Пока ставится: посчитать план сбора локально (сколько сцен под квоты),
   заархивировать ненужное, подготовить скрипты.
3. Прогнать одну сцену как smoke test. **Не пропускать**: два дефекта ниже
   ловятся именно тут, а не после двадцати минут пустого прогона.
4. Запустить полный сбор параллельно.
5. **Качать инкрементально с первой минуты**, а не в конце.
6. Забрать всё, что не лежит в инвентаре (BDDL!), до смерти машины.

## Минимальная установка

Полный `bootstrap.sh` избыточен: он ставит torch с CUDA и model-серверы, а для
рендера сцен нужен только LIBERO с robosuite. `micromamba` вместо conda —
один бинарник, разворачивается за секунды.

```bash
curl -sL https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C /workspace bin/micromamba
export MAMBA_ROOT_PREFIX=/workspace/mamba
eval "$(/workspace/bin/micromamba shell hook -s posix)"
micromamba create -y -n libero python=3.8.13 -c conda-forge -q
micromamba activate libero
git clone https://github.com/Lifelong-Robot-Learning/LIBERO.git /workspace/LIBERO
cd /workspace/LIBERO && git checkout 8f1084e3132a39270c3a13ebe37270a43ece2a01
pip install torch==1.11.0 torchvision==0.12.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt && pip install -e .
python scripts/configure_libero.py --repo /workspace/LIBERO --config-dir /root/.libero
```

**CPU-torch, а не CUDA** — рендер идёт через MuJoCo, torch тут нужен только
чтобы LIBERO импортировался. Экономит несколько минут и гигабайты.

**`configure_libero.py` обязателен**: при первом импорте LIBERO спрашивает путь
к датасетам через `input()`, и в неинтерактивном ssh это падает с `EOFError`.

SimplerEnv ставится отдельным окружением (python 3.10, `pip install -e
ManiSkill2_real2sim`, затем `-e .`, затем пины `setuptools<81`,
`numpy==1.24.4`, `opencv-python<4.10`). Ставить его параллельно сбору LIBERO
безопасно: установка это сеть и диск, а сбор упирается в процессор.

## Три дефекта, которые стоили времени

**1. `MUJOCO_GL=osmesa` не работает — нужен `egl`.** На арендованной машине
OSMesa не установлен, и падение выглядит невнятно:
`AttributeError: 'NoneType' object has no attribute 'glGetError'`. Правильно:
`MUJOCO_GL=egl` и `MUJOCO_EGL_DEVICE_ID=0`. Для SimplerEnv переменная не нужна
— там SAPIEN.

**2. Отправлять надо ОБА сборщика.** Я упаковала `collect_libero.py` и забыла
`collect_simpler.py`; выяснилось это только когда четыре процесса упали с
`No such file or directory`, уже под конец аренды. Проверяйте `ls` на сервере
после распаковки, а не доверяйте `tar`.

**3. Фоновый запуск через ssh не переживает закрытие сессии.**
`ssh host 'nohup cmd &'` с `disown` молча не создал даже лог-файла. Что
работает надёжно: **держать ssh-сессию открытой со своей стороны** (у агента —
`run_in_background: true` на самом вызове ssh). Альтернатива — tmux на сервере,
но это лишний шаг под таймером.

## Параллелизм: как понять, помогает ли

Разбиение по процессу на **(сьют × задача)** естественно: каждый сборщик пишет
свой инвентарь, поэтому гонок за файл нет вовсе. Дублей тоже: сборщик при
старте читает свой инвентарь и пропускает уже собранные `task_uid`, так что
перезапуск недоделанной части безопасен.

**Не доверяйте `load average` при выборе числа процессов.** Это
экспоненциально сглаженное среднее, оно **отстаёт на минуты**. Я увидела
«6.14 при 32 ядрах», решила, что машина простаивает, подняла процессы с 16 до
26 — и получила прирост 43 → 52 сцены/мин, около 20%, а не вдвое. Реальный
load оказался 30.7, то есть мы уже упирались в CPU, а по каждому процессу
потребление упало с 31% ядра до 22%.

Мерьте **пропускную способность**, а не загрузку:

```bash
a=$(cat out/*/libero_inventory.jsonl | wc -l); sleep 60
b=$(cat out/*/libero_inventory.jsonl | wc -l); echo "$((b-a)) сцен/мин"
```

Узкое место — физика MuJoCo на CPU; GPU при этом был загружен на 8–18%, то
есть карта нужна только для EGL-контекста, и брать мощную незачем.

**Волны против «всё сразу».** Наивный драйвер с `wait` каждые N процессов
держит машину недогруженной в хвосте каждой волны. Лучше запускать все части
сразу; если драйвер уже работает волнами, его можно убить (`pkill -f
run_collect.sh`), не трогая запущенные сборщики — они осиротеют и доработают.

## Что забрать до смерти машины

Инвентарь и картинки очевидны. Неочевидное:

- **BDDL-файлы LIBERO.** Инвентарь хранит только *путь* внутрь репозитория
  (`source.bddl_file`), а сами файлы — часть клона. Без копии определения сцен
  умирают вместе с сервером. Забирать все задачи собираемых сьютов в
  `data/libero_bddl/`.
- **У SimplerEnv BDDL нет и не нужен** — сцена воспроизводится по
  `gym_env_name` + `episode_id` + `reset_seed` + пину коммита, всё в записи.
- **Версии окружения.** Пины из `bootstrap.sh` известны, а фактические версии
  внутри окружения — нет. Снимите `pip freeze`, если это важно; если не
  снимали, честно перечислите это в `not_recorded` провенанса.

Инкрементальная выкачка простым циклом `rsync` раз в минуту стоит дёшево и
превращает внезапную смерть машины из потери всего в потерю минуты:

```bash
while true; do
  rsync -az -e "ssh -p PORT" --exclude 'log.txt' root@HOST:/workspace/out/ data/incoming/
  n=$(cat data/incoming/*/libero_inventory.jsonl | wc -l); echo "$n сцен"
  [ "$n" -ge TARGET ] && break; sleep 60
done
```

## После приёмки — обязательные проверки

Дублей быть не должно **по построению**, но проверять всё равно: перезапуски
под таймером — как раз тот случай, когда «по построению» ломается.

```python
uids = [json.loads(l)["task_uid"] for l in open(inv)]
assert len(uids) == len(set(uids))           # дубли
assert all(r["source"]["settle_steps"] == 40 for r in rows)   # однородность
assert not [v for r in rows for v in r["images"].values() if v and not (base/v).exists()]
```

Отдельно: **если два `task_id` делят одно название задачи, их `task_uid`
совпадут и одна сцена молча затрёт другую.** В `libero_90` так и есть — 90
задач дают лишь 74 текста. В spatial/object/goal/10 названия уникальны.
Сверяйте ожидаемое число сцен с фактическим: расхождение означает схлопывание.

И запишите провенанс — `data/full_set/collection_provenance.json` как образец:
пины репозиториев, версии, правило сэмплирования, параметры рендера, счётчики,
достигнутая параллельность и явный список того, что зафиксировать не удалось.
