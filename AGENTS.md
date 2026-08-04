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

## Текущее состояние проекта (актуализируется агентом)

Этот раздел — единственный persistent handoff по текущему шагу работы: если
пользователь в начале нового чата попросит просто прочитать `AGENTS.md`, весь
нужный контекст должен быть здесь, а не в отдельном файле-снапшоте (`expl.md`
существовал раньше именно как такой файл и был сознательно удалён —
предполагается, что этот раздел заменяет его целиком, без отдельного
handoff-файла). Актуальность этого раздела важнее его краткости.

**Этап:** D4 закрыт и заморожен (tag `slava-pilot-v0`, коммит `113e531`) —
grounded semantic frames + instruction variants готовы, после закрытого D3
(`data/selected_tasks_v0.jsonl`, 20 задач: 16 LIBERO + 4 SimplerEnv).
Следующий этап — первые model rollouts (см. конец этого раздела). Порядок
этапов — в "Порядок построения benchmark" ниже.

**`data/pilot_v0_release/frames_v0.jsonl`** — 20 фреймов, схема v0.2, полностью проходит
`scripts/validate_frames.py`. **Все поля контента теперь реально заполнены,
включая `mt_russian`** (см. ниже) — Tier-1 variants, три
"желательных"/exploratory варианта (`ru_translit`, `ru_colloquial`,
`ru_anaphora`, заполнены или обоснованно `axis_na`), `token_len` и
`mt_russian`/`mt_metadata`. Правила авторинга (транслитерационная схема,
`-ка`-стратегия для colloquial, критерии применимости anaphora) — в skill
`slava-instruction-variants`. Дашборд (`scripts/generate_frames_review.py`):
`ru_colloquial`/`ru_anaphora` в `SCORED_VARIANTS` (получают
naturalness/equivalence/ambiguity), `ru_translit` в `TEXT_VARIANTS` без
скоринга (как `en_paraphrase` — механический transform, скорить нечего).
`validation.native_check` выставлен `"passed"` на всех 20 записях. RU Tier-1
варианты были LLM draft, но пользователь лично просмотрел все переформулировки
промптов и подтвердил, что LLM-draft оценок и его личного просмотра
достаточно для human-verified native check — формальный построчный проход по
`data/frames_review.html` с расстановкой оценок не потребовался. `validation.
author`/`validation.notes` в `data/pilot_v0_release/frames_v0.jsonl` обновлены под всех 20
записях, чтобы отражать это честно (не "pending human review", а
"human-verified by project owner"). Вопрос закрыт, freeze разблокирован.

**Прошёл полный ручной+программный аудит всех 20 фреймов** (по явному
запросу пользователя, высокий recall, "передаём данные другой команде"):
`scene.objects` сверены с `object_lexicon.csv` программно (category/color,
0 расхождений); полнота `scene.objects` против `task_inventory.jsonl`
проверена (0 missing/extra sim_handle); все `variants`, включая
`code_switch`, построчно сверены с лексиконом (правило — EN NP должна
совпадать со словом, которое уже использует `en_canonical`/`en_paraphrase`
для этого объекта, обычно `canonical_name_en`, но иногда `semantic_subtype_
en` или урезанная форма без модификатора — см. skill
`slava-instruction-variants`). В процессе аудита исправлено: `distractor`
vs `background` роль переразмечена по всем сценам (см. ниже); `ru_case_swap`
у `pick_up_the_black_bowl...` (была потеряна позиционная привязка «по
центру стола», из-за чего цель не отличалась от дистрактора — той же
черной миски); устаревшие draft-оценки `push_the_plate...__init034`
(текст уже был исправлен раньше, оценки — нет); `ru_negation` у
`pick_up_the_milk...` (generic «сок» → лексиконный «апельсиновый сок»);
`flat_stove` везде теперь называется по `canonical_name_ru`
(«электроплитка»)/`allowed_synonyms_ru` («настольная плита» в colloquial),
а не по широкой `category_ru` («плита») — было расхождение с лексиконом,
пользователь подтвердил, что нужно поправить; заодно `en_paraphrase` для
`push_the_plate...` (`shove` → `slide`, чтобы не добавлять оттенок силы,
которого нет в `push`). Ноль оценок `naturalness`/`equivalence`/`ambiguity`
ниже порога 4 в текущем состоянии файла.

**Проверено и сознательно НЕ считается багом:** 4 задачи с корзиной
(`butter`/`cream_cheese`/`milk`/`tomato_sauce`) называют объект по
`semantic_subtype` (масло/сливочный сыр/...), хотя
`semantic_identity_visually_recoverable=no` в лексиконе для всех этих
объектов (подпись на упаковке физически неразличима на рендере) — RU здесь
обязан зеркалить `en_canonical` (буквальное неизменяемое имя LIBERO-таски),
которое тоже называет объект по subtype; ограничение симметрично в EN/RU,
значит не искажает Δlang, но стоит помнить при интерпретации результатов
этих 4 сцен.

**Оставшийся мягкий пункт, не блокирующий:** `ru_negation` у
`widowx_stack_cube` (4 сцены) использует слово «желтый» дважды в разных
ролях (forbidden-объект и reference для размещения) — формулировка после
переупорядочивания в эту же сессию («возьми не желтый, а зеленый кубик и
поставь на желтый») стала яснее прежней, но draft-оценка `naturalness: 4`
(не 5) не пересчитывалась — можно перепроверить при желании, `native_check`
это не блокирует (порог `>=4` пройден).

**Вопрос направления шкалы `ambiguity` — решён.** Пользователь подтвердил:
выше = чётче/однозначнее (5 = максимально однозначно), как и были проставлены
все текущие draft-оценки. Менять данные не потребовалось.

**QA pipeline из `task.md` (16 пунктов) сверен построчно с `validate_frames.py`
и `frames_schema.py` — все 16 пунктов теперь реализованы и зелёные**
(файлы картинок, sim_handle против `task_inventory.jsonl`, уникальность id,
target/reference/forbidden-контракт, реестры action/relation, непустые
success_predicates, реестр variants, `ru_negation`⇄`forbidden`,
`ru_case_swap`⇄`axis_na`, native_check status, `axis_na`-reason, и —
закрыто позже, в отдельной сессии — пункт 14, `token_len` для реальных
токенизаторов, см. ниже).

**`data/selected_tasks_v0.jsonl` (D3) отдельно перепроверен и подтверждён
корректным.** Важно: у D3 в `task.md` нет отдельной JSON-схемы — это
заморозка отобранных строк `task_inventory.jsonl` (`usable_for_slava=true`),
поэтому правильный контракт для него — тот же `schemas/task_inventory.
schema.json`, не что-то новое; `validate_inventory()` на нём зелёный. Также
подтверждено: 16 LIBERO + 4 SimplerEnv; все 9 квот из `task.md` выполнены
(ни одна не ниже минимума, `container` впритык 4/4); ни одного `null` в
`quota_eligibility`; все `usable_for_slava=true`; `task_uid` уникальны;
`init_state_id`/`episode_id` — только из зафиксированных в "Неизменяемые
решения" наборов; `source.commit` совпадает с пинами в `scripts/bootstrap.sh`;
множество `task_uid` в `selected_tasks_v0.jsonl` и `frames_v0.jsonl`
идентично (0 потерянных/лишних сцен между D3 и D4).

**Актуальный шаблон схемы фрейма v0.2** пользователь сам вставил в `task.md`
(строки ~600-727: новый YAML-пример с `mt_metadata`/`token_len`, старый
пример помечен `old` следом). Синхронизация с `data/pilot_v0_release/frames_v0.schema.json`
подтверждена. В `task.md` остались висящие маркеры-слова `upd`/`old` прямо в
тексте (как минимум строки ~298, ~600, ~727) — спросили пользователя явно:
он подтвердил, что `task.md` не трогаем в принципе, это его внешний источник
истины и условие проекта. Оставлено как есть окончательно, не поднимать
снова.

**Git:** весь D4-pipeline закоммичен (коммит `113e531`, "Freeze D4 pilot v0"
— `data/pilot_v0_release/frames_v0.jsonl`, `data/frames_review.html`, `data/pilot_v0_release/prompts_v0.jsonl`,
`data/pilot_v0_release/frames_v0.schema.json`, все `scripts/*frames*`/`compute_token_len.py`/
`export_prompts.py`/`run_mt_translate.py`, `src/slava_inventory/
frames_schema.py`, `.claude/skills/`, `requirements-tokenizers.txt`, плюс
регенерированные `data/screenshot_sheet_small.html`/`screenshot_sheet_full.
html`/`docs/index.html`, которые оказались устаревшими относительно уже
закоммиченного `task_inventory.jsonl`, и `task.md`-правки пользователя
v0.2-шаблона) по его явному согласию. **Тег `slava-pilot-v0` проставлен** на
этот коммит (freeze по "Definition of Done: pilot v0" из `task.md`) — тег и
коммит локальные, не запушены, пуш делать только по отдельной явной
просьбе. `data/HOPE_3D_models/` (209 МБ) сознательно не в git. Новое:
`.venv-tokenizers/` (локальный venv для `compute_token_len.py`,
`transformers`/`huggingface_hub`/`sentencepiece`) — `python -m venv` сам
создаёт внутри `.venv-tokenizers/.gitignore` с `*`, в git не попадёт и не
должен.

**Реорганизация после freeze:** `frames_v0.jsonl`/`prompts_v0.jsonl`/
`frames_v0.schema.json` перенесены из `data/`/`schemas/` в новую подпапку
`data/pilot_v0_release/` (по явной просьбе пользователя — физически отделить
то, что D4 передаёт следующему этапу, от вспомогательных артефактов). Все
пути в `scripts/*frames*`/`compute_token_len.py`/`export_prompts.py`/
`run_mt_translate.py`, `src/slava_inventory/frames_schema.py`, `README.md` и
этом файле обновлены. По ходу нашлась и исправлена связанная бага: и
`validate_frames.py`, и `generate_frames_review.py` резолвили путь к
картинкам (`images.agentview_rgb`/`wrist_rgb`) относительно директории самого
`frames_v0.jsonl`, а не относительно `data/`, где реально лежит
`data/images/` — при регенерации это привело бы к ложным "missing file". Оба
скрипта теперь используют отдельную константу `IMAGES_BASE_DIR = data/`,
независимую от того, где лежит сам `frames_v0.jsonl`. `git mv` сохранил
историю файлов; тег `slava-pilot-v0` остался на прежнем коммите (`113e531`) —
это состояние данных на freeze, реорганизация путей не меняет содержание
фреймов.

**`token_len`/`token_len_metadata` теперь реальные** (закрыто в этой сессии,
не эвристика). Схема и ключи-токенизаторы task.md не задавал явно — решены с
пользователем в чате и записаны как источник истины в
`src/slava_inventory/frames_schema.py` (`TOKEN_LEN_TOKENIZERS`,
`TOKEN_LEN_CHECKPOINTS`): `qwen3_vl` (`Qwen/Qwen3-VL-4B-Instruct`, покрывает
и GreenVLA), `openvla_oft`
(`moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10` —
официальный OFT-чекпойнт именно под наши LIBERO spatial/object/goal сьюты,
покрывает и Prismatic), `paligemma` (`google/paligemma-3b-pt-224`, gated —
покрывает и π0/π0.5, у них тот же gemma-токенизатор), `smolvla`
(`HuggingFaceTB/SmolVLM2-500M-Video-Instruct`). Форма — `token_len:
{tokenizer_key: {variant_key: int}}`, посчитано для всех заполненных на
данный момент `variants.*` (не для `mt_russian`, он всё ещё `null`).
Подробности, известные грабли (lerobot pi0/smolvla не хранят собственный
tokenizer.json, `trust_remote_code=False` для openvla-oft) и когда
пере-запускать — в skill `slava-token-len`. Инструмент —
[`scripts/compute_token_len.py`](scripts/compute_token_len.py), гоняется из
отдельного gitignored venv `.venv-tokenizers/` (тяжёлая зависимость
`transformers`, сознательно не в `requirements-notebook.txt`):
`.venv-tokenizers/bin/python scripts/compute_token_len.py`, затем обычный
`python3 scripts/validate_frames.py`. `google/paligemma-3b-pt-224` — gated,
для скачивания нужен HF-аккаунт с принятой лицензией PaliGemma
(`huggingface-cli login`); у пользователя уже есть.

**`mt_russian` теперь реальный** (закрыто в этой сессии). Google Translate
API не подошёл пользователю (биллинг/доступ) — переключились на DeepL API
по его явному выбору; ключ передан через переменную окружения
`DEEPL_API_KEY` (сначала пользователь один раз вставил ключ текстом в чат —
это зафиксировано как небезопасное, ключ рекомендовано отозвать/перевыпустить,
новый задан только через env var). Инструмент —
[`scripts/run_mt_translate.py`](scripts/run_mt_translate.py): сырой перевод
`variants.en_canonical`, без редактуры (по правилу task.md), header-based
DeepL-авторизация (form-body деприкейчен с ноября 2025), `api-free.deepl.com`
(free-tier ключ, суффикс `:fx`). `mt_metadata` = `{"system": "DeepL API
(api-free.deepl.com, EN->RU)", "date": ...}`. Важная находка: у пользователя
шелл по умолчанию — fish, ключ задан как `set -Ux` (fish universal
variable) — invisible для bash/zsh-процессов, которыми пользуется этот
харнесс; MT-скрипт нужно гонять через `fish -c '...'`, не напрямую. Raw
DeepL-вывод оставлен как есть, включая наблюдаемую непоследовательность
между похожими предложениями (`"со средины стола"` vs `"со середины
стола"` для двух пар init state одной задачи) — это ожидаемое поведение
сырого MT, не баг. Все грабли — в skill `slava-mt-russian`. После MT-прогона
`token_len` пересчитан (`compute_token_len.py`, добавилась колонка
`mt_russian`), `validate_frames.py` зелёный.

**`scripts/export_prompts.py` теперь существует** (закрыто в этой сессии).
Формат task.md не задавал (только "есть export_prompts.py" и "первые prompts
для OpenVLA/GreenVLA-style eval") — решено с пользователем: JSONL, одна
строка на `(task_uid, variant)`, 7 primary-вариантов — 6 из "Сначала
затравка" (`en_canonical`, `en_paraphrase`, `ru_literal`, `ru_case_swap`,
`ru_negation`, `code_switch`) плюс `mt_russian` (добавлен по решению
пользователя, как только перестал быть `null` — у него своя строка в
"Table - behavioral pilot"). `axis_na`-варианты у конкретной сцены
пропускаются (не эмитятся как `null`-промпты). Выход —
[`data/pilot_v0_release/prompts_v0.jsonl`](data/pilot_v0_release/prompts_v0.jsonl), 127 строк из 20 сцен × 7
вариантов минус axis_na (`ru_case_swap` заполнен у 8/20, `ru_negation` у
19/20 — совпадает с минимальными квотами `task.md`; `mt_russian` у всех
20/20). Каждая строка несёт не только `instruction`, но и reset-metadata
(`bddl_file`/`init_state_id` или `episode_id`/`reset_seed`/`gym_env_name`) и
`target_object`/`reference_object`/`forbidden_objects`/`success_predicates`
— то, что нужно eval harness для авторазметки роллаута по
`rollout_annotations.jsonl` контракту из `task.md`, не только текст промпта.

**QA pipeline `task.md` теперь полностью закрыт, включая native check.**
Все 16 пунктов чеклиста зелёные; пользователь лично просмотрел RU
переформулировки промптов и явно подтвердил, что это достаточно как
human-verified native check (не требуется формальный построчный проход по
`data/frames_review.html`) — `validation.author`/`validation.notes` в
`data/pilot_v0_release/frames_v0.jsonl` обновлены под всех 20 записях, чтобы это отражать
честно. Направление шкалы `ambiguity` тоже подтверждено (выше = чётче).
`task.md` содержит висящие маркеры `upd`/`old` (см. выше) — пользователь
явно попросил не трогать этот файл, оставлено окончательно. Freeze tag
`slava-pilot-v0` проставлен по итогам этого явного согласия.

**Следующий крупный блок работы: первые model rollouts.** Ничего из этого
кода не начато — это задача для следующей сессии (пользователь переезжает на
GPU-сервер, там её будет писать новый агент). Ниже — подробный бриф: что
нужно построить, что и как собирать, что уже решено с пользователем, и что
явно осталось открытым и требует обсуждения с ним перед/во время реализации.
Масштабирование pipeline на ~200 сцен — это отдельный будущий блок, не
путать с first rollouts, не начинать раньше него.

### Вход и цель

Вход — [`data/pilot_v0_release/prompts_v0.jsonl`](data/pilot_v0_release/prompts_v0.jsonl)
(127 строк `(task_uid, variant)` — 20 сцен × 7 primary-вариантов минус
`axis_na`) и [`data/pilot_v0_release/frames_v0.jsonl`](data/pilot_v0_release/frames_v0.jsonl)
(более полный источник — нужен, если для `first_contact_object` придётся
сопоставлять `sim_handle` из симулятора с `id`/ролью слота). Цель — прогнать
каждую комбинацию (сцена × вариант × модель) closed-loop в симуляторе,
залогировать поведение и получить `rollout_annotations.jsonl` +
таблицы "Table - behavioral pilot"/"Table - cleaned language effect" из
`task.md`. Формат `rollout_annotations.jsonl` и список `failure labels`
(`success`/`target_grounding_error`/`reference_grounding_error`/
`relation_binding_error`/`negation_error`/`physical_execution_error`/
`no_action_or_timeout`/`unclear`, с правилами разметки каждой) заданы в
`task.md`, разделы "Auto-labeling для первых прогонов" и "Failure labels" —
не изобретать свою схему, реализовывать строго по этим разделам.

### Модели — 5, не 4

`task.md` в таблице "Модели и среды" перечисляет 3 строки, но GreenVLA у
пользователя считается за **две отдельные модели** — R0 (base) и R1 (bridge),
как и в его собственном описании curriculum'а (`R0-base → R1-bridge →
R2-bridge` в разделе "Наш core"). Итоговый список для первого прохода:

1. **GreenVLA-R0** — Qwen3-VL-4B-Instruct бэкбон, action-tuned R0.
2. **GreenVLA-R1 (bridge)** — тот же бэкбон, следующая стадия curriculum'а.
3. **OpenVLA-OFT** — `moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10`
   (тот же чекпойнт, что уже используется для `token_len`).
4. **π0/π0.5** — через lerobot, PaliGemma-бэкбон.
5. **SmolVLA** — через lerobot, `HuggingFaceTB/SmolVLM2-500M-Video-Instruct`
   судя по регистру токенизаторов, но конкретный action-policy чекпойнт для
   инференса (не только токенизатор) ещё предстоит выбрать/подтвердить.

### Модель → среда

`task.md` явно привязывает только GreenVLA (обе версии) → SimplerEnv/bridge
(4 сцены) и OpenVLA-OFT → LIBERO (16 сцен). Для π0/π0.5 и SmolVLA
пользователь явно решил: **обе модели гоняются на обеих средах, то есть на
всех 20 сценах** — не только на своей "родной" среде из таблицы `task.md`.
Значит нужна LIBERO-интеграция для lerobot-политик (π0/π0.5, SmolVLA) и
SimplerEnv/bridge-интеграция для них же — обе стороны matrix, а не только
одна. Итоговая матрица прогонов: GreenVLA-R0/R1 × 4 SimplerEnv-сцены,
OpenVLA-OFT × 16 LIBERO-сцен, π0/π0.5 и SmolVLA × все 20 сцен (обе среды).

### Объём первого прохода

Пользователь явно выбрал: **все 5 моделей × все 127 промптов** (не
уменьшенное подмножество, вопреки более осторожному совету `task.md` для
полного 60–80-задачного набора — "2–3 модели"). Технических препятствий к
этому нет: эпизоды LIBERO/SimplerEnv короткие (обычно до нескольких сотен
шагов), инференс VLA на современной GPU быстрый, весь объём (максимум
5 × 127 = 635 эпизодов, меньше — там, где модель не покрывает среду сцены)
занимает часы, не дни, на одной GPU уровня A100/RTX 4090.

**Открытый вопрос, не решённый явно: сколько повторов на комбинацию
(сцена × вариант × модель).** `task.md` для полного набора советует 25
роллаутов/вариант — но там "вариант" пулит много разных задач, у нас же
каждая (сцена, вариант) уже фиксированная точка с зафиксированным
`init_state_id`/`episode_id`/`reset_seed`. Если политика детерминирована (или
инференс без сэмплирования), повторный прогон той же комбинации даст тот же
результат — тогда лишние повторы не добавляют статистической мощности, только
тратят compute. Если политика или окружение стохастичны (temperature,
sampling actions, шум в физике), повторы осмысленны. **Прежде чем писать
rollout logger, нужно решить с пользователем: n=1 на комбинацию по
умолчанию, или n>1 с явным указанием источника стохастичности** — не
предполагать это молча.

### Что логировать на каждом шаге (rollout logger)

По разделу "Auto-labeling для первых прогонов" `task.md`:

```
object poses
contacts
gripper state
robot action
current instruction variant
task_uid
seed
model name
```

Из этого автоматически считаются (тоже per `task.md`): `first_contact_object`,
`wrong_object_rate`, `forbidden_object_touch`, `final_spatial_predicate`,
`relation_success`, `conditional_execution_success`, `action_divergence_to_en`.
`first_contact_object` — это `sim_handle`; чтобы связать его с ролью
(target/reference/distractor/forbidden), нужен `scene.objects` из
`frames_v0.jsonl`, не только `prompts_v0.jsonl`.

**Дополнительно по явной просьбе пользователя, не из task.md:** сохранять
записи с камер (`agentview` + `wrist`, где есть — у SimplerEnv/WidowX нет
wrist-камеры) в ходе роллаута — кадры или видео, "для дебага и красоты", не
как обязательный вход в auto-labeling метрики. Формат (видео vs frame dump,
частота кадров, куда сохранять) ещё не решён — обсудить на сервере.

### Выход

`rollout_annotations.jsonl`, одна строка на эпизод, строго по формату из
`task.md` (`run_id`, `model`, `task_uid`, `variant`, `instruction`, `seed`,
`success`, `first_contact_object`, `target_object`, `reference_object`,
`wrong_object`, `forbidden_object_touched`, `final_relation_success`,
`conditional_execution_success`, `failure_type_auto`, `notes`). Первые **100
rollouts** — ручная валидация точности auto-labeler'а (`task.md`, строка
1224), прежде чем доверять разметке всего массива. Далее — таблицы "Table -
behavioral pilot" (SR/first-contact target accuracy/wrong-object
rate/relation success/forbidden touch по каждому из 8 вариантов) и "Table -
cleaned language effect" (Δlang-метрики — главная метрика пилота, отделяет
языковой эффект от instruction-string OOD).

### Открытые вопросы для сервера (явно не решены в этом чате)

- сколько повторов на (сцена × вариант × модель) — см. выше;
- точный action-policy чекпойнт для SmolVLA (инференс, не только
  токенизатор) и π0/π0.5;
- как именно поднимать LIBERO-инференс для lerobot-политик (π0/π0.5,
  SmolVLA) — своя обвязка или готовая lerobot-интеграция;
- формат/частота сохранения камерных записей;
- спеки сервера уже обсуждались (см. предыдущий диалог) — ориентир: одна GPU
  ≥24 ГБ VRAM (RTX 4090/A5000/A6000 или облачный A100 40 ГБ), headless
  EGL-рендеринг для MuJoCo и SAPIEN, 32–64 ГБ RAM, 100+ ГБ диска под
  чекпойнты — но нужно уточнить при реальном выборе конкретных чекпойнтов
  π0/π0.5 и SmolVLA, если они окажутся тяжелее ожидаемого.

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

## `task.md` — контракт, от которого нельзя отходить молча

[`task.md`](task.md) не справочный документ, а source of truth по структурам
данных, схемам, квотам и процессу, из которого копируются реальные
формулировки в другие места (внешний источник пользователя, из которого он
сам вставляет актуальные разделы в `task.md`). Результат этой работы передаётся
следующим людям, у которых не будет истории этого диалога — они будут
ориентироваться только на `task.md` и на данные/код, которые ему соответствуют.
Поэтому:

- не изобретайте собственные названия полей, id-схемы, соглашения об
  именовании или структуры данных там, где `task.md` уже даёт пример или
  правило — даже если своя схема кажется чище или удобнее в реализации.
  Пример такой ошибки из этой сессии: `build_frames_v0.py` завёл id
  `wooden_cabinet_1__middle_drawer` вместо того, чтобы использовать реальное
  имя BDDL-региона `wooden_cabinet_1_middle_region`, уже присутствующее в
  `data/libero_bddl` и в `success_predicates` исходного inventory — костыль,
  который расходился и с `task.md`, и с физической средой;
- если для конкретного случая `task.md` не даёт прямого примера (как было с
  `type: state` для success_predicates у `open`/`turn_on`), расширяйте
  структуру в согласии с духом существующего контракта, а не произвольно;
  явно проговорите это с пользователем, а не решайте молча;
  расхождение самого `task.md` (например, отсутствие `ambiguity` в YAML-примере
  при том, что раздел "Native check" требует три оценки) фиксируйте как
  находку, а не тихо исправляйте под себя;
- если требование пользователя или реальность (среда, BDDL, рендеры) всё же
  вынуждают отойти от `task.md` содержательно — не просто в деталях
  реализации, а в структуре данных, схеме, названии поля или процессе —
  **обязательно скажите об этом пользователю отдельно и явно**, до того как
  закрепите это в коде/данных. Ему нужно успеть обновить свой внешний источник
  `task.md`, иначе следующая сессия снова разойдётся с ним;
- если расхождение с `task.md` уже существует на диске (например, раздел
  устарел, потому что пользователь ещё не перенёс туда согласованные в чате
  правки), не выбирайте эту рассинхронизацию как разрешение изобретать что-то
  третье — по возможности ориентируйтесь на актуальную договорённость из
  диалога и явно напомните об открытом расхождении.

## Как помогать пользователю

Пользователь ведет исследовательский проект и предпочитает совместную,
практическую работу.

- По умолчанию общайтесь по-русски.
- Сначала сообщайте конкретный результат или диагноз, затем необходимые детали.
- Пользователь предпочитает короткие ответы связным текстом абзацами, а не
  списками/буллитами. Списки уместны только когда перечисление явно уместнее
  прозы (например, построчная сверка пунктов чек-листа).
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
- замороженный D3 manifest (20 задач): [`data/selected_tasks_v0.jsonl`](data/selected_tasks_v0.jsonl),
  человекочитаемый лист с квотами: [`data/selected_tasks_v0.html`](data/selected_tasks_v0.html);
- grounded semantic frames v0.2 (target/reference/relation/forbidden + Tier-1
  instruction variants на каждую из 20 сцен), **заморожено**
  (freeze `slava-pilot-v0`): [`data/pilot_v0_release/frames_v0.jsonl`](data/pilot_v0_release/frames_v0.jsonl),
  contract: [`data/pilot_v0_release/frames_v0.schema.json`](data/pilot_v0_release/frames_v0.schema.json). Верхний
  уровень фрейма сделан плоским буквально по шаблону из `task.md`
  (`task_uid`/`suite`/`task_id`/`init_state_id`/`frame_version`/`canonical_en`/
  `bddl_file`, без вложенного `source`), расширен `environment`/`commit`/`task_name`/
  `episode_id`/`reset_seed`/`gym_env_name` (`null` для чужого суита) для
  воспроизводимости SimplerEnv-сцен и `mt_metadata` (заполнен, реальный
  DeepL-прогон). `scene.objects[].role` — только
  `target`/`reference`/`distractor`/`background`, как в шаблоне; `forbidden` —
  не роль, а независимый список id в `slots.forbidden` (объект с ролью
  `distractor` или `reference`, явно названный в `ru_negation`).
  `slots.success_predicates` — структурированные (`type: spatial_relation` с
  `relation`/`arg1`/`arg2`, либо `type: state` для `open`/`turn_on` — второй тип
  шаблон не покрывал явно), ссылаются на `id` из `scene.objects`, а не на сырые
  BDDL-регионы. Изначально собран скриптом
  [`scripts/build_frames_v0.py`](scripts/build_frames_v0.py) как LLM draft
  (регенерация даёт `validation.native_check="pending"`/`mt_russian=null` —
  не запускайте её на замороженном файле без явной причины). Валидация —
  [`scripts/validate_frames.py`](scripts/validate_frames.py): схема +
  физическое наличие картинок (резолвятся от `data/`, не от места, где лежит
  сам `frames_v0.jsonl`) + сверка `sim_handle` с `task_inventory.jsonl`
  (правила 1–2 из QA-чеклиста `task.md`); `token_len` реальный (не
  эвристика) — считает [`scripts/compute_token_len.py`](scripts/compute_token_len.py)
  из отдельного venv `.venv-tokenizers/`, см. skill `slava-token-len`.
  `validation.native_check="passed"`, human-verified пользователем (см.
  выше) — редактируемый дашборд для будущих правок/масштабирования на
  ~200 сцен — [`data/frames_review.html`](data/frames_review.html)
  (генератор [`scripts/generate_frames_review.py`](scripts/generate_frames_review.py),
  применение правок [`scripts/apply_frames_review.py`](scripts/apply_frames_review.py));
- плоские prompts для первых roll-out'ов (JSONL, один `(task_uid, variant)`
  на строку, 6 primary-вариантов из "Сначала затравка" `task.md` + `mt_russian`,
  с reset-metadata и target/reference/forbidden/success_predicates для
  авторазметки): [`data/pilot_v0_release/prompts_v0.jsonl`](data/pilot_v0_release/prompts_v0.jsonl), генератор
  [`scripts/export_prompts.py`](scripts/export_prompts.py);
- подробный research и benchmark plan: [`task.md`](task.md);
- deployment и pinned dependencies: [`scripts/bootstrap.sh`](scripts/bootstrap.sh).

**`data/pilot_v0_release/`** — отдельная подпапка для файлов, которые D4
буквально передаёт следующему этапу (первые model rollouts): `frames_v0.jsonl`,
`prompts_v0.jsonl`, `frames_v0.schema.json`. Всё остальное (`task_inventory.jsonl`,
`object_lexicon.csv`, `selected_tasks_v0.jsonl`, все HTML-дашборды, `scripts/*`,
`data/images/`, `.claude/skills/`) — вспомогательные/рабочие артефакты, они
остаются на прежних местах вне этой папки. Это разделение — по явной просьбе
пользователя, чтобы граница "что уходит в следующий этап" была видна физически
в дереве репозитория, а не только по документации.

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

### Мнемоническое правило для frames_v0: составные объекты (несколько ручек/ящиков)

Когда target или forbidden — это не отдельный физический объект, а адресуемая
часть одного составного объекта (например, конкретный ящик шкафа `wooden_cabinet`
с несколькими ящиками), в `scene.objects` заводятся синтетические под-объекты с
общим `sim_handle`, но разными `id`. `id` должен буквально совпадать с полным
именем BDDL-региона фикстуры (`:target wooden_cabinet_1` + имя региона из
`:regions`, склеенные через одно подчёркивание — например `wooden_cabinet_1_middle_region`
/ `wooden_cabinet_1_top_region`, как в
`data/libero_bddl/libero_goal/open_the_middle_drawer_of_the_cabinet.bddl`,
где `:goal (Open wooden_cabinet_1_middle_region)`), а не изобретаться заново
(двойное подчёркивание и произвольные суффиксы вроде `__middle_drawer` — баг,
исправленный в этой сессии). Это также совпадает с тем, как
`success_predicates` в исходном `task_inventory`/`selected_tasks_v0.jsonl`
уже ссылались на этот регион до перехода на frames_v0. Роль (`role`) у обоих —
обычная `target`/`distractor`: отдельной роли `forbidden` в схеме нет (см.
`scene.objects[].role` выше). То, что под-объект используется как
forbidden-кандидат для `ru_negation`, выражается только через его `id` в
`slots.forbidden`, а не через role. Это позволяет `slots.target`/
`slots.forbidden` указывать на конкретную часть без нарушения контракта "один
физический объект — один `sim_handle`" из `task_inventory`. Так уже размечен
`open_the_middle_drawer_of_the_cabinet` в
[`scripts/build_frames_v0.py`](scripts/build_frames_v0.py). Не путайте это с
`ru_case_swap`: у составного объекта нет полноценного reference для
перестановки ролей (`reference` тут `null`, обе части — `target`/`distractor`
внутри одного физического объекта), это пара для `ru_negation`, а не для
`ru_case_swap`.

Третий под-объект того же шкафа, `wooden_cabinet_1_bottom_region`, размечен
`role: distractor`, но сознательно НЕ включён в `slots.forbidden` — он не
назван в тексте `ru_negation` («не верхний, а средний ящик...»), а
`forbidden` привязан именно к тому, что явно названо в «не X, а Y» (метрика
`forbidden_object_touch` из `task.md` диагностирует именно негированный
кандидат, а не любой неверный объект вообще). Не путайте «правдоподобная
неверная альтернатива действию» (`role: distractor`) с «названа как неверная
в конкретном instruction variant» (`slots.forbidden`) — это разные вопросы,
и `distractor`, не входящий в `forbidden`, — нормальный, ожидаемый случай.

**Известное ограничение: `build_scene_objects` копирует `visible_agentview`/
`visible_wrist` родительского физического объекта на все его синтетические
под-объекты без изменений** (см. `base["visible_agentview"]`/
`base["visible_wrist"]` в `scripts/build_frames_v0.py`). Это может быть
неверно: видимость человек проверял для шкафа целиком в
`visibility_review.html` («виден ли шкаф»), а не для того, различима ли
конкретно эта его часть («виден ли именно этот ящик, а не сосед сверху/
снизу») — особенно на wrist-камере, которая для физического объекта
`wooden_cabinet` в этой сцене вообще на грани кадра
(`visible_wrist: visible_partial` унаследовано, но малоинформативно на уровне
под-объекта). Перед freeze любой сцены с составным объектом эту унаследованную
видимость нужно перепроверять вручную по каждому под-объекту отдельно (agentview
и особенно wrist), а не считать автоматически верной. Для
`open_the_middle_drawer_of_the_cabinet` для этого делался разовый временный
дашборд (`scripts/generate_cabinet_drawer_wrist_review.py` +
`scripts/apply_cabinet_drawer_wrist_review.py` → `data/cabinet_drawer_wrist_review.html`,
не часть постоянного pipeline и не входил в общий `apply_frames_review.py`
op-словарь); правки уже применены в `frames_v0.jsonl` (`visible_wrist`:
`top_region=false` в обеих сценах шкафа, `bottom_region=true` в `init034`), и
сам дашборд после использования удалён из репозитория. Для следующего
составного объекта потребуется аналогичный разовый инструмент, а не
восстановление этого.

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
  прокидывает обновлённую видимость в `data/selected_tasks_v0.jsonl`;
- grounded semantic frames v0.2: schema runtime
  [`src/slava_inventory/frames_schema.py`](src/slava_inventory/frames_schema.py),
  сборка [`scripts/build_frames_v0.py`](scripts/build_frames_v0.py) →
  `data/pilot_v0_release/frames_v0.jsonl`, валидация
  [`scripts/validate_frames.py`](scripts/validate_frames.py), редактируемый
  дашборд native check
  [`scripts/generate_frames_review.py`](scripts/generate_frames_review.py) →
  `data/frames_review.html`, правки применяются через
  [`scripts/apply_frames_review.py`](scripts/apply_frames_review.py);
  реальный `mt_russian` (сырой MT, DeepL API) заполняет
  [`scripts/run_mt_translate.py`](scripts/run_mt_translate.py) (ключ через
  `DEEPL_API_KEY`, см. skill `slava-mt-russian`); реальные `token_len`
  считает
  [`scripts/compute_token_len.py`](scripts/compute_token_len.py) (нужен venv
  `.venv-tokenizers/`, см. skill `slava-token-len`); экспорт prompts для
  первых roll-out'ов —
  [`scripts/export_prompts.py`](scripts/export_prompts.py) →
  `data/pilot_v0_release/prompts_v0.jsonl`.

После изменений выполняйте проверки, пропорциональные риску. Особенно берегите
`data/task_inventory.jsonl`, `data/object_lexicon.csv` и `data/images`: human
annotations и локальные рендеры нельзя восстанавливать ценой их перезаписи.

## Agent skills для повторяемых задач разметки

В `.claude/skills/` живут project-scoped skills — операционный слой поверх
контракта из этого файла и `task.md`: не «что за поле», а «как сделать
хорошо, какие есть подводные камни, что мы уже один раз сделали неправильно».
Они написаны, чтобы не переоткрывать заново на ~200 сценах то, что уже узнали
на 20:

- `slava-instruction-variants` — авторинг Tier-1 вариантов (`en_paraphrase`,
  `ru_literal`, `ru_free_order`, `ru_case_swap`, `ru_negation`,
  `code_switch`): один вариант — одна языковая ось, лаконичность промптов для
  VLA, разбор реальных перегруженных формулировок, которые правили в пилоте;
- `slava-object-lexicon` — заполнение `data/object_lexicon.csv`: порядок
  источников истины, recoverability, согласование рода, `usable_v0`;
- `slava-scene-roles` — роли `scene.objects` и `slots`
  (`target`/`reference`/`distractor`/`background`/`forbidden`), включая
  составные адресуемые объекты (id из BDDL-региона, а не выдуманная схема) и
  унаследованную видимость под-объектов;
- `slava-visibility-review` — разметка `visible_agentview`/`visible_wrist`,
  включая ограничение для составных объектов;
- `slava-quota-eligibility` — разметка девяти `quota_eligibility` флагов и
  отбор манифеста под квоты `task.md`;
- `slava-native-check` — прогон native check (`data/frames_review.html`):
  что реально оценивается, пороги, и явно непрояснённый в `task.md` вопрос —
  в какую сторону растёт шкала `ambiguity` (см. сам skill, там это разобрано
  подробно и требует явного проговаривания с пользователем перед массовой
  разметкой, а не молчаливого выбора направления);
- `slava-token-len` — реальные токенизаторы для `token_len`/
  `token_len_metadata`: какие 4 ключа/чекпойнта, почему lerobot pi0/smolvla
  не хранят свой tokenizer.json, gated-доступ к PaliGemma, отдельный venv
  `.venv-tokenizers/`, когда пере-запускать после regen/правок/`mt_russian`;
- `slava-mt-russian` — реальный MT-прогон для `mt_russian`
  (`scripts/run_mt_translate.py`): почему нельзя редактировать вывод, DeepL
  header-auth/free-tier хост, ключ только через `DEEPL_API_KEY` (не в
  чат/код/CLI), грабли fish `set -Ux` vs bash/zsh-окружение харнесса, порядок
  пере-запуска `compute_token_len.py`/`export_prompts.py` после MT-прогона,
  как переключать MT-провайдера (уже было один раз: Google → DeepL) и общее
  правило безопасной передачи секретов в этом проекте;
- `slava-session-handoff` — процесс закрытия сессии и подготовки нового
  чата: сверка "Текущего состояния проекта" на противоречия (не просто
  дописывать абзац сверху), когда заводить/расширять skill вместо нового,
  структура самодостаточного стартового промпта для следующего чата.

Эти файлы — не статичная документация. Когда в ходе работы находится новое
устойчивое правило, исключение или ошибка (как случай `__middle_drawer` vs
`wooden_cabinet_1_middle_region`, или пропущенный `bottom_region`), агент
должен сразу дописать соответствующий skill, а не только упомянуть находку в
чате — иначе следующая сессия наступит на те же грабли. Частное решение для
одной сомнительной сцены сначала фиксируйте в `notes` конкретной записи; в
skill превращайте только повторяемое правило, по той же логике, что и для
мнемонических правил разметки квот выше.

Список skills выше — не окончательный. Когда проект переходит к новому виду
повторяемой ручной задачи, для которой ещё нет skill (например: MT-прогон и
проверка `mt_russian`, замер `token_len` реальными токенизаторами, разметка
`rollout_annotations`/failure labels после первых прогонов, что угодно из
`task.md`, до чего мы ещё не дошли) — агент должен завести новый файл в
`.claude/skills/<name>/SKILL.md` по образцу существующих (YAML frontmatter
`name`/`description`, затем операционные правила и разобранные на реальных
примерах ошибки), не дожидаясь отдельной просьбы пользователя. Не молчать и
не откладывать: если задача уже второй раз требует одного и того же
нетривиального решения, это сигнал завести skill сейчас, а не полагаться на
то, что следующая сессия увидит переписку в истории — она её не увидит.

## Агент обязан сам поддерживать `AGENTS.md` в актуальном состоянии

Этот файл заменяет отдельные handoff-файлы вроде удалённого `expl.md`:
пользователь должен иметь возможность в начале нового чата попросить агента
просто прочитать `AGENTS.md` и получить весь нужный контекст без пересказа
предыдущей переписки. Это работает только если файл действительно
поддерживается в актуальном состоянии внутри той же сессии, где меняется
состояние проекта, а не по отдельному запросу пользователя:

- в конце значимого куска работы (закрыт этап, изменилось состояние
  ключевого артефакта, принято решение, найдено расхождение с `task.md`,
  появился новый открытый вопрос) — обновляйте раздел "Текущее состояние
  проекта" тем же изменением, а не отдельным шагом после того, как
  пользователь спросит;
- если раздел "Текущее состояние проекта" устарел (описывает более раннюю
  стадию, чем показывает фактическое состояние репозитория/данных) —
  перепишите его при первой возможности, не оставляйте расхождение молча;
- новые устойчивые мнемонические правила, предпочтения пользователя по
  стилю работы и найденные баги/расхождения — по-прежнему фиксируются здесь
  же, по местам (мнемоники квот, contract-раздел про `task.md`,
  соответствующий skill), а не только в разделе статуса;
- если правка меняет что-то, что уже описано в другом месте файла
  (например, контракт схемы, список точек входа), поддерживайте оба места в
  согласии, а не дублируйте информацию с риском разъехаться;
- не разрастайте файл ради полноты: краткая, но точная сводка лучше
  исчерпывающего, но устаревающего текста. Если детали лучше живут в skill
  или в коде — ссылайтесь, а не копируйте.
