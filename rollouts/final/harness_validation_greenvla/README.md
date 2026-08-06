# Пул `harness_validation_greenvla` — валидация стенда на полном bridge-наборе

66 эпизодов: три модели GreenVLA × 22 сцены SimplerEnv, **только**
`en_canonical`. Единственный вопрос этого пула — воспроизводим ли мы числа,
которые авторы публикуют о своих чекпойнтах. Никаких языковых сравнений здесь
нет и быть не может: вариант один.

## Что запускалось

Промпты — `data/full_set/prompts_simpler_en.jsonl`, сгенерированы
`scripts/export_prompts_simpler_en.py` из `data/full_set/simpler_inventory.jsonl`
(собранного с `--settle-steps 40`). Четыре bridge-задачи:
`widowx_stack_cube` (8 сцен), `widowx_carrot_on_plate` (8),
`widowx_spoon_on_towel` (3), `widowx_put_eggplant_in_basket` (3).

```bash
python scripts/export_prompts_simpler_en.py
SLAVA_RUN_POOL=harness_validation_greenvla \
conda run -n slava-notebook python scripts/run_rollouts.py \
  --models greenvla_r0 greenvla_r1_bridge greenvla_r2_bridge \
  --variants en_canonical --prompts data/full_set/prompts_simpler_en.jsonl \
  --num-shards 2 --shard-index 0     # второй шард — index 1, вторая GPU
```

Зачем отдельно от пилота: все четыре SimplerEnv-сцены пилота — это одна задача
`widowx_stack_cube`, самая тяжёлая из четырёх, а публикуемые авторами средние
считаются по всем четырём. Сравнение шло между разными наборами задач.

## Железо и параметры

Арендованный инстанс vast.ai, **2×RTX 3090 (Ampere, cc 8.6)**, 07.08.2026.
Ampere — значит берётся собственный `dtype` чекпойнта, обходные пути для Volta
не применялись. Два шарда `run_rollouts.py`, по одному на карту, с разведёнными
портами env-воркера и model-сервера. Логи обоих шардов — `logs/`.

## Результат

```
              stack_cube  carrot  spoon  eggplant   всего    заявлено
GreenVLA-R0      0/8       0/8     0/3     0/3      0/22       33.3%
GreenVLA-R1      1/8       1/8     1/3     2/3      5/22       72.9%
GreenVLA-R2      2/8       3/8     0/3     0/3      5/22       80.5%
```

Разбор — `docs/HARNESS_VALIDATION.md`.

## Достоверность

- **Успех берётся из симулятора** (`info["success"]` у ManiSkill), а не из
  нашей авторазметки. Поэтому число сопоставимо с авторским и не зависит от
  открытого вопроса о точности `auto_label.py`. Поля `failure_type_auto` в
  аннотациях присутствуют, но здесь они не несут нагрузки.
- Ни одна из трёх моделей не воспроизвела опубликованное число.
- **12 `run_id` этого пула совпадают с пилотными** — те же сцены
  `widowx_stack_cube`, снятые второй раз на другом железе. Совпало 9 исходов из
  12. Это измерение шума, а не ошибка; но файлы аннотаций двух пулов
  склеивать нельзя (см. `rollouts/RUNS.md`).
