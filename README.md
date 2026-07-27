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
