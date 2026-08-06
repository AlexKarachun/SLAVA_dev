# Архив: снимки таблицы аннотаций

Не прогоны, а состояния файла `rollout_annotations.jsonl` перед правками,
которые его переписывали. Кадры к ним живут в соответствующих пулах.

| Файл | Строк | Что было дальше |
| --- | --- | --- |
| `rollout_annotations.jsonl.bak_before_openvla_fix` | 69 | правка OpenVLA-OFT (post-processing гриппера, chunk replay, зеркалирование кадра, settle-шаги) — после неё SR вырос с нуля до 74.7% |
| `rollout_annotations.jsonl.bak_before_relabel` | 550 | пересчёт меток `failure_type_auto` существующих эпизодов (`scripts/relabel_rollouts.py`): часть эпизодов носила `unclear` из-за недостижимой ветки разметчика на SimplerEnv |
| `rollout_annotations.jsonl.bak_before_reset_fix_rerun` | 551 | пересбор lerobot-семейства после фикса сброса очереди действий; эпизоды до него — в `../lerobot_pre_reset_fix/` |

Годятся только для сверки истории правок. Считать по ним метрики нельзя: это
состояния до исправлений, а не независимые прогоны.
