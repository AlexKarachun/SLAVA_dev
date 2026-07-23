# SLAVA_dev

SLAVA (*Slot-Level Attribution for VLA*) — исследовательский проект о том, как
VLA-модели понимают и исполняют инструкции на русском языке.


## Развёртывание на сервере

На машине должны быть установлены Git, Conda/Miniforge и графические библиотеки
для MuJoCo/SAPIEN.

```bash
git clone https://github.com/AlexKrachun/SLAVA_dev.git
cd SLAVA_dev
bash scripts/bootstrap.sh
```



## Screenshot sheet

```bash
python scripts/generate_screenshot_sheet.py --mode small\
python scripts/generate_screenshot_sheet.py --mode full\
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
