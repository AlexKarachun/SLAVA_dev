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

**Этап:** D4 закрыт и заморожен (tag `slava-pilot-v0` на коммите `113e531`,
запушено в `origin/main`, актуальная голова `main` — `973fdab`) — grounded
semantic frames + instruction variants готовы, после закрытого D3
(`data/selected_tasks_v0.jsonl`, 20 задач: 16 LIBERO + 4 SimplerEnv). Первые
model rollouts (см. конец этого раздела) **начаты и остановлены пользователем
досрочно** по лимиту времени: GreenVLA-R0/R1 полностью готовы (28/28 каждая),
OpenVLA-OFT частично (21/99), pi0/pi0.5/SmolVLA не начаты (0/127 каждая) — 77
эпизодов итого. `data/rollout_report.html` сгенерирован финальным проходом на
этих данных (behavioral pilot + Δlang таблицы из task.md, с честными
оговорками про неполное покрытие). Открытый бэклог, требующий пользователя:
ручная валидация первых 100 rollouts (task.md), решение о доснятии
pi0/pi0.5/SmolVLA — детали в конце этого раздела. **Сессия после этого
мигрировала с Vast.ai GPU-сервера на локальный Mac пользователя (без CUDA)**
— результаты прогона упакованы и скачаны отдельно от git, детали в самом
конце этого раздела ("миграция на локальную машину"). Порядок этапов — в
"Порядок построения benchmark" ниже.

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
этот коммит (freeze по "Definition of Done: pilot v0" из `task.md`).
**Запушено в `origin/main`** по явной просьбе пользователя (коммиты `113e531`,
`dce8d6b`, и следующим коммитом `973fdab` — реорганизация в
`data/pilot_v0_release/`, см. ниже; тег `slava-pilot-v0` тоже запушен).
Дальнейшие коммиты/пуши — по-прежнему только по явной просьбе, это разовое
разрешение не распространяется молча на будущие изменения. `data/HOPE_3D_models/`
(209 МБ) сознательно не в git. Новое:
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

**`token_len`/`token_len_metadata` реальные** (не эвристика, закрыто в более
ранней сессии, до freeze). Схема и ключи-токенизаторы task.md не задавал явно — решены с
пользователем в чате и записаны как источник истины в
`src/slava_inventory/frames_schema.py` (`TOKEN_LEN_TOKENIZERS`,
`TOKEN_LEN_CHECKPOINTS`): `qwen3_vl` (`Qwen/Qwen3-VL-4B-Instruct`, покрывает
и GreenVLA), `openvla_oft`
(`moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10` —
официальный OFT-чекпойнт именно под наши LIBERO spatial/object/goal сьюты,
покрывает и Prismatic), `paligemma` (`google/paligemma-3b-pt-224`, gated —
покрывает и π0/π0.5, у них тот же gemma-токенизатор), `smolvla`
(`HuggingFaceTB/SmolVLM2-500M-Video-Instruct`). Форма — `token_len:
{tokenizer_key: {variant_key: int}}`, изначально посчитано для всех
заполненных на тот момент `variants.*` (`mt_russian` тогда был ещё `null` —
реальный MT-прогон случился в отдельной, более поздней сессии, см. ниже, и
`token_len` был пересчитан после него, включая `mt_russian`; сейчас `null`
там больше нет). Подробности, известные грабли (lerobot pi0/smolvla не
хранят собственный
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
частота кадров) ещё не решён — обсудить на сервере; но место хранения уже
задано (см. "Выход и требования к запуску" ниже).

### Выход и требования к запуску

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

Три дополнительных требования к самому rollout-коду и командам запуска,
зафиксированные явно с пользователем, не додумывать по-своему:

- у команды запуска должен быть **smoke-test гиперпараметр**: короткий
  прогон на 2 сцены на каждую модель с оригинальным промптом (`en_canonical`)
  — быстрая проверка работоспособности всей цепочки перед полным прогоном по
  всем 127 промптам;
- **все логи со всех запусков** (`rollout_annotations.jsonl`, камерные
  записи, что угодно ещё) должны складываться в одно единое место, не быть
  раскиданы по моделям/запускам поотдельности — точную структуру этого
  единого каталога предстоит спроектировать на сервере;
- нужен **notebook**, где одна ячейка запускает и выводит дашборд со всеми
  камерными записями со всех прогонов (agentview + wrist, где есть) — чтобы
  отсмотреть отснятое одним запуском ячейки, без ручного перебора файлов.

### Открытые вопросы — решены в сессии реализации (2026-08-04)

Все пункты ниже обсуждены и подтверждены пользователем в чате перед началом
кода (архитектура объяснена, согласие получено), кроме отмеченных как решённые
агентом самостоятельно после того, как пользователь явно передал право решать
("если понадобится что-то решить — перечитай task.md, поставь себя на моё
место, реши сам; если вопрос реально требует меня — отложи в беклог").

- **Архитектура — env-worker отдельно от model-server**, общаются по
  localhost HTTP. Причина: `slava-libero` (Python 3.8.13, `torch 1.11+cu113`)
  и `slava-simpler` (Python 3.10) из `bootstrap.sh` жёстко запинены под
  рендеринг, заливать в них современные VLA-веса рискованно; у 5 моделей
  тоже несовместимые стеки друг с другом (например GreenVLA требует Python
  3.11+). env-worker (в `slava-libero`/`slava-simpler`) делает reset/render/
  step и шлёт `{images, instruction, proprioception}` на model-server;
  model-server — отдельный conda/venv на модель с `/predict`. Рассмотрен
  готовый `allenai/vla-evaluation-harness` (client-server, LIBERO+SimplerEnv,
  13+ моделей) — сознательно не подключён: неясна поддержка произвольного
  `init_state_id`/своего текста инструкции на эпизод (это наше ядро), плюс
  собственная SQLite-схема логов, которую всё равно пришлось бы
  транслировать в `rollout_annotations.jsonl`. Взята только сама идея
  client-server сплита как подтверждение, что паттерн стандартный.
- **Повторы (n) на комбинацию сцена×вариант×модель: n=1 для всех моделей**
  (решение пользователя, вопреки моему предложению различать по типу action
  head — детерминированные autoregressive vs стохастические flow-matching/
  diffusion). Пользователь выбрал единый n=1 ради простоты сравнения таблиц.
  Если впоследствии окажется, что π0/π0.5/SmolVLA дают заметно нестабильный
  результат от прогона к прогону (stochastic sampling в их action head), это
  стоит отдельно поднять — n=1 тогда может занижать оценку SR для этих
  моделей относительно детерминированных.
- **Камера: PNG-кадр на каждый шаг** (решение пользователя, не MP4/не через
  N шагов). Хранится в `rollouts/episodes/<run_id>/camera/{agentview,wrist}/
  step_<NNNN>.png`.
- **LIBERO-инференс для lerobot-политик (π0/π0.5, SmolVLA):** пользователь
  попросил сначала проверить готовые скрипты. Найдено: `lerobot` сам
  официально поддерживает LIBERO как env (`pip install -e ".[libero]"`,
  `lerobot-eval --env.type=libero`) — полноценный gym-класс внутри lerobot,
  не нужен ни openpi, ни свой адаптер с нуля. `lerobot-eval` CLI не даёт
  задать свою инструкцию/фиксированный `init_state_id` на эпизод (нужно нам),
  поэтому наш rollout-loop дёргает их env-класс напрямую в коде, а не через
  CLI — но сам env и engineering вокруг него (obs keys, control_mode,
  action space) переиспользуются готовые, не написаны с нуля. Подробности,
  включая точные observation keys (`observation.state` 8-dim,
  `observation.images.image`/`image2`, action `Box(-1,1,shape=(7,))`,
  `control_mode: relative|absolute` — надо сверить с тем, на чём обучен
  каждый конкретный чекпойнт) — в skill `slava-model-rollouts` (см. ниже).
- **Чекпойнты — исследованы через WebSearch/WebFetch в сессии реализации**
  (не выдуманы; актуальность на 2026-08-04, стоит перепроверить, если сессия
  идёт значительно позже):

  | Модель | Среда | Чекпойнт |
  | --- | --- | --- |
  | GreenVLA-R0 | SimplerEnv/bridge (4) | `SberRoboticsCenter/GreenVLA-5b-base-stride-1` |
  | GreenVLA-R1 (bridge) | SimplerEnv/bridge (4) | `SberRoboticsCenter/GreenVLA-5b-stride-1-R1-bridge` |
  | OpenVLA-OFT | LIBERO (16) | `moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10` |
  | π0 | LIBERO (16) | `lerobot/pi0_libero_finetuned` |
  | π0 | SimplerEnv/bridge (4) | `lerobot/pi0_base` (zero-shot) |
  | π0.5 | LIBERO (16) | `lerobot/pi05_libero_finetuned` |
  | π0.5 | SimplerEnv/bridge (4) | `lerobot/pi05_base` (zero-shot) |
  | SmolVLA | LIBERO (16) | `HuggingFaceVLA/smolvla_libero` |
  | SmolVLA | SimplerEnv/bridge (4) | `lerobot/smolvla_base` (zero-shot) |

  GreenVLA — пользователь сам указал репозиторий (`github.com/greenvla/
  GreenVLA`), R0/R1-bridge чекпойнты найдены на HF `SberRoboticsCenter/*`,
  backbone подтверждён как `Qwen3-VL-4B-Instruct` (совпадает с
  `TOKEN_LEN_TOKENIZERS['qwen3_vl']`). Для π0/π0.5/SmolVLA пользователь
  явно поручил найти официальные HF-чекпойнты самостоятельно — найдены
  симметричные `*_libero_finetuned`/`*_libero_base` у `lerobot` для всех
  трёх (LIBERO-часть), и только `*_base` для SimplerEnv/bridge-части.
  **Официального bridge/WidowX-специфичного финетюна ни для π0, ни для
  π0.5, ни для SmolVLA не нашлось** (есть один сторонний
  `juexzz/INTACT-pi0-finetune-bridge`, популярность не проверялась).
  Решение (подтверждено пользователем явно через AskUserQuestion): **брать
  `*_base` zero-shot на SimplerEnv/bridge, решить о смене чекпойнта по
  результатам smoke-теста.** Риск, явно проговорённый и принятый: эти
  модели предобучены на кадрах с реальных камер, SimplerEnv рендерит через
  SAPIEN — визуальный домен-гэп может утопить SR в ноль независимо от языка
  инструкции (floor effect), тогда Δlang на этих 4 сценах для этих 3 моделей
  может оказаться неинформативным. Если smoke-test это покажет — вернуться к
  вопросу подбора community bridge-финетюна.
- **Bootstrap:** на этом сервере `conda`/окружения ещё не подняты
  (`/opt/miniforge3/bin/conda` есть, но `slava-libero`/`slava-simpler`/
  `slava-notebook` — нет). `scripts/bootstrap.sh` запущен агентом
  автономно с `--skip-libero-datasets` (демонстрационные HDF5 не нужны для
  чистого inference-rollout, только для будущего training/trajectory —
  экономит время/трафик; при необходимости донакатить отдельно). GPU этого
  сервера — Tesla V100 32GB (Volta, compute capability 7.0, **нет bf16
  tensor cores** — чекпойнты, которые по умолчанию грузятся в bf16
  (Qwen3-VL-backbone, lerobot pi0/pi0.5 default `dtype=bfloat16` в примерах
  выше), в каждом model-server нужно форсировать в fp16/fp32).

**`HF_TOKEN` для HuggingFace добавлен пользователем в `~/.bashrc` (не в
`.env`) перед тем, как отойти.** Первая строка `~/.bashrc` — стандартный
guard `[ -z "$PS1" ] && return`, поэтому неинтерактивные (не login/не -i)
shell-вызовы этого харнесса не видят токен через обычный `source
~/.bashrc`; агент при первой попытке диагностики по неосторожности вывел
сырое значение токена в tool output через `grep -A1 -B1` (тот же класс
ошибки, что раньше был с `DEEPL_API_KEY`, вставленным текстом в чат —
см. skill `slava-mt-russian`). **Пользователю стоит решить, ротировать ли
этот HF-токен** из осторожности, раз его значение попало в контекст сессии.
Впредь для передачи `HF_TOKEN` в non-interactive команды используется
`export HF_TOKEN=$(awk -F'"' '/^export HF_TOKEN=/{print $2}' ~/.bashrc)`
(command substitution, не печатает значение в tool output), а не `source
~/.bashrc` и не `grep` с контекстными строками.

**Пользователь отошёл на ~1 час в середине этой сессии** (после
подтверждения архитектуры и всех решений выше), явно разрешив агенту
принимать дальнейшие некритичные решения самостоятельно ("поставь себя на
моё место"), откладывая в беклог только то, что реально требует его личного
решения. Дальнейший прогресс реализации, включая то, что уже реально
запущено/проверено на этом сервере (а не только спроектировано), — смотри
ниже эту сессию по мере обновления этого раздела.

### Продолжение сессии (новый агент, тот же день) — реальный прогресс

Пользователь вернулся в чат кратко дважды («продолжай, отложи вопросы
в беклог» и затем «если всё будет норм — запускай полный тест на все
5 моделей и 127 сцен, я всё ещё буду отсутствовать») и снова отошёл.
Ниже — что реально сделано и проверено на сервере этим агентом, а не
только спланировано. Полная техническая версия — в skill
`slava-model-rollouts`, здесь только summary для будущего чтения этого
раздела целиком.

**Bootstrap.** `scripts/bootstrap.sh --skip-libero-datasets` был запущен
предыдущим (прерванным) агентом и застрял ровно на моменте создания env
`slava-libero` (env создан, но `pip install -r requirements.txt` ещё не
выполнялся — 0 пакетов кроме pip/setuptools/wheel). Этот агент перезапустил
`bootstrap.sh --skip-libero-datasets --skip-smoke-test` (idempotent —
`ensure_repo`/`ensure_env` пропускают уже готовое), он **успешно
завершился**: `slava-libero` (Python 3.8.13, torch 1.11.0+cu113, CUDA
доступна — да) и `slava-simpler` (Python 3.10, ManiSkill2_real2sim+SAPIEN)
оба с зелёными import-проверками из самого скрипта.

**Архитектура — реализована и в двух ключевых местах ИСПРАВЛЕНА против
плана, записанного предыдущим агентом** (см. "Открытые вопросы" выше и
детали в skill `slava-model-rollouts`):
1. **Один env-worker на среду, общий для всех моделей**, а не
   предполагавшийся отдельный lerobot-специфичный LIBERO env для
   pi0/pi0.5/SmolVLA — после чтения реального кода `huggingface/lerobot`
   (`src/lerobot/envs/libero.py`) оказалось, что это тонкая gymnasium-обёртка
   вокруг того же самого `libero.libero.envs.OffScreenRenderEnv`, который
   наш собственный `env_worker_libero.py` уже использует. Одна реализация
   env-worker'а на LIBERO (порт 8701, env `slava-libero`) обслуживает
   OpenVLA-OFT и всех трёх lerobot-политик; одна на SimplerEnv (порт 8702,
   env `slava-simpler`) обслуживает GreenVLA-R0/R1 и тех же трёх
   lerobot-политик. Это не решение пользователя, а инженерное упрощение
   после того, как реальный API стал виден — не переоткрывать этот вопрос.
2. **`/predict`-контракт модель-сервера расширен полем `meta`**
   (`{task_uid, suite, environment}`) сверх `obs`/`instruction` — понадобилось
   для OpenVLA-OFT, у которого `unnorm_key` берётся из имени LIBERO suite
   (`libero_spatial`/`_object`/`_goal`), а не выводится из пикселей.

**Env-worker'ы — реально протестированы через живой HTTP**, не только
написаны: `src/slava_rollout/env_worker_libero.py` и `env_worker_simpler.py`
подняты вручную, `/reset` + `/step` вызваны curl'ом на реальных сценах из
`prompts_v0.jsonl` (`libero_goal__open_the_middle_drawer_of_the_cabinet`,
`simpler__widowx_stack_cube`) — оба вернули корректные observation
(agentview/wrist PNG, proprioception), `info.success`/`first_contact_object`/
`object_poses` из настоящей физики (robosuite/MuJoCo и SAPIEN
соответственно). Контакт-трекинг (`src/slava_rollout/contacts.py`) — эвристика
поверх `env.sim.data.contact` (LIBERO) и `scene.get_contacts()` (SimplerEnv),
явно помечена в skill как требующая проверки на обязательном
first-100-rollout ручном аудите из task.md, а не как гарантированно точная.

**Три model-server бэкенда написаны против реального, прочитанного кода
чужих репозиториев** (не по памяти/догадке):
`scripts/model_servers/greenvla_server.py` (github.com/greenvla/GreenVLA,
`load_pretrained_policy`+`select_action` — подтверждено их же
`examples/example_inference_bridge.py`), `lerobot_server.py` (обслуживает
pi0/pi0.5/SmolVLA через `huggingface/lerobot`'s `PreTrainedConfig`/
`get_policy_class`/`make_pre_post_processors`/`predict_action`, читает
`policy_cfg.input_features` в рантайме вместо хардкода имён ключей —
LIBERO-финетюны и zero-shot bridge-чекпойнты их не разделяют одинаково),
`openvla_oft_server.py` (переиспользует `GenerateConfig`/`get_model`/
`get_action` из github.com/**moojink**/openvla-oft — не
`openvla/openvla-oft`, той организации с этим репо нет). **Ни один из трёх
ещё не прогнан end-to-end** на момент этой записи — только env-worker'ы
реально проверены живой физикой; model-server'ы "должны работать", но
первая настоящая проверка — это smoke-test.

**Conda-окружения под каждую модель** (`slava-openvla` py3.10+torch,
`slava-lerobot` py3.12 — **современный `huggingface/lerobot` требует
Python>=3.12**, из документации `pyproject.toml`, — `slava-greenvla` py3.11)
создаются/устанавливаются в фоне этим агентом; по ходу найдены и
исправлены два реальных пакетных бага в чужих репозиториях (не в нашем
коде): GreenVLA репозиторий не собирается через `pip install -e .`
("[project.version] or [tool.poetry.version] is required" — их
`pyproject.toml` не имеет `version`, хотя их же README рекомендует `uv sync`,
который более снисходителен; починено локальной правкой
`version = "0.0.0"` в склонированную копию `/workspace/greenvla_repo/
pyproject.toml`, это не влияет на апстрим); `huggingface/lerobot` требует
Python≥3.12, а не 3.10/3.11, как можно было бы предположить — пересоздан env.

**Артефакты, созданные в этой сессии:** `src/slava_rollout/` (`schema.py`,
`storage.py` — от предыдущего агента; `contacts.py`, `imaging.py`,
`auto_label.py`, `clients.py`, `env_worker_libero.py`,
`env_worker_simpler.py` — новые), `scripts/run_rollouts.py`,
`scripts/model_servers/{base_server,greenvla_server,lerobot_server,
openvla_oft_server}.py`, `notebooks/02_rollout_camera_dashboard.ipynb`,
`.claude/skills/slava-model-rollouts/SKILL.md` (создан предыдущим агентом
пустым по названию, фактически написан в этой сессии). **Ничего из этого
ещё не закоммичено** — по правилам сессии коммиты/пуши только по явной
просьбе, а её не было.

**Дальше по плану (без дальнейших вопросов, раз пользователь снова
отошёл):** дождаться готовности всех пяти conda-окружений моделей, прогнать
`--smoke-test` (2 сцены/модель, только `en_canonical`) по одной модели за
раз, чинить реальные ошибки по мере появления (ожидаемо — первая реальная
проверка нечитанных частей API), и **если smoke-test пройдёт устойчиво —
пользователь явно попросил сразу запускать полный прогон на всех 5
моделях и 127 промптах**, не дожидаясь его возвращения. Если какая-то
модель не проходит smoke-test даже после разумной попытки почитать
трейсбек и починить — не гадать бесконечно: зафиксировать точную ошибку
здесь и продолжать с оставшимися моделями, а не блокировать весь прогон
из-за одной.

**Реальные баги/находки при первом прогоне smoke-test (pi0/LIBERO), все
исправлены в этой же сессии:**
1. **Второй инцидент с утечкой секрета в tool output** (первый — см. запись
   предыдущего агента про `HF_TOKEN`/`grep -A1 -B1` выше). Этот агент вызвал
   `env HF_TOKEN=$HF_TOKEN python -c ...` как видимую команду — `conda run`
   при ошибке напечатал полную командную строку, включая уже
   раскрытое значение токена, в tool output. **Правило на будущее, записано
   явно:** никогда не писать `HF_TOKEN=$VALUE` (даже через `$VAR`) как часть
   видимого текста команды — экспортировать переменную окружения отдельной
   командой (`export HF_TOKEN=...`) в том же шелле и звать `conda run`/любую
   другую команду уже без повторения токена в её собственной командной
   строке. **Пользователю стоит рассмотреть ротацию HF-токена ещё раз** —
   те же соображения, что и в первом инциденте.
2. **`torch`, поставленный по умолчанию (`pip install torch` без пина) в
   `slava-lerobot`, оказался версии 2.11.0+cu130 — эта сборка официально
   поддерживает только compute capability ≥7.5, а у V100 этого сервера
   CC=7.0 (Volta)**: явное предупреждение PyTorch при первом `torch.cuda`
   вызове. Это тот же класс проблемы, что описан в разделе про CUDA/GPU в
   базовом гайде (`AGENTS.md` verstack про Blackwell/cu124), но в обратную
   сторону — не "GPU новее чем сборка", а "сборка новее чем GPU новее не
   поддерживает старую архитектуру". Исправлено даунгрейдом до
   `torch==2.7.1+cu126` (та же версия, что и так зафиксирована апстримом в
   `pyproject.toml` GreenVLA и подтверждённо работает без предупреждений на
   этом железе). **Если снова будете переустанавливать `slava-lerobot` с
   нуля — сразу пинните `torch==2.7.1`, не полагайтесь на резолвер pip.**
3. **Реальный баг в `lerobot_server.py`** (не баг чужого репо): `PolicyFeature.
   type.value` — это ЗАГЛАВНАЯ строка (`"VISUAL"`/`"STATE"`), а код сравнивал
   с `"visual"`/`"state"` в нижнем регистре — фильтр молча не находил ни
   одной image-фичи. Исправлено сравнением с enum-членами `FeatureType.
   VISUAL`/`FeatureType.STATE` напрямую вместо строк. Заодно найдено и
   обработано: `lerobot/pi0_libero_finetuned` объявляет **3** image-фичи, а
   не 2 — третья `observation.images.empty_camera_0` (224×224, ниже
   разрешения двух настоящих камер 256×256) — это заглушка "камеры нет",
   которую чекпойнт при обучении всегда видел нулевой; код теперь кормит её
   нулевым изображением, а не дублирует туда agentview (что скормило бы
   модели данные не того распределения, которое она видела на трейне).

**Полное сквозное подтверждение (2026-08-05, ~00:15).** Через реальный
`scripts/run_rollouts.py --models openvla_oft --smoke-test` (не только
unit-тест бэкенда напрямую) впервые прошёл настоящий closed-loop эпизод:
env-worker `/reset`+`/step` × 300 шагов реальной физики LIBERO, model-server
`/predict` OpenVLA-OFT на каждом шаге, запись в `rollout_annotations.jsonl`
строго по 16 полям контракта task.md (`success=false`,
`failure_type_auto="no_action_or_timeout"` — модель не открыла ящик за
отведённые 300 шагов, правдоподобный результат, не ошибка пайплайна).
393.7 секунды на один LIBERO-эпизод (~6.5 минут) — то есть оценка
предыдущего агента "часы, не дни" была рассчитана на A100/RTX4090; на
одной V100 32GB этого сервера полный прогон 5 моделей × 127 промптов
(≈500+ эпизодов, с учётом что не каждая модель покрывает каждую сцену)
реалистично займёт **часы, растянутые на существенную часть суток**, а не
"несколько часов". Отдельно юнит-тестами (прямой вызов backend.predict())
подтверждены на реальных чекпойнтах: GreenVLA (`GreenVLA-5b-base-stride-1`),
pi0 (`pi0_libero_finetuned`), SmolVLA (`smolvla_libero`) — все вернули
осмысленные action-массивы правильной размерности. `pi0_base` (bridge
zero-shot) поймал CUDA OOM, но это оказалось артефактом того, что несколько
тяжёлых unit-тестов гонялись **одновременно** на одной GPU (openvla-oft 7B
+ pi0_base ~3B разом) в ходе отладки — не баг кода; настоящий
`run_rollouts.py` теперь физически не может повторить эту ошибку, см.
следующий пункт.

**Важный фикс архитектуры, найденный именно на этом этапе:** исходный
`WorkerPool` кэшировал **каждый** запущенный model-server до самого конца
всего процесса — значит один `run_rollouts.py --models <все 5>` к пятой
модели держал бы в GPU-памяти одновременно все 5 чекпойнтов (0.5B–7B) сразу,
почти гарантированный OOM на 32ГБ. Добавлен `WorkerPool.stop_model()`,
вызывается сразу после того, как у модели заканчиваются эпизоды — теперь
резидентна максимум одна модель за раз (env-worker'ы остаются жить между
моделями, они лёгкие). Чистое инженерное исправление постфактум, не
вопрос, требующий пользователя.

**Полный прогон (5 моделей × 127 промптов) запущен** по прямому
разрешению пользователя ("если всё будет норм — запускай на все 5 моделей
и 127 сцен, не дожидаясь меня"), командой:
`conda run -n slava-notebook python scripts/run_rollouts.py` (без
`--models`/`--smoke-test` — дефолт покрывает все 5 моделей). Ожидаемая
продолжительность — многие часы; отчёт (`scripts/generate_rollout_report.py`
→ `data/rollout_report.html`) уже написан и безопасен для перегенерации в
любой момент против частично заполненного `rollout_annotations.jsonl` — не
нужно дожидаться полного завершения, чтобы посмотреть текущий прогресс.

4. **Пакетный баг в самом репозитории GreenVLA** (не наш код):
   `pip install -e .` не собирался — `[project]` в их `pyproject.toml` не
   имеет `version` (их README рекомендует `uv sync`, который к этому
   снисходительнее), и после починки `version` — не собирался ещё раз, т.к.
   `[tool.poetry]` не объявляет `packages`, а poetry-core по умолчанию ищет
   папку `greenvla/`, которой нет (их код лежит в `lerobot/`, это старый
   форк lerobot, не пакет с именем `greenvla`). Исправлено двумя точечными
   правками в **склонированную копию** `/workspace/greenvla_repo/
   pyproject.toml` (`version = "0.0.0"` + `packages = [{include =
   "lerobot"}]` под `[tool.poetry]`) — апстрим не тронут, это не наш
   репозиторий и это временный локальный воркэраунд для установки на этом
   сервере.
5. **`openvla-oft`'s inference-only импорт неожиданно тянет `tensorflow`/
   `tensorflow_datasets`/`dlimp`** (через `prismatic/vla/datasets/rlds/` —
   код для RLDS-датасетов, не нужный для eval, но импортируется eagerly), а
   версия `protobuf`, которую резолвер поставил по умолчанию, несовместима
   с скомпилированными `tensorflow_metadata`'s `_pb2.py` (`gencode 6.31.1
   runtime 5.29.6` — protobuf gencode/runtime version guarantee violation).
   Исправлено апгрейдом `tensorflow>=2.16` (снимает верхний потолок
   `protobuf<5`) и `protobuf` до `>=6.31.1,<7`; резолвер после этого пишет
   warning о несовпадении с `openvla-oft`'s заявленным `tensorflow==2.15.0`
   пином — **не баг, просто конфликт заявленных версий, реальный импорт
   проходит чисто**, tensorflow тут не используется на пути инференса.

**06.08.2026 (03:xx–08:xx UTC), продолжение той же сессии — ещё 2 реальных бага
найдены через поведенческую сверку, прогон остановлен пользователем досрочно:**

6. **`conda run` не форвардил сигналы завершения дочернему процессу** —
   `proc.terminate()` на `subprocess.Popen`, обёрнутый в `conda run`, убивал
   только сам `conda run`-wrapper, а реальный python-процесс (model-server)
   оставался жить и держать GPU-память. Пойман на реальном CUDA OOM при
   старте OpenVLA-OFT, когда осиротевшие GreenVLA-R0/R1 серверы всё ещё
   держали ~31ГБ вместе. Исправлено process-group termination
   (`start_new_session=True` + `os.killpg(pgid, SIGTERM→SIGKILL)`) в
   `scripts/run_rollouts.py`.
7. **OpenVLA-OFT: пропущен обязательный gripper post-processing.** Самый
   значимый баг сессии, найден именно через требуемую пользователем
   поведенческую сверку, а не через код-ревью. `experiments/robot/robot_
   utils.py`'s `get_action()` возвращает gripper-канал в конвенции OpenVLA's
   dataloader'а (0=close..1=open), но `env_worker_libero.py`'s OSC_POSE
   контроллер ждёт (-1=open..+1=close) — наш `openvla_oft_server.py` не
   применял `normalize_gripper_action(binarize=True)` + `invert_gripper_
   action()`, которые `run_libero_eval.py` (референсный скрипт авторов)
   применяет перед отправкой действия в среду. Симптом: 13 эпизодов подряд
   (2 разные задачи) со 100% `no_action_or_timeout` и плоским
   `gripper_state` в step-логах — при заявленных авторами ~97% SR на этом
   чекпойнте такая единообразность failure type и есть сигнал бага, не
   сложности задачи. После фикса: то же самое действие теперь бинаризуется
   в ±1.0, гриппер реально замыкается на объекте (`contacts` перестают быть
   пустыми), failure type становится разнообразным (`target_grounding_
   error`/`relation_binding_error`/`negation_error`). 13 заражённых записей
   вычищены из `rollouts/rollout_annotations.jsonl` (бэкап:
   `rollout_annotations.jsonl.bak_before_openvla_fix`), их episode-папки
   перенесены в `rollouts/episodes_archived_buggy_openvla_gripper/` (не
   удалены), затем эпизоды пересняты заново с фиксом.

**Полный прогон запущен по приоритету пользователя** (лимит времени ~13ч,
явный порядок: GreenVLA-R0/R1 первые как самые важные → OpenVLA-OFT →
pi0/pi0.5/SmolVLA последними, ок если не успеют). **Остановлен пользователем
досрочно** в 08:33 UTC ("we have no 7 hours, quit this run") на пути к
task.md-аудиту и финальному отчёту. Финальное покрытие данных на момент
остановки (см. `data/rollout_report.html`, таблица "Фактическое покрытие"):

```
GreenVLA-R0:        28/28  готово
GreenVLA-R1(bridge): 28/28  готово
OpenVLA-OFT:         21/99  частично (~365с/эпизод; полный прогон занял бы ещё ~8ч)
pi0:                  0/127 не начат
pi0.5:                0/127 не начат
SmolVLA:               0/127 не начат
```

Итого 77 эпизодов в `rollouts/rollout_annotations.jsonl`. Процессы остановлены
чисто (`kill -TERM` на pgid оркестратора и OpenVLA-OFT model-server'а — тот же
process-group fix из п.6 выше сработал корректно, GPU освобождена, никаких
недописанных/битых записей, т.к. `append_annotation` пишет только по
завершении эпизода). env-worker'ы (LIBERO :8701, SimplerEnv :8702) оставлены
живыми (лёгкие, не держат GPU) — можно возобновить `run_rollouts.py --models
pi0 pi05 smolvla` (resume-by-run_id пропустит уже готовые 77) без пересборки
окружений, если пользователь решит доснять остальное отдельным запуском.
`scripts/_report_loop.sh` (pid 26371, автообновление отчёта каждые 10 мин)
тоже остановлен — данные теперь статичны, отчёт сгенерирован вручную финальным
проходом.

**Находка из поведенческой сверки готовых данных (не баг, см.
`data/rollout_report.html` §6):** SR=0% на всех 77 эпизодах без исключения —
это делает Δlang-таблицу вырожденной на этом объёме (все SR=0%, значит все
gap'ы = 0). Проверено, что `success` берётся напрямую из нативного
`env.check_success()`/`info["success"]`, не из нашей эвристики — не баг
разметки. Отдельно на sample эпизодов по md5 кадров agentview: **GreenVLA-R0
систематически "замирает"** (identical consecutive frames) на 24–40 из 60
шагов в каждом проверенном эпизоде, GreenVLA-R1 — заметно меньше (1–14),
OpenVLA-OFT — почти никогда (max run = 1 на LIBERO). Раз паттерн
модель-специфичен при общем env-worker коде для GreenVLA-R0/R1 — похоже на
реальное поведенческое различие между R0 (base curriculum stage) и R1
(следующая стадия), а не на инфраструктурный баг; стоит перепроверить на
большем объёме, если прогон возобновится.

**05.08.2026, новая сессия, 3-й сервер (Vast.ai, 4×V100-32GB) — причина
SR=0% для OpenVLA-OFT найдена и исправлена, подтверждено smoke-test'ом.**
Полная деривация — в skill `slava-model-rollouts`, раздел "SR=0% root cause
(found 2026-08-05...)". Кратко: три независимых от языка бага в
OpenVLA-OFT-пайплайне, все найдены чтением реального `run_libero_eval.py` из
`moojink/openvla-oft`, а не гаданием — (1) отсутствие open-loop chunk replay
(уже была зацепка в брифе, подтверждена и исправлена), (2) **картинка
подавалась зеркально по горизонтали** — `env_worker_libero.py` делает только
вертикальный флип (для человекочитаемого D1-дашборда), а OpenVLA-OFT
тренировался на full 180°-повороте; исправлено точечно в
`openvla_oft_server.py`, `env_worker_libero.py` не тронут, (3) не хватало 10
шагов физического "отстоя" перед первым обращением к модели после
`set_init_state()`. После фикса всех трёх: `--smoke-test` (2 эпизода,
`en_canonical`) — **2/2 success** (было 0/21 реальных эпизодов в прошлой
сессии), плюс эпизоды стали в 5-8 раз быстрее (33-76с вместо ~394с) — модель
теперь спрашивается раз в 8 шагов, а не на каждом шаге. Отдельно подтверждено:
`en_canonical`-промпт для проверенной сцены дословно совпадает с
`benchmark.get_task(i).language` из живого LIBERO benchmark API (не с текстом
`:language` внутри самого `.bddl`-файла, который устарел и не совпадает) —
значит успех получен на буквально оригинальном промпте датасета, не на
SLAVA-перефразировке. **pi0/pi0.5/SmolVLA/GreenVLA пока НЕ проверены на этом
же уровне строгости** (собственная image-preprocessing/action-конвенция
каждого не сверена построчно с их eval-кодом) — не доверять их данным из
прошлой сессии, пока это не сделано. `HF_TOKEN` добавлен пользователем в
`~/.bashrc` на этом сервере, извлечён безопасным способом (`awk`, без
`source`/`grep -A/-B`), устанавливать заново на будущих машинах тем же
способом.

**Открытый бэклог, требующий пользователя (не может быть закрыт агентом
самостоятельно):**

- **Ручная валидация первых 100 rollouts** (task.md, "Auto-labeling для
  первых прогонов": "проверить первые 100 rollouts и оценить точность
  auto-labeler'а") — explicit требование человеческой проверки, не выполнено.
  77 эпизодов уже готовы (близко к 100) — можно проверить сейчас на этом
  объёме, а не ждать полного прогона.
- **pi0 / pi0.5 / SmolVLA** — 0 эпизодов, требуют отдельного продолжения
  прогона (см. команду выше), решение когда/если запускать — за пользователем
  (время-бюджет уже был превышен один раз).
- **v0.1 (projection 3D→2D crosshair) и pointing-зонд GreenVLA** — сознательно
  не начаты, task.md сам относит их к шагу после behavioral pilot, не к
  Definition of Done pilot v0 — не блокер, но следующий шаг проекта.

**05.08.2026, миграция на локальную машину пользователя (MacBook M3, без
CUDA) — сессия на Vast.ai сервере закрывается.**

Этот сервер (`$PUBLIC_IPADDR`=159.48.242.12, container `$CONTAINER_ID`=46835455)
**не имеет персистентного volume** (`workspace_is_volume=false`) — весь
`/workspace`, включая этот репозиторий и все результаты прогонов, **пропадёт
безвозвратно** при recycle/destroy инстанса (но не при простом stop/start —
это переживёт). Пользователь сам решает, останавливать/уничтожать ли этот
инстанс; агент этого не делает самостоятельно. Важно: пока инстанс не
уничтожен, к нему можно вернуться и доснять pi0/pi0.5/SmolVLA (см. предыдущий
абзац) — CUDA-часть пайплайна физически не может работать на локальном Mac.

**Результаты прогона упакованы для скачивания**, т.к. `rollouts/` (2.1ГБ,
16628+ файлов: PNG-кадры камер + step-логи + `rollout_annotations.jsonl`)
сознательно не идёт в git (см. `.gitignore`, добавлено этой сессией) — слишком
много бинарных данных для репозитория:

```
/workspace/downloads/slava_rollout_results_2026-08-05.zip   (1.7 ГБ)
  ├── rollouts/rollout_annotations.jsonl (+ .bak_before_openvla_fix)
  ├── rollouts/episodes/<run_id>/{camera/{agentview,wrist}/*.png, steps.jsonl}
  ├── rollouts/logs/*.log
  └── data/rollout_report.html (копия, идентична закоммиченной в git)
```

Сознательно **не включена** в архив `rollouts/episodes_archived_buggy_
openvla_gripper/` (371МБ, 13 эпизодов с багом gripper post-processing до
фикса, см. "Real bugs found" в skill `slava-model-rollouts`) — контаминация
уже задокументирована текстом, сами данные не нужны для анализа; при желании
всё ещё лежат на сервере нетронутыми, пока инстанс жив.

Скачать (структура зипа рассчитана на распаковку прямо в корень
`git clone`-нутого репозитория — `rollouts/` и `data/` лягут на свои места):

```
scp -P 49987 root@159.48.242.12:/workspace/downloads/slava_rollout_results_2026-08-05.zip ~/Downloads/
# затем на Mac, внутри свежего git clone:
cd SLAVA_dev && unzip ~/Downloads/slava_rollout_results_2026-08-05.zip
```

(порт/IP — текущие для этого инстанса, могут смениться, если инстанс
перезапустят; актуальные значения — `$VAST_TCP_PORT_22`/`$PUBLIC_IPADDR` на
самом сервере, или в Vast.ai веб-консоли). `rsync -avP` вместо `scp` — тот же
адрес/порт, если хочется докачивать с возобновлением при обрыве соединения на
таком объёме.

**Процессы на сервере остановлены чисто** для миграции: оба env-worker'а
(LIBERO :8701, SimplerEnv :8702, `kill -TERM`, не аварийно) и
`scripts/_report_loop.sh` (автообновление отчёта). Оркестратор и model-server'ы
уже были остановлены раньше в этой же сессии (см. выше). GPU полностью
свободна. Если пользователь вернётся на этот сервер продолжить
pi0/pi0.5/SmolVLA — команды перезапуска env-worker'ов есть в skill
`slava-model-rollouts`, раздел "What's still open".

**05.08.2026, 3-й сервер (Vast.ai, 4×V100-32GB), продолжение — параллельный
прогон всех 5 моделей на 4 GPU, жёсткий дедлайн сессии ~3ч.** Полная
деривация багов — в skill `slava-model-rollouts` (разделы "SR=0% root
cause..." и "pi0/pi0.5: cuDNN..."). Кратко: OpenVLA-OFT SR=0%-баг найден и
исправлен (3 независимых от языка бага: отсутствие open-loop chunk replay,
зеркальная по горизонтали картинка, отсутствие physics-settle steps) —
подтверждено smoke-test 2/2, затем **полный прогон завершён: 99/99, 74.7%
SR**. При аудите lerobot-моделей найдены и исправлены ещё два похожих класса
бага в общем `lerobot_server.py` (другая image-flip конвенция, неправильный
proprioception layout) плюс третий, специфичный для pi0/pi0.5
(PaliGemma/SigLIP): cuDNN не находит engine для bf16/дефолтного conv2d на
V100 — исправлено `torch.backends.cudnn.enabled = False`. Добавлена
multi-GPU шардинг-поддержка в `run_rollouts.py` (`--shard-index`/
`--num-shards`, `SLAVA_MODEL_PORT_<KEY>` env-override) и SIGTERM-обработчик
(bare kill к оркестратору раньше не гонял `finally: pool.stop_all()`,
сиротил env-worker/model-server процессы — теперь чинится сам).
Из-за дедлайна сессии **pi0/pi0.5/SmolVLA/GreenVLA-R0/R1 запущены
параллельно на 4 GPU, но покрытие частичное** (эпизод занимает
~210-670с в зависимости от модели, полные 127/28 не успевают) — актуальные
цифры покрытия и SR смотрите в `data/rollout_report.html` (перегенерируется
`python scripts/generate_rollout_report.py` против текущего
`rollout_annotations.jsonl` без правок кода). `rollout_annotations.jsonl`
со старого сервера (77 эпизодов, включая уже готовые OpenVLA-OFT/GreenVLA)
пользователь решил НЕ переносить на эту машину — весь прогон здесь идёт с
нуля, `load_completed_run_ids()` резюмирует сам по мере накопления данных.

**Пользователь явно переприоритизировал: GreenVLA-R0/R1 — главный приоритет
покрытия до дедлайна, pi0/pi0.5/SmolVLA — опционально** (не страшно, если не
успеют). GPU1 переключен с pi0.5 на GreenVLA-R1, оба GreenVLA теперь бегут
параллельно на GPU0/GPU1. Заодно подтверждено на новом железе: R0
по-прежнему "замирает" (md5 по кадрам agentview: 36/60 identical
consecutive — тот же диапазон 24-40/60, что в прошлой сессии на другом
сервере) — воспроизводится независимо на другом хосте, усиливает вывод, что
это поведение модели, а не инфраструктурный баг.

**05.08.2026, ~11:11 UTC — журнал сессии для восстановления после обрыва.**
Пользователь явно попросил логировать основные действия на случай обрыва
сессии/исчерпания квоты — этот блок для этого. Если читаешь это в новой
сессии: смотри также skill `slava-model-rollouts` (все технические детали
багов) и просто продолжай мониторить/дособирать данные, ничего заново не
переоткрывай.

**Хронология этой сессии (сервер Vast.ai, 4×V100-32GB, полностью с нуля —
никакой персистентности с прошлых серверов):**
1. Bootstrap (`scripts/bootstrap.sh --skip-libero-datasets --skip-smoke-test`) —
   `slava-libero`/`slava-simpler`/`slava-notebook` подняты, зелёные.
2. Собраны 3 новых conda-env для моделей: `slava-openvla` (torch 2.2.0 — этот
   пин требует openvla-oft's pyproject.toml, НЕ 2.7.1; numpy<2 + opencv<4.10
   нужны из-за ABI-конфликта с torch 2.2.0), `slava-lerobot` (torch 2.7.1+cu126,
   torchvision 0.22.1 — pip install -e ".[smolvla]" САМ подтягивает
   несовместимый torch 2.11/torchvision 0.26, пере-пиновать после установки
   обязательно), `slava-greenvla` (torch 2.7.1, репозиторий требует локального
   патча `pyproject.toml`: `version = "0.0.0"` + `packages = [{include =
   "lerobot"}]` под `[tool.poetry]` — не трогать апстрим, это только в
   `/workspace/greenvla_repo`).
3. **OpenVLA-OFT SR=0% диагностирован и исправлен** — 3 бага (chunk replay,
   image mirror, missing settle steps), все с деривацией из реального
   эталонного кода `moojink/openvla-oft`. Smoke-test 2/2 → полный прогон
   **99/99, 74.7% SR** (было 0/77 в прошлых сессиях). Детали — skill,
   раздел "SR=0% root cause found 2026-08-05".
4. Добавлена multi-GPU шардинг-инфраструктура в `scripts/run_rollouts.py`:
   `--shard-index`/`--num-shards` (делит список эпизодов round-robin),
   `SLAVA_MODEL_PORT_<MODEL_KEY>` env-override (аналог уже существовавших
   `SLAVA_LIBERO_PORT`/`SLAVA_SIMPLERENV_PORT`) — нужно, чтобы несколько
   параллельных процессов на разных GPU не бились портами. Плюс SIGTERM-хендлер
   в `main()` (`_handle_sigterm` → `SystemExit`, чтобы `finally:
   pool.stop_all()` реально срабатывал при остановке оркестратора вручную —
   раньше bare kill сиротил env-worker/model-server).
5. Пробовали 2 процесса OpenVLA-OFT (7B) на одной GPU — **не сработало**, OOM
   (32.4/32.8GB), откатились на 1 процесс/GPU для этой модели. Для лёгких
   моделей (SmolVLA 2.4GB) двойной запуск на одной GPU работает нормально
   (см. п.9).
6. **Аудит lerobot-моделей (pi0/pi0.5/SmolVLA)** нашёл и исправил ещё 3 бага
   в общем `scripts/model_servers/lerobot_server.py`: (a) другая
   image-flip-конвенция (lerobot's LiberoEnv вообще не флипает, в отличие от
   и env-worker'а, и OpenVLA-OFT), (b) неправильный proprioception layout
   (нужен тот же `eef_pos+axis_angle+gripper_qpos`, что у OpenVLA-OFT), (c)
   cuDNN-краш (`GET was unable to find an engine...`) на SigLIP conv2d у
   pi0/pi0.5 (PaliGemma-based) на V100 — исправлено `torch.backends.cudnn.
   enabled = False`. Затем (d) **4-й баг**: lerobot-модели тоже нуждаются в
   `num_steps_wait=10` (как OpenVLA-OFT), подтверждено чтением
   `lerobot.envs.libero.LiberoEnv`'s дефолта — добавлено в
   `LIBERO_NUM_STEPS_WAIT` для pi0/pi05/smolvla, все три перезапущены.
7. **GreenVLA-R0 freezing подтверждён воспроизводимым на новом железе**
   (md5 по кадрам: 36/60 identical consecutive, тот же диапазон, что в
   прошлой сессии на другом сервере) — усиливает вывод "поведение модели, не
   инфраструктура". **GreenVLA-R1 подтверждён НЕ замирающим** (тот же md5-тест
   на первом эпизоде R1: longest run = 1 из 64 кадров) — тоже совпадает с
   прошлой сессией, реальное поведенческое различие R0/R1, не артефакт
   железа/сессии.
7b. **Проверка "подозрительный ли SR" по просьбе пользователя** (после
    ~40 эпизодов pi0.5 с 0% успеха): проверил `gripper_state` (среднее
    `robot0_gripper_qpos`) — оставалось ~0 весь эпизод даже при контакте с
    целевым объектом, показалось подозрительным. **Ложная тревога** —
    сравнение с УСПЕШНЫМ эпизодом OpenVLA-OFT на той же задаче показало
    точно такое же поведение (`gripper_state`≈0 почти весь эпизод, слегка
    меняется только в последних шагах) — это особенность двупалого gripper'а
    (симметричные пальцы, среднее qpos не отражает open/close), не баг. Реальный
    вывод: pi0/pi0.5/SmolVLA пока (на момент записи) видели только
    `libero_goal`-задачи (индексы 0-2 из 9 уникальных LIBERO-задач в
    `prompts_v0.jsonl`: `open_middle_drawer`, `push_plate`, `wine_bottle_rack`)
    — те же задачи, где даже OpenVLA-OFT слаб (17-50% SR, не 74%+). Решающий
    тест: `libero_object`-задачи (индексы 4-7, простой pick-and-place, где
    OpenVLA-OFT получает 100% = 6/6 на каждой) начнутся, когда эти модели
    дойдут дальше по списку промптов — если там ТОЖЕ 0%, это станет весомым
    сигналом реального бага, а не просто сложности задачи. Проверить это в
    следующей итерации мониторинга.

    **Обновление: сигнал подтвердился.** pi0 дошёл до `libero_object`
    (butter/cream_cheese/milk) — 0/18, во всех `first_contact_object=None`
    (не просто неверный объект — вообще ноль контакта), чище паттерн, чем на
    `libero_goal`. Отрендерил картинку, которую реально видит pi0 (после
    "отмены флипа env-worker'а") — выглядит перевёрнутой/неправдоподобной.
    Откатил image-flip фикс в `lerobot_server.py`, перезапустил pi0 —
    результат тот же: 0% SR, `first_contact_object` всё ещё `null`. Значит
    ориентация картинки — не (единственная) первопричина, проверено A/B на
    живых данных. **Вопрос остаётся открытым**, не решено из-за дедлайна и
    репriorитизации на GreenVLA-R0/R1. Полная запись — skill
    `slava-model-rollouts`, "Fifth issue, still OPEN/unresolved".

8. Пользователь дважды корректировал приоритеты в реальном времени: сначала
   "покрыть GreenVLA-R0/R1 — главное, остальное опционально" (GPU1
   переключен с pi0.5 на greenvla_r1_bridge), затем "давай всё-таки прогоним
   все модели, ещё пара часов есть, следи за en_canonical на подозрительный
   SR". В ответ pi0.5 запущен ВТОРЫМ процессом на GPU2 (рядом со SmolVLA —
   лёгкие модели, суммарно ~20/32GB, безопасно).
9. Дедлайн сессии — ориентировочно **~13:30 UTC** (3ч от начала работы плюс
   продление "ещё пара часов" в ~11:05 UTC — точную границу не проверяли,
   ближе к делу уточнить у пользователя, если он на связи, иначе
   консервативно закругляться к 13:00-13:15).

**Текущее состояние процессов на момент записи (11:11 UTC) — для
возобновления, если что-то упадёт:**

```
GPU0: greenvla_r0        (env-worker SimplerEnv :8702 default, model-server :8801)
GPU1: greenvla_r1_bridge (env-worker SimplerEnv :8752, model-server :8802)
GPU2: smolvla            (env-worker LIBERO :8721/SimplerEnv :8722, model-server :8806)
      + pi05              (env-worker LIBERO :8731/SimplerEnv :8732, model-server :8825) — ВТОРОЙ процесс, та же GPU
GPU3: pi0                (env-worker LIBERO :8741/SimplerEnv :8742, model-server :8804)
```

Все запущены как `conda run -n slava-notebook python scripts/run_rollouts.py
--models <X>` с `CUDA_VISIBLE_DEVICES=<N>` и соответствующими
`SLAVA_LIBERO_PORT`/`SLAVA_SIMPLERENV_PORT`/`SLAVA_MODEL_PORT_<KEY>` (см.
конкретные команды в истории bash-вызовов этой сессии, либо просто
перезапустить с любыми свободными портами — resume безопасен по `run_id`).
Логи — `rollouts/logs/<model>_full*.log` (оркестратор) и
`rollouts/logs/model_server_<model>_<port>.log`/`env_worker_<ENV>_<port>.log`.

**Если сессия прервалась и её нужно продолжить:**
1. `ps aux | grep run_rollouts` — проверить, что ещё живо.
2. `nvidia-smi` — проверить занятость GPU.
3. Для упавших моделей — просто перезапустить той же командой (`--models
   <key>`, свои порты, `CUDA_VISIBLE_DEVICES`) — `load_completed_run_ids()`
   продолжит с того места, где остановились, дублирования не будет.
4. Если что-то зависло с ошибками — сначала `curl
   http://127.0.0.1:<model_port>/predict_chunk` напрямую с реальным `obs` (из
   живого `/reset` env-worker'а) для получения настоящего traceback, а не
   гадать по логам оркестратора (Flask прячет traceback в JSON-теле, не в
   stdout) — see skill, "Process-management lesson".
5. **Смотреть на прогресс:** `python3 -c "import json; ..."` по
   `rollouts/rollout_annotations.jsonl`, группировка по `model`/`success`
   (см. примеры команд в истории сессии) — просто и быстро.
6. **Ближе к дедлайну:** остановить все процессы (`kill -TERM <pid>` их
   ОРКЕСТРАТОРА, не process group — SIGTERM-хендлер теперь сам корректно
   гасит детей), перегенерировать отчёт (`conda run -n slava-notebook python
   scripts/generate_rollout_report.py`), проверить `data/rollout_report.html`
   глазами, обновить этот раздел AGENTS.md финальными цифрами.

**05.08.2026, ~14:30 UTC — найден и подтверждён реальный корневой баг
GreenVLA: gripper range mismatch.** Полная деривация — skill
`slava-model-rollouts`. Кратко: сырой gripper-канал GreenVLA лежит в [0,1]
(0=закрыт, 1=открыт), а SimplerEnv/ManiSkill2's WidowX-контроллер
(`PDJointPosMimicControllerConfig(..., normalize_action=True)`) ожидает
[-1,1] — команда "закрыть" интерпретировалась как ПОЛУоткрыто, гриппер
никогда не сжимался достаточно для устойчивого захвата. Исправлено рескейлом
`2x-1` в `scripts/model_servers/greenvla_server.py::predict_chunk()` —
**это общий файл для R0/R1/R2**, фикс уже применён ко всем трём. Empирически
подтверждено на R2: **1/4 = 25% SR** сразу после фикса (было 0% на десятках
эпизодов до него) — реальный, не единичный успех. Дополнительно по пути
исправлен `action_horizon=2` (их README: "For Bridge (WidowX) benchmarking
on SimplerEnv we used action_horizon=2", мы использовали 1) — не сам решил
проблему, но обоснованно правильнее. Также найден баг разметки D4-сцены
`widowx_stack_cube`: `slots.forbidden` совпадает с `reference`-объектом,
из-за чего `negation_error` ложно срабатывает на легитимный контакт с
поверхностью размещения — влияет только на `failure_type_auto`, не на сам
`success`. **R0/R1 получили тот же фикс в коде, но НЕ переисследованы
заново с ним** (пользователь явно отложил их в беклог, все GPU отданы R2 при
нехватке времени) — при возобновлении сессии сначала прогнать R0/R1 с уже
исправленным `greenvla_server.py`, скорее всего SR тоже вырастет.

**Пользователь спросил про skill на каждую из моделей (OpenVLA-OFT, pi0,
pi0.5, SmolVLA, GreenVLA)** — сделано позже в этой же сессии, см. следующий
раздел.

### Продолжение той же сессии: коммит/пуш, затем camera-swap баг у pi0/pi0.5/SmolVLA

После первого коммита/пуша (docs/ + все фиксы) пользователь попросил
продолжить по бэклогу. Сделано:

- **Report provenance-аудит** (по запросу пользователя "давай перепроверим,
  что в метрики не попали статистики из багованных запусков"):
  `generate_rollout_report.py` теперь сравнивает mtime первого сохранённого
  кадра каждого эпизода с mtime файла model-server'а, который его
  произвёл, и **исключает из всех агрегатов** модели, у которых часть
  эпизодов собрана до последнего фикса того файла — pi0 (67/127), pi0.5
  (58/127), SmolVLA (24/47) на тот момент были смешанной провенанс, OpenVLA-
  OFT (99/99) и GreenVLA-R2 (28/28) — чистые. Секция "Валидность данных" в
  отчёте показывает это явно, не молча.
- **Галерея камер переделана в grid** по запросу пользователя ("побольше
  видео... в таблице") — сетка по моделям, несколько эпизодов на разных
  промпт-вариантах (round-robin, не почти-дубликаты) вместо одной колонки.
- **GreenVLA-R0/R1 rerun с gripper-фиксом запущен** на всех 4 GPU (backlog
  п.1) — 2 шарда на модель.
- **Найден и исправлен реальный баг у pi0/pi0.5/SmolVLA на LIBERO: agentview
  и wrist камеры были перепутаны местами.** Это и есть настоящая причина
  0%/1.6%/0% SR на `libero_object` — не gripper range (гипотеза из
  предыдущего бэклога) и не image orientation (уже проверено и исключено
  ранее). Дерево доказательства: у всех трёх LIBERO-чекпойнтов
  (`lerobot/pi0_libero_finetuned`, `pi05_libero_finetuned`,
  `HuggingFaceVLA/smolvla_libero`) объявлены фичи с именами
  `observation.images.image`/`image2` — без подстроки "wrist". Собственный
  класс `LiberoEnv` в `huggingface/lerobot`
  (`src/lerobot/envs/libero.py:158-159`) явно маппит
  `agentview_image → "image"`, `robot0_eye_in_hand_image → "image2"` — т.е.
  "image" это ГЛАВНАЯ камера, "image2" это wrist. Наш `_wrist_first` в
  `lerobot_server.py` сортирует по подстроке "wrist" в имени — для этих
  чекпойнтов это no-op, и код падал на позиционное присвоение
  (`image_feature_names[0] <- real_cameras[0]`, где
  `real_cameras=[wrist, agentview]`) — то есть wrist-камера уходила в слот
  "image" (главная сцена), а agentview — в слот "image2" (wrist). Полностью
  перепутано для КАЖДОГО эпизода pi0/pi0.5/SmolVLA на LIBERO, собранного до
  этого фикса. Исправлено явным `_LIBERO_CAMERA_NAME_MAP` в
  `lerobot_server.py`, специфичным для этих двух имён (не трогает
  zero-shot SimplerEnv чекпойнты). Полная деривация — skill
  `slava-lerobot-policies`.
- **245 старых (баганых) эпизодов pi0/pi0.5/SmolVLA LIBERO вычищены** из
  `rollout_annotations.jsonl` (архив директорий:
  `rollouts/episodes_archived_lerobot_pre_camera_swap_fix/`, бэкап JSONL:
  `.bak_before_lerobot_camera_swap_fix`) — чтобы rerun пересобрал их заново
  под тем же run_id, а не был пропущен `load_completed_run_ids()`.
- **Rerun pi0/pi0.5/SmolVLA запущен** на всех 4 GPU параллельно с
  GreenVLA R0/R1 (GPU1 несёт 3 процесса — ~31.2/32.8GB, впритык, но
  работает). **Первый же эпизод pi0 после фикса — реальный success**
  (`en_canonical`, было 0% на сотнях эпизодов до этого) — сильное
  подтверждение, что баг найден верно.
- **Skill разбит**: `slava-model-rollouts` (общая архитектура, контракты,
  process-management lessons) + `slava-openvla-oft` + `slava-lerobot-
  policies` + `slava-greenvla` (каждый — API конкретного вендора + все
  найденные баги для него).

### Третья часть сессии: пользователь усомнился в R1-результате → найден настоящий баг + pure-upstream репро

Пользователь: GreenVLA сам заявляет неплохой Entire Avg SR на SimplerEnv для
R1 (72.9%), а у нас 0/28 (хоть и с реальным grounding) — попросил проверить
все неочевидные места, а затем прямо воспроизвести их метрики их же кодом
(клонировать репо, их checkpoint, их же SimplerEnv-код), выделив под это
одну GPU, чтобы понять — модель объективно не справляется именно со
stacking, или у нас баг.

**Проверено и ИСКЛЮЧЕНО** (5 неочевидных мест, до нахождения реальной
причины): TimeLimit/max_steps (корректно обрывается на 60, не 120 — было
ложное подозрение на 138-шаговый эпизод, оказался склейкой 3 старых попыток
в одном append-only файле), `prepackaged_config`/visual-matching (применяется
корректно), success-condition в `evaluate()` (стандартная bbox+contact
проверка), у GreenVLA нет отдельного SimplerEnv eval-скрипта вообще (только
inference-примеры). Также обнаружено, что их README-число 72.9%/80.5% —
**агрегат по всем 4 bridge-задачам**, не per-task для stacking специфично —
сравнение с нашим числом на одной (вероятно самой сложной) задаче было
нечестным независимо от корректности пайплайна.

**Найден настоящий баг (6-е, неочевидное место): rotation representation
mismatch.** `PDEEPoseController.compute_target_pose()`
(`ManiSkill2_real2sim/agents/controllers/pd_ee_pose.py:195`) делает
`Rotation.from_rotvec(action[3:6])` — контроллер ожидает **axis-angle**
(rotation vector), не Euler-углы. GreenVLA же по своей документации выдаёт
`[x,y,z,roll,pitch,yaw,gripper]` — именно Euler-конвенция (в отличие от
LIBERO/OpenVLA-OFT, где явно "axis_angle" в терминологии для той же по сути
величины — другая embodiment, другая конвенция). Подтверждено НЕ догадкой,
а прямым чтением SimplerEnv's own эталонного RT1-wrapper'а
(`simpler_env/policies/rt1/rt1_model.py`): там есть конкретно
`action_rotation_mode == "rpy"` ветка, которая делает
`euler2axangle(roll, pitch, yaw)` **перед** отправкой в тот же самый env —
то есть эта конверсия — не наша придумка, а то, что валидированные модели в
этом же харнессе обязаны делать. `greenvla_server.py` отправлял
roll/pitch/yaw как есть, без конверсии — for малых углов axis-angle и Euler
похожи (почему грубое дотягивание/захват всё же работал), но расходятся на
реальных величинах — ровно то, что объясняет "хватает правильный кубик,
никогда не стекает точно" (relation_binding_error вместо success).

**Фикс:** `chunk[:,3:6] = euler2axangle(roll,pitch,yaw)` (через
`transforms3d`, добавлен в `slava-greenvla` conda env) в
`greenvla_server.py::predict_chunk()`, после существующего gripper-рескейла.

**Pure-upstream репро (без единой строчки SLAVA_dev кода) — методология и
статус:** новый conda env `greenvla-simpler-repro` (`/venv/greenvla-simpler-
repro`), собран С НУЛЯ (не `conda create --clone` — попытки клонировать
`slava-greenvla` И `slava-simpler` дважды падали на conda solver'е, который
спотыкается о pip-only пакеты при клонировании смешанных conda+pip envs;
известное ограничение conda, не наша ошибка). Установлено: `pip install -e
ManiSkill2_real2sim -e SimplerEnv` (SimplerEnv's own env-side код) +
`pip install -e .` из `greenvla_repo` (их же inference-код) в ОДИН env.
**Реальный, воспроизводимый на этой машине баг найден по пути:**
`sapien==2.2.2` (собран до numpy 2.0) segfault'ит на `env.step()` с numpy≥2 —
подтверждено дифом версий пакетов между рабочим `slava-simpler` (numpy
1.24.4) и падающим свежим env (numpy 2.4.6, подтянутый транзитивно через
GreenVLA-стек). Фикс: `numpy==1.26.4` (граница — GreenVLA-стек, конкретно
`pandas`/`datasets`, требует `>=1.26.0`, а `sapien==2.2.2` совместим только
с numpy 1.x ABI — 1.26.4 последняя 1.x-версия, устраивает обе стороны).
Скрипт-репро (не в репозитории, в scratchpad):
воспроизводит ровно тот же generic client-server паттерн, что и остальные
policy wrapper'ы в SimplerEnv (RT1Inference/OctoInference) — минимальный
клей между их API, не переизобретение ни одной из сторон.
**Первый прогон (R1-bridge, 20 эпизодов, с фиксами gripper+rotation,
GPU3): уже 1/8 = реальный success (ep 3, 16 шагов) на момент записи**,
прогон продолжается — сравнение "с фиксами vs без" и финальное число будет
дописано сюда после завершения.

**Параллельно (тот же вывод, что фикс работает) — R0/R1 rerun через НАШ
собственный пайплайн с новым rotation-фиксом запущен на GPU1/GPU2** (старые
28+28 pre-rotation-fix эпизода вычищены — архив
`rollouts/episodes_archived_greenvla_r0_r1_pre_rotation_fix/`, бэкап
`.bak_before_greenvla_rotation_fix` — иначе `load_completed_run_ids()`
пропустил бы их как уже готовые). GPU0 занята SmolVLA (доигрывает шард 3,
приостановленный ранее ради дебага — вернул на месте).

## Бэклог (актуализирован 05.08.2026, конец сессии — читать вместо всех более старых версий этого раздела выше)

Всё, что было в предыдущих версиях этого раздела и не повторено ниже, **уже
сделано**. Это финальный срез на момент хэндоффа; см. "Продолжение сессии"
подразделы выше (особенно "пользователь усомнился в R1-результате") для
полной хронологии находок, если нужны подробности рассуждений.

**ГЛАВНОЕ, что должен сделать новый агент первым делом**: на момент записи
на GPU **всё ещё выполняются 5 фоновых процессов** (см. точный список в
подразделе прямо ниже, "Живые процессы на момент хэндоффа"). Не убивать
их бездумно — сначала `ps aux | grep run_rollouts.py` и `nvidia-smi`, дать
им доиграть (`load_completed_run_ids()` резюмит безопасно, если что-то
всё-таки упадёт/зависнет). Когда все допишут, дальше по списку:

1. **GreenVLA R0/R1/R2 rotation-фикс rerun** — R2 **готов раньше** (обычно
   заканчивается первым, 28 эпизодов уже почти на месте), R0/R1 медленнее.
   **Ключевая находка этой части сессии**: контроллер WidowX
   (`Rotation.from_rotvec`) ждёт axis-angle, а GreenVLA выдаёт Euler-углы
   (`roll,pitch,yaw`) без какой-либо конверсии — подтверждено чтением
   `PDEEPoseController` + эталонного RT1-wrapper'а в SimplerEnv (у него есть
   явная ветка `euler2axangle()` для моделей с Euler-выходом). Фикс:
   `euler2axangle()` в `greenvla_server.py::predict_chunk()`, после
   gripper-рескейла. **Подтверждено pure-upstream репро** (см. п.2) —
   доверять этому фиксу, не перепроверять заново без новой причины.
2. ~~Pure-upstream репро GreenVLA-R1 (их код + SimplerEnv's own eval,
   БЕЗ единой строчки нашего кода)~~ — **готово, финальный результат: 2/20
   = 10.0% SR** на `widowx_stack_cube`, R1-bridge, с обоими фиксами
   (gripper + rotation). Подтверждает: баг был настоящий, фикс реально
   работает, ненулевой success — воспроизводимый факт. 10% далеко от их
   заявленных 72.9%/80.5% (Entire Avg) — но это **агрегат по всем 4
   bridge-задачам** (spoon-on-towel, carrot-on-plate, **stack-cube**,
   eggplant-in-basket), не число для stacking специально; stacking
   объективно может быть заметно сложнее остальных трёх. Не путать это
   число с числами нашего собственного пайплайна (п.1) — они собираются
   отдельно и могут отличаться по чистой статистической случайности при
   таком размере выборки, это не повод для тревоги само по себе. Метод и
   находки по пути (сегфолт `sapien==2.2.2` vs numpy≥2, решён пином
   `numpy==1.26.4`; `conda create --clone` не работает на смешанных
   conda+pip env — известное ограничение conda) — в skill `slava-greenvla`.
   Репро-скрипт и его env (`greenvla-simpler-repro`) — вне репозитория, в
   scratchpad и в отдельном conda env; не привязывались к git, можно
   удалить `conda env remove -n greenvla-simpler-repro` если больше не
   нужен, либо оставить для будущих аналогичных проверок.
3. **pi0/pi0.5 SimplerEnv rerun (base/wrist camera-фикс)** — запущен на
   GPU0 после того, как SmolVLA LIBERO полностью досчитался (99/99).
   **По пути найден и исправлен ещё один настоящий баг**: `lerobot/
   pi0_base`/`pi05_base` — cross-embodiment BASE-чекпойнты, никогда не
   файнтюненные на конкретного робота; их собственный `config.json`
   реально объявляет `output_features["action"].shape == (32,)` (общий
   padded-размер, не настоящий 7-dim WidowX). Наш код брал этот 32-мерный
   вектор как есть → `AssertionError: ((32,), 7)` на каждом `/step`.
   Исправлено усечением `action[:7]` в `lerobot_server.py::predict()` —
   та же конвенция, что `GreenVLA`'s `BridgeOutputsTransform` для того же
   embodiment. **Также хит по пути**: запуск pi0+pi0.5 одновременно на
   одной GPU во время их ОБЩЕЙ фазы загрузки чекпойнта временно даёт CUDA
   OOM (пиковая память двух ~3B PaliGemma-моделей одновременно > 32GB) —
   решается запуском последовательно (дать одной полностью загрузиться,
   потом стартовать вторую), не параллельно с нуля. Детали — skill
   `slava-lerobot-policies`.
4. **pi0 на LIBERO: `no_action_or_timeout` доминирует (90/99), pi0.5 —
   нет** — новая, отдельная, необъяснённая находка (не то же самое, что
   camera-swap, который уже исправлен и подтверждён для обоих). Не
   расследовано в этой сессии. Кандидаты для следующей: сравнить
   action-head/flow-matching конфиг pi0 vs pi0.5 (см. архитектурный
   раздел в `slava-lerobot-policies` — они архитектурно НЕ идентичны,
   у pi0.5 state идёт текстом в промпт, а не отдельным эмбеддингом),
   либо прямой `curl` к живому pi0 model-server'у с реальным observation
   для инспекции сырых предсказанных action-значений.
5. **Архитектурные справки по всем 4 моделям — готово.** По просьбе
   пользователя добавлены секции "Architecture reference" в
   `slava-openvla-oft`/`slava-lerobot-policies`/`slava-greenvla` — backbone,
   action head, inference pipeline шаг за шагом, код/псевдокод, точные
   цитаты из официальных paper/репо (не выдумано). Весь прежний
   накопленный опыт (баги, находки) сохранён без изменений, секции
   добавлены сверху. Полезно перечитать перед следующим заходом на баг в
   любой из этих моделей — многие находки этой сессии (rotation-фикс,
   action-truncation-фикс) прямо предсказывались архитектурными деталями,
   которые эти секции теперь документируют явно.
6. **Ручная валидация первых 100 rollouts** (task.md, explicit
   требование) — **пользователь явно отложил до конца сборки данных**
   ("Отложить до конца сборки данных") — сборка данных практически
   закончена (см. п.1 выше), пора поднимать этот вопрос с пользователем.
7. **Перегенерировать `docs/rollout_report.html` и закоммитить/запушить**
   once все прогоны из п.1/3 закончатся. Команда:
   `python3 scripts/generate_rollout_report.py --output docs/rollout_report.html --for-pages`.
   Отчёт на момент хэндоффа НЕ перегенерирован после rotation/action-
   truncation фиксов — числа в нём устарели.
8. **Баг разметки D4/pi0-SimplerEnv-camera-fix zero-shot ambiguity
   (smolvla camera1/2/3, pi0_base/pi05_base right_wrist_0_rgb дублирование
   для бимануальных слотов)** — все известные варианты этого класса багов
   исследованы и задокументированы в `slava-lerobot-policies`, ничего не
   осталось открытым по этой линии на момент хэндоффа.
9. **v0.1 (projection 3D→2D crosshair) и pointing-зонд GreenVLA** — не
   начаты, сознательно вне scope pilot v0 (task.md относит их к следующему
   шагу). **Что это, если пользователь/агент спросит снова** (объяснялось
   в чате 05.08.2026, task.md строки ~1160-1168, ~129): v0 (то, что у нас
   есть) — RGB + sim handles + позы объектов + contacts. v0.1 добавляет
   проекцию известной 3D-позы объекта (уже есть в `steps.jsonl`'s
   `object_poses`) в 2D-точку на кадре ("crosshair") — ground-truth ответ
   на "где на картинке объект X". Зачем: у GreenVLA отдельная VLM-голова,
   которая умеет отвечать на "укажи на X" — с crosshair можно сравнить
   pointing-accuracy VLM-головы (по-русски/по-английски) с тем, что
   action-голова реально трогает первой в той же сцене (`first_contact_
   object`, уже есть в v0). Точный pointing + неверное действие = прямое,
   внутримодельное (без патчинга) доказательство H-binding-гипотезы
   (понимание есть, связка "понимание→действие" рвётся) — уникально для
   GreenVLA, у остальных 4 моделей нет pointing-головы для такого
   сравнения. v1.0 (ещё дальше) — instance segmentation/bbox/masks.
10. **`rollout_annotations.jsonl` со старого сервера** (77 эпизодов) — по
    решению пользователя НЕ переносился на эту машину, весь прогон здесь с
    нуля. Если понадобятся эти старые данные отдельно — они остались на
    предыдущей машине/в zip у пользователя.

### Живые процессы на момент хэндоффа (05.08.2026, ~20:05 UTC, финальное обновление)

**Ещё одна находка после первой версии этого раздела**: pi0.5's rerun упал
из-за ОТДЕЛЬНОГО (не action-truncation) бага — device mismatch
(`cuda:0` vs `cpu`) в токенизации языка, специфично для pi0.5 (не pi0),
т.к. pi0.5 строит текстовый промпт со state ВНУТРИ preprocessor'а. Фикс:
`preprocessor_overrides={"device_processor": {"device": ...}}` в
`lerobot_server.py::LerobotBackend.__init__` (коммит `787a6af`). Исправлено
через прямую репродукцию (`/predict_chunk` напрямую к серверу), но
**НЕ подтверждено на полном rerun'е** — pi05 перезапущен на GPU0 сразу
после фикса (порт env-worker 9701, model-server 9711), проверить его
прогресс первым делом. Детали — skill `slava-lerobot-policies`.

Снимок для возобновления — числа ниже растут в реальном времени, не
переписывать этот блок, просто прочитать как "что было запущено и где" и
перепроверить актуальные счётчики через
`python3 -c "import json; from collections import Counter; c=Counter(); [c.update([json.loads(l)['model']]) for l in open('rollouts/rollout_annotations.jsonl')]; print(c)"`
или аналогичный однострочник.

```
GPU0 (~free again): pi0 FINISHED (28/28 SimplerEnv + 99/99 LIBERO — full
                 coverage, action-truncation fix confirmed working, process
                 exited cleanly). pi05 SimplerEnv still running: env-worker
                 :9602, model-server lerobot/pi05_base :9612.
GPU1 (~11.8GB): GreenVLA-R0 rotation-fix rerun, env-worker :9301,
                 model-server (R0-base) :9311
GPU2 (~11.6GB): GreenVLA-R1-bridge rotation-fix rerun, env-worker :9302,
                 model-server (R1-bridge) :9312
GPU3 (~11.6GB): GreenVLA-R2-bridge rotation-fix rerun, env-worker :9401,
                 model-server (R2-bridge) :9411
```

Счётчики на момент записи (последнее обновление, формат success/total):
GreenVLA-R0 0/18, GreenVLA-R1 0/20, GreenVLA-R2 3/10, OpenVLA-OFT 74/99
(полное покрытие 99/99 эпизодов, 74 из них успешны), **pi0 — полное
покрытие 127/127 эпизодов, 2 успешны** (LIBERO 99/99 + SimplerEnv 28/28),
pi0.5 SimplerEnv ещё не начат (LIBERO часть 99/99 уже готова, 0 успехов).
Логи оркестраторов:
`rollouts/logs/{greenvla_r0,greenvla_r1,greenvla_r2}_rotationfix.log`,
`rollouts/logs/pi05_simplerenv_actiontrunc_fix_v2.log`.

**Если процессы всё ещё живы, когда начинается новая сессия** — просто дать
доиграть (`ps aux | grep run_rollouts.py`, `tail -f` соответствующий лог).
**Если умерли/зависли** — резюмить безопасно той же командой (без
`--num-shards`, эти конкретные reruns шли одним шардом каждый):
```
CUDA_VISIBLE_DEVICES=<N> SLAVA_SIMPLERENV_PORT=<port> SLAVA_MODEL_PORT_<KEY>=<port> \
  conda run -n slava-notebook python scripts/run_rollouts.py --models <model_key>
```
— подставить свободные порты (не пересекающиеся с ещё живыми процессами) и
нужный `model_key` (`greenvla_r0`, `greenvla_r1_bridge`, `greenvla_r2_bridge`,
`pi0`, `pi05`). `load_completed_run_ids()` продолжит с того места, где
остановились — дублирования не будет.

**Важно про pi0+pi0.5 на одной GPU**: если запускаете оба заново, дайте
ПЕРВОМУ полностью загрузиться (`nvidia-smi` покажет стабильную память,
модель-сервер начнёт отвечать 200 на `/predict_chunk`) ДО старта второго —
одновременная загрузка двух ~3B PaliGemma-моделей может временно превысить
32GB и упасть с CUDA OOM (уже случилось раз в этой сессии, решилось
последовательным запуском).

**После того как все 5 процессов выше допишут до конца** (проверить: ни
одного `run_rollouts.py` в `ps aux`) — следующий шаг это п.6-7 бэклога
выше (спросить пользователя про ручную валидацию, перегенерировать отчёт,
закоммитить).

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
  Исключение из "коммитим только по явной просьбе" — конец сессии/handoff
  (skill `slava-session-handoff`): там коммит и пуш всего нужного для
  переноса на другую машину (например, GPU-сервер) — это по умолчанию, а не
  по отдельному запросу каждый раз, потому что следующая сессия может
  начаться с чистого `git clone` без доступа к этому диалогу.
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
  что реально оценивается, пороги, направление шкалы `ambiguity` (решено:
  выше = чётче) и что для pilot v0 засчиталось как human-verified native
  check (неформальный просмотр пользователем, не построчный проход по
  дашборду) — v0-специфичное решение, не автоматический дефолт для ~200
  сцен, см. сам skill;
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
- `slava-model-rollouts` — **общая** (05.08.2026 разбита на 4 skill'а из-за
  размера) client-server архитектура первых model rollouts (env-worker/
  model-server split, почему один shared env-worker на среду, а не на
  модель), контракт `rollout_annotations.jsonl`/авторазметка, память GPU
  (одна модель резидентна за раз), как безопасно параллелить SimplerEnv,
  общие process-management уроки (`conda run` не форвардит сигналы,
  wrapper-vs-child PID). Модель-специфичные API/баги теперь в отдельных
  skill'ах ниже — читать этот файл первым для контекста, затем нужный
  из четырёх;
- `slava-openvla-oft` — OpenVLA-OFT: architecture reference (Prismatic VLM,
  SigLIP+DINOv2, parallel decoding vs vanilla autoregressive, L1-regression
  action head), confirmed real API из `moojink/openvla-oft`, 4 реальных бага
  с root cause (пропущенный gripper post-processing, chunk replay, image
  mirroring, missing settle steps) — довели SR с 0% до 74.7%;
- `slava-lerobot-policies` — pi0/pi0.5/SmolVLA (общий `lerobot_server.py`):
  architecture reference для всех трёх (flow matching, action expert,
  camera1/2/3 у SmolVLA — исследовано дважды, документирована и
  подтверждена живыми чекпойнтами арбитрарность), cuDNN-фикс, camera-swap
  баг (настоящая причина 0% на LIBERO, не gripper/orientation), base/wrist
  camera-фикс для zero-shot `*_base` чекпойнтов на SimplerEnv,
  action-truncation баг у `pi0_base`/`pi05_base` (32-dim vs реальный 7-dim);
- `slava-greenvla` — GreenVLA R0/R1/R2: architecture reference (Qwen3-VL-4B
  backbone, π0-style action expert, flow matching, R2's настоящий offline
  RL curriculum — IQL + noise-actor), gripper-range-mismatch фикс,
  **rotation representation mismatch фикс** (Euler vs axis-angle — самая
  крупная находка сессии), pure-upstream репро методология и результат
  (2/20=10% SR на stack_cube с обоими фиксами, их же код);
- `slava-session-handoff` — процесс закрытия сессии и подготовки нового
  чата (на той же или другой машине/железе): сверка "Текущего состояния
  проекта" на противоречия (не просто дописывать абзац сверху), когда
  заводить/расширять skill вместо нового, структура самодостаточного
  стартового промпта для следующего чата и как его физически передать
  агенту, которого пользователь заведёт на новой машине/в новом чате.

Кроме `slava-*`, в `.claude/skills/` также лежат 14 сторонних skills из
[obra/superpowers](https://github.com/obra/superpowers) (`brainstorming`,
`writing-plans`, `executing-plans`, `test-driven-development`,
`systematic-debugging`, `verification-before-completion`,
`subagent-driven-development`, `dispatching-parallel-agents`,
`requesting-code-review`/`receiving-code-review`, `using-git-worktrees`,
`finishing-a-development-branch`, `using-superpowers`, `writing-skills`) —
общая методология разработки (TDD, поиск root cause, план перед кодом,
верификация перед заявлением "готово"), не специфичная для SLAVA. Скопированы
руками (не через `claude plugin install`), чтобы уехать вместе с `git clone`
на другую машину — источник, версия, коммит и лицензия (MIT) записаны в
`.claude/skills/THIRD_PARTY_NOTICES.md`. Это вендоренный снепшот: не
редактировать их как `slava-*` (новые находки/поправки — в апстрим или в
отдельный `slava-*`-skill, если это специфично для проекта), обновлять через
переустановку/повторное копирование, не ручным патчем.

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
