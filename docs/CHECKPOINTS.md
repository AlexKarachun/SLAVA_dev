# Чекпойнты: что под какого робота существует

Этот файл существует, чтобы не переоткрывать один и тот же вопрос: **какую модель
в какой среде мы вообще имеем право запускать.** Все цифры ниже вычитаны из
самих чекпойнтов и из листингов организаций на HF, а не из статей и не по памяти.
Дата сверки — 2026-08-06.

## Сначала: у нас два разных робота, а не один

Это источник почти всей путаницы, поэтому вперёд всего остального.

| Среда | Симулятор | Робот | Действие |
| --- | --- | --- | --- |
| LIBERO | robosuite / MuJoCo | **Franka Emika Panda** (`libero/libero/envs/env_wrapper.py:16`, `robots=["Panda"]`) | 7 = 3 дельты позиции + 3 дельты ориентации + гриппер |
| SimplerEnv | ManiSkill2-real2sim / SAPIEN | **WidowX 250** (bridge) | 7 = 6 дельт схвата + гриппер |

Размерность у обоих семь — и это **совпадение формата, а не общее пространство**.
Кинематика, диапазоны и нормировка разные, поэтому политика, обученная под одного
из них, на другом не определена. «У нас мини-датасет по WidowX на LIBERO и на
SimplerEnv» — неверная формулировка: на LIBERO WidowX нет.

Отсюда следует главное правило: **клетка сетки существует тогда и только тогда,
когда под эту пару «модель × робот» опубликован чекпойнт.** Не когда среда
установлена и не когда модель формально «поддерживает манипуляцию».

## Сетка

Столбец «объявлено» — то, что чекпойнт пишет о себе сам
(`output_features.action` / `input_features.observation.state`), для lerobot-формата.
GreenVLA и OpenVLA-OFT в этом формате не лежат, у них прочерк.

| Модель | LIBERO (Panda) | SimplerEnv (WidowX) |
| --- | --- | --- |
| **GreenVLA-R0** | ✗ чекпойнта не существует | ✓ `SberRoboticsCenter/GreenVLA-5b-base-stride-1` |
| **GreenVLA-R1** | ✗ чекпойнта не существует | ✓ `SberRoboticsCenter/GreenVLA-5b-stride-1-R1-bridge` |
| **GreenVLA-R2** | ✗ чекпойнта не существует | ✓ `SberRoboticsCenter/GreenVLA-5b-stride-1-R2-bridge` |
| **OpenVLA-OFT** | ✓ `moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10` | ✗ чекпойнта не существует |
| **pi0** | ✓ `lerobot/pi0_libero_finetuned` — action 7, state 8 | ⚠ `lerobot/pi0_base` — action 32, state 32 (padded) |
| **pi0.5** | ✓ `lerobot/pi05_libero_finetuned` — action 7, state 8 | ⚠ `lerobot/pi05_base` — action 32, state 32 (padded) |
| **SmolVLA** | ✓ `HuggingFaceVLA/smolvla_libero` — action 7, state 8 | ✗ **чекпойнта не существует** |

Обозначения: ✓ дообучен под этого робота; ⚠ кросс-эмбодимент база, запуск
законен, но с оговоркой (ниже); ✗ запускать нечем.

### Почему у pi0/pi0.5 на WidowX стоит ⚠, а не ✗

`pi0_base` и `pi05_base` — настоящие кросс-эмбодимент базы: объявленные 32
измерения это zero-padded универсальное пространство, куда при обучении реальные
семь значений bridge клали в начало вектора и добивали нулями. Поэтому `action[:7]`
— точная обратная операция к `pad_vector()`, ровно та же, которую применяет
`BridgeOutputsTransform` у GreenVLA для того же робота. Запуск определён.

Оговорка, которую нельзя терять: **ни один из этих двух чекпойнтов не везёт
статистик нормализации вообще** (проверено через `make_pre_post_processors(...)`,
`NormalizerProcessorStep.stats`). Значит раскладка наблюдения — обоснованное
соглашение, а не проверяемый факт, и их zero-shot SR на bridge слабо
специфицирован независимо от любых багов. Это идёт в Limitations, а не
замалчивается.

### Почему у SmolVLA на WidowX стоит ✗

`lerobot/smolvla_base` — не кросс-эмбодимент база, а чекпойнт под руку SO-100.
Он объявляет `action (6,)` и `state (6,)`, а его постпроцессор везёт статистики
денормализации только под ключи `so100`, `so100-red`, `so100-blue`. Шесть
суставных координат SO-100 не превращаются в семимерную команду WidowX ни
обрезкой, ни добивкой нулями — это разные величины в разных единицах.

Проверяется в одну строку, и разница видна ровно по линии «дообучен на bridge /
не дообучен»: community-дообучения SmolVLA на BridgeData V2
(`Mohab921/smolvla_bridgev2_finetune`, `asatheesh/lerobot-smolvla-bridge`)
объявляют `action (7,)`. Официального такого чекпойнта нет — ни в `lerobot`,
ни в `HuggingFaceVLA`. Статья SmolVLA (arXiv 2506.01844) оценивает модель только
на LIBERO и Meta-World; SimplerEnv, WidowX и BridgeData V2 в ней не упоминаются
ни в оценке, ни в предобучении. Предобучение — 481 community-датасет,
преимущественно SO-100.

Заполнить клетку можно только чужим дообучением неизвестного качества или своим
на BridgeData V2. И то и другое выбивается из дизайна, где у всех остальных
моделей официальные чекпойнты авторов.

## Что из этого уже собрано

Пересчитывается из `rollouts/rollout_annotations.jsonl`.

| Модель | LIBERO | SimplerEnv |
| --- | --- | --- |
| GreenVLA-R0 | — | 28 / 28 ✓ |
| GreenVLA-R1 | — | 28 / 28 ✓ |
| GreenVLA-R2 | — | 28 / 28 ✓ |
| OpenVLA-OFT | 99 / 99 ✓ | — |
| pi0 | 99 / 99 (пересбор, см. ниже) | 28 — исключены |
| pi0.5 | 99 / 99 (пересбор, см. ниже) | 28 — исключены |
| SmolVLA | 99 / 99 (пересбор, см. ниже) | 15 — исключены |

Исключения объявлены в `data/rollout_provenance.json` с обоснованием и
применяются обоими генераторами отчётов. Итого 551 эпизод собран, 480 идут в
метрики.

Открытое по LIBERO: 297 эпизодов pi0, pi0.5 и SmolVLA собраны до фикса сброса
очереди действий (`/reset`, 2026-08-06). Контаминация течёт между вариантами
инструкции, то есть по измеряемой оси, поэтому их нужно пересобрать. Камеры и
вектор состояния у этих эпизодов уже правильные — это чинилось раньше и данные
после тех фиксов пересобраны.

## Сверка с task.md

Сетка из task.md («Модели и среды»):

- GreenVLA (R0-base + R1-bridge) → SimplerEnv/bridge
- OpenVLA-OFT → LIBERO
- π0 / π0.5 / SmolVLA → среда не указана

Наличие чекпойнтов **подтверждает этот план, а не противоречит ему**: GreenVLA
действительно только bridge, OpenVLA-OFT действительно только LIBERO. task.md
уже фиксирует, что сетка несимметрична, и требует сказать это в Limitations —
там же стоит план Б (LoRA-адаптация GreenVLA на LIBERO) как optional.

Единственное отклонение: SmolVLA на SimplerEnv мы пытались запустить, хотя
task.md этого не требовал. Клетка закрывается как «чекпойнта не существует».

## Как перепроверить, не доверяя этому файлу

Объявленные пространства (lerobot-формат):

```bash
curl -sL "https://huggingface.co/<repo>/raw/main/config.json" | python3 -c \
  "import json,sys; d=json.load(sys.stdin); print(d.get('output_features'), \
   {k:v for k,v in d['input_features'].items() if v['type']=='STATE'})"
```

Что вообще опубликовано организацией:

```bash
curl -s "https://huggingface.co/api/models?author=SberRoboticsCenter&limit=100" \
  | python3 -c "import json,sys; [print(m['modelId']) for m in json.load(sys.stdin)]"
```

Статистики нормализации (нужно окружение `slava-lerobot`) — через
`make_pre_post_processors(cfg, pretrained_path=...)` и `.steps[0].stats`.

## Источники

- Листинги организаций на HF: `SberRoboticsCenter`, `moojink`, `HuggingFaceVLA`,
  `lerobot` (сверено 2026-08-06)
- `config.json` каждого чекпойнта из таблицы
- SmolVLA: [arXiv 2506.01844](https://arxiv.org/html/2506.01844v1)
- LIBERO-робот: `libero/libero/envs/env_wrapper.py:16`
- WidowX-робот: `ManiSkill2_real2sim/agents/robots/widowx.py`
- Раскладка камер и состояния под каждое семейство:
  `.claude/skills/slava-lerobot-policies/SKILL.md`
