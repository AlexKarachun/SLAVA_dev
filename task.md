### *Cross-Lingual Action-Binding Collapse in VLA Models*

**SLAVA?** *Slot-Level Attribution for VLA*

## Идея:

Роботы на VLA-моделях резко хуже выполняют команды не на английском — и показываем, что дело не в незнании русского. Наша гипотеза: при дообучении VLM в робополитику модель сохраняет понимание неанглийской инструкции - его можно декодировать из внутренних состояний, - но **теряет каузальную связь между этим пониманием и генерацией действия**. 

### Что делаем?

Мы строим контролируемый русскоязычный стресс-набор (это минимальные лингвистические пары, примерно штук 1500), раскладываем отказы по уровням (парсинг → выбор объекта → пространственное отношение → action binding), доказываем механизм каузальным патчингом между базовым VLM-бэкбоуном и его робовариантом (Qwen3-VL ↔ GreenVLA) и предлагаем, как это фиксить. 

#### Сразу по срокам

Есть несколько возможных ориентиров: 

- жесткий - в сентябре (**ICLR 2027**)
- реалистичный - в январе (**RSS 2027, ICML 2027, ACL 2027**)
- вальяжный - весна 2027 (**CoRL 2027, NeurIPS 2027**)

| Venue | Почему подходит | Дедлайн |
| --- | --- | --- |
| **ICLR 2027** | ок, если много mechinterp’а | 15-19 Sep 2026, full ~27 Sep |
| **ICML 2027** | A*-ML, не роботикс, mechanism + targeted training recipe | Тоже пока нет инфы, ориентиры - январь 2027 |
| **NeurIPS 2027** | Опять общая конфа | ориентир: начало мая 2027 |
| **ACL 2027** | Тогда упаковываем как multilingual NLP/VLM paper | январь 2027 |
| **CoRL 2027** | А это уже роботикс - упор нужен на VLA | ориентир: конец мая / начало июня 2027 |
| **RSS 2027** | Самый престижный robotics  | ориентир: конец января 2027 |

### Related work

**Для Introduction - обоснование мотивации:**

Деградация на неанглийском - это системное явление на всех уровнях стека (LLM - VLM - VLN - VLA)

1. **✅ Уровень VLA:** Dong et al. - падение SR 30–50% на 10 языках и Chen et al. - ru/zh/fr/ar + code-switch, зависимость от action head. Это единственные прямые VLA-свидетельства, феномен подтверждён дважды независимо.
2. **✅ Уровень VLN:** *Cross-Lingual Vision-Language Navigation* - это двуязычный Room-to-Room (BL-R2R), zero-shot падение на китайском. 
3. **Уровень VLM:**
- *Multilingual Multimodal Pre-training for Zero-Shot Cross-Lingual Transfer* - значительный разрыв EN vs non-EN в text-video/image retrieval при zero-shot переносе.
- xGQA и *Improving the Cross-Lingual Generalisation in VQA* - деградация мультиязычного VQA, особенно на языках, далёких от английского, атрибуция к misalignment текстовых эмбеддингов
- CLAIM - multilingual object hallucination, LVLM чаще галлюцинируют на неанглийских запросах, а лечат training-free вмешательством в cross-lingual attention heads - может быть полезно для обоснования наших интервенций
- Обзор *Multilingual Vision-Language Models: A Survey* - явно там тоже что-то есть про это
1. **Уровень LLM - механизм English-pivot**
- *Do Llamas Work in English? On the Latent Language of Multilingual Transformers* - logit lens показывает: в средних слоях мультиязычные LLM думают через представления, смещённые к английскому
- *How do Large Language Models Handle Multilingualism?* (NeurIPS 2024) - послойная картина: понимание в перевод в общее пространство в генерацию; language-specific нейроны.

> Наши layerwise LNS-пробы и logit-lens эксперименты это прямой перенос этой методологии на VLA - поэтому изучаем-с.
> 
1. Поверхностная вариативность тоже ломает: LIBERO-plus - VLA с >90% SR коллапсируют под систематическими пертурбациями; *Flatness Preserves Instruction Following* instruction blindness от файнтюнинга на фиксированных строках. Это обоснование для почему обязателен EN-paraphrase контроль и метрика Δlang - без них языковой эффект неотличим от общей хрупкости к незнакомым строкам.
2. Контекст instruction blindness: LangGap, BayesianVLA, Stable Language Guidance. Политики игнорируют язык - наша кросс-язычная ось показывает, что blindness неравномерна по языкам.

**Похожее по идее:**

1) ✅ Dong et al., 2026 - *When Does Language Matter? Multilingual Instructions Reveal Step-wise Language Sensitivity in VLA Models*

Они переводят LIBERO на 10 языков, показывают падение SR на 30–50% на неанглийских инструкциях и находят, что чувствительность к языку концентрируется в отдельных шагах роллаута, затем предлагают step-wise inference-time alignment скрытых состояний к английским референсам.
Как именно они определяют language-critical steps? можно ли переиспользовать как метрику? Их intervention - какие требования на инференсе (нужен ли EN-роллаут той же сцены)? На каких моделях - есть ли Qwen-based? 

2) ✅ Chen et al., 2026 - *Beyond English: Uncovering the Multilingual Gap in Vision-Language-Action Models*

MT-перевод инструкций + code-switching, LIBERO+SimplerEnv, сравнение action heads (FAST-style деградирует сильнее, чем flow/diffusion), метод MPCA - training-time выравнивание проекций мультиязычных эмбеддингов к английским.
Их точные числа на русском? Как устроен их code-switching - сколько слов подменяют и чем? Детали MPCA: какие слои, какой корпус - сможем ли построить MPCA-proxy бейзлайн? Что именно они говорят про action heads и на каком бэкбоне?

3) ✅ *Unmasking the Illusion of Embodied Reasoning in VLA Models*, 2026

Они делают контрфактические layouts (рекомбинация spatial/semantic инструкций), вскрывают shortcut-обучение: lexical-kinematic shortcut - токен red напрямую запускает motion primitive без визуального grounding'а. Всё на английском.
Их дизайн контрфактических пар - мы можем что-то скопировать? Какая у них таксономия failure modes? Меряют ли что-то похожее на Action Sensitivity Score?

*4) RoboSemanticBench*, 2026

Они диагностируют, используется ли semantic competence в action prediction после VLA пост-тренинга и показывают разрыв между компетентностью бэкбона и действием. Но это один язык.

Как операционализируют “семантика не используется действием” - корреляционно или каузально? А можно ли адаптировать их пробы под наши slot probes? Не закрывают ли они частично нашу pointing-vs-action диссоциацию?

5) ProGAL-VLA / Point-VLA / PEEK 

Это всё про системы явного grounding-баттлнека: символьные подцели с верификацией заземления (ProGAL), визуальные подсказки-указатели к инструкции (Point-VLA), VLM-предсказанные точки как языко-независимый интерфейс политики (PEEK).

Их grounding-oracle механики - что переиспользовать в нашей oracle-лестнице (bbox/crosshair-подсказки)? Числа ProGAL про 41% grounding failures у OpenVLA можно процитировать нам.

6) Actions-as-Language / Grover / InstructVLA

Что делают: борьба с забыванием VLM-способностей при action-tuning: представление действий текстом против catastrophic forgetting; сохранение претрейн-представлений; разведение рассуждения и действия.

А меряет ли кто-то из них хоть что-то мультиязычное? Их метрики retention - надо ли нам  брать как secondary-метрики нашего аудита?

7) ✅ Надо прочитать и нашу *Does VLA Even Know the Basics? Measuring Commonsense and World Knowledge Retention in VLA Models* 

## Наш главный тезис

> Action fine-tuning does not merely reduce multilingual VLA performance. It can decouple multilingual semantic slots from action prediction. We show this with controlled Russian minimal pairs, slot-level oracle attribution, and causal patching between base-VLM and action-tuned VLA checkpoints.
> 

Всё, что не доказывает этот клейм, то appendix :)

### Три возможных объяснения

| Гипотеза | Смысл | Диагностический признак |
| --- | --- | --- |
| H-understanding | VLA не извлекает смысл RU-инструкции | slot probes не декодируются из VLA (но декодируются из base) |
| H-grounding | смысл есть, но не привязан к объекту/отношению в сцене | probes ок; visual-grounding oracle восстанавливает большую часть |
| H-binding (головная) | семантика есть и заземлена, но action head её не читает | probes ок; oracles слабо помогают; slot-swap patching работает на EN, не на RU |

## Наши research questions

- RQ1. Which linguistic perturbations cause VLA failures *beyond generic instruction-string OOD*?

Метод: EN-paraphrase/reordered контроли, основная метрика Δlang = gap(RU-ось) − gap(EN-paraphrase).

- RQ2. Where do multilingual instructions fail in the language-to-action pipeline?

Метод: slot-level атрибуция + oracle-лестница.

- RQ3. Does action fine-tuning erase multilingual semantics or render them non-causal for action prediction?

Метод: base в VLA layerwise probes + каузальный patching. *(Подвопрос: почему дискретные action heads усиливают collapse — механистическое объяснение эмпирики есть у Chen)*

- RQ4. Can a slot-causal, base-anchored repair restore multilingual action binding without sacrificing English control?

Метод: один основной repair vs translation / Dong-style shift / MPCA-proxy

- RQ5. Can we just translate russian instructions into english?

### Наш сore

1. **SLAVA** - контролируемые минимальные пары, наш бенч
2. **Slot-level атрибуция**: first-contact, forbidden-touch, spatial predicates, conditional execution, action divergence от EN-роллаута
3. **Oracle recovery curves** (translation → slot → visual grounding → relation → action primitive)
4. **Pointing-vs-action диссоциация на GreenVLA.** Например, **** VLM-голова модели отвечает на укажи на красную кружку по-русски, а мы сравниваем точность pointing'а с тем, что экшен голова реально трогает первой на той же сцене. Внутримодельное, беспатчинговое доказательство H-binding, уникально для GreenVLA (наследие их стадии L1?)
5. **Base→VLA пробинг**: layerwise slot probes, cross-lingual probe transfer (train EN → test RU), Language-Neutrality Score по слоям; четыре публичные стадии curriculum'а Qwen3-VL base → Qwen3-VL-action → GreenVLA-R0 → R1-bridge → R2-bridge
6. **Каузальный patching**: layer-level EN→RU; slot-swap (перекл. target-слота меняет действие на EN, но не на RU?); action-head-input patching. Attention-head-гранулярность
7. **Один repair**: Repair 1a/1b на общей каузальной маске

### Возможно еще:

Полный action-head retraining study - это 3 головы на одном бэкбоне, Action-Binding Preservation loss и selective-freezing рецепт, еще языки, long-horizon анафора — exploratory-ось, полные attention-ablations, open-loop анализ реальных демо GreenVLA

## Бенч

#### Сначала затравка

- 60–80 задач (LIBERO Spatial/Object/Goal + 8-12 bridge-задач SimplerEnv для GreenVLA)
- 6 primary-вариантов: en_canonical, en_paraphrase, ru_literal, ru_case_swap, ru_negation, code_switch
- 25 роллаутов/вариант, 2–3 модели; парный дизайн (одна сцена/сид, разные инструкции), бутстрап-CI, McNemar
- Если пилот покажет, что ru_colloquial устойчив к translation-oracle (перевод не лечит), это усиливает repair-нарратив.

### Потом полный набор

- 120–180 задач × 12–13 вариантов (все оси: + free_order, colloquial, anaphora, translit, mt_russian, + zh-подмножество)
- меньше роллаутов / open-loop / oracle-only прогоны
- фреймы, инструкции, авторазметчик, evaluation harness - готовый инструмент для тестирования моделей на русском

## Модели и среды

| Base | Action-tuned | Closed-loop среда |
| --- | --- | --- |
| Qwen/Qwen3-VL-4B-Instruct | GreenVLA (R0-base + R1-bridge) | SimplerEnv/bridge |
| Prismatic | OpenVLA-OFT | LIBERO |
| PaliGemma → π0/π0.5 (lerobot), SmolVLA |  |  |

План B (LoRA-адаптация GreenVLA на LIBERO для симметрии таблиц) — optional. В Limitations честно: модельная сетка × среды несимметрична.

## Repair

По результатам фазы 4 строится маска M компонентов, где (а) EN/RU-выравнивание разрушено, (б) patching каузально влияет на действие, (в) EN-перформанс слабо чувствителен.

- **Repair 1a - base-anchored causal restoration:** θ_repaired = θ_vla + α·M·(θ_base − θ_vla). Data-free; риск: дрейф базисов → Procrustes-выравнивание, α-свип, жёсткое ограничение EN-retention.
- **Repair 1b - lightweight slot-to-action adapter (страховка):** маленький low-rank адаптер на action-readout, выравнивающий RU-слот-представления с action-каузальным EN-подпространством; учится на минимальных парах нашего бенча.

**Бейзлайны:** direct RU / translate-to-EN (+latency) / EN-keyword anchoring / Dong-style step-wise shift / MPCA-proxy. 

## Когда мы готовы?

1. нетривиальный Δlang после EN-paraphrase контролей 
2. slot/oracle-доказательство, что отказы не сводятся к переводу
3. base→VLA layerwise collapse или диссоциация декодируемо, но не каузально
4. каузальный patching, меняющий target/действие хотя бы для одного слота
5. repair, улучшающий RU/code-switch при EN-retention ~ 100%.

## Пути

**Gate 1:** Δlang > 0 хотя бы на одной модели; перевод не закрывает всё; профили провалов различаются по осям. *Разворот, если GreenVLA держит русский:* «Why does a multilingual-backbone VLA survive? Anatomy of preserved cross-lingual grounding» 

**Gate 2:** разные оси → разные bottleneck'и. *Если всё лечится переводом:* нарратив multilingual VLA failure is (mostly) lexical + механистика забывания

**Gate 3:** слоты декодируемы, но не каузальны → **головной нарратив H-binding** (максимум); слоты не декодируемы → H-understanding: action tuning стирает мультиязычную семантику - тоже новая ось забывания; всё каузально, ломается сценное заземление → H-grounding, упор на oracle/pointing-результаты.

**Gate 4:** 1a или 1b бьёт перевод на CS при EN-retention → мы красавчики; слабый repair → мы не особо красавчики, но публикуемся.

### План работы

**06.07.2026**

#### Задачи

1. убедиться, что мы правильно понимаем шесть ближайших конкурентов и наша отстройка от них честная
2. собрать доказательную базу, что модели деградируют на неанглийском для Introduction/Related Work
3. артефакт - заполненная таблица related work + короткие конспекты, которые лягут в статью

#### Протокол

1. **Задача** - что за вопрос решают (одним предложением).
2. **Метод/данные** - модели, среды, языки, как построены инструкции (машинный перевод? вручную?)
3. **Метрики** - что именно меряют (success rate? что-то тоньше?).
4. **Главные находки** - 3–5 пунктов с числами.
5. **Ограничения** - что они сами признают + что видим мы.
6. **Что берём** - методы/метрики/бейзлайны, которые мы переиспользуем или с которыми сравниваемся.
7. **Чем отличаемся** - проверить и при необходимости уточнить формулировку из карты ниже. Если наша формулировка отстройки неточна — это важнейшая находка, немедленно сообщить.
8. **Риск пересечения** - что они могут сделать в follow-up, который нас обгонит. Это не шутка - тут вопрос скорости.

#### Формат сдачи

**Формат сдачи:** таблица (Notion/Google Sheets), можно использовать данный шаблон или модифицировать его/создать новый.

## 21.07.2026

> Следующая задача - собрать v0 бенчмарк. Это environment-first benchmark: сначала LIBERO/SimplerEnv scene + init state + RGB renders + реальные sim objects, и только потом русские инструкции.
> 

За первую неделю нужно собрать `task_inventory.jsonl` на 100 candidate-сцен, screenshot sheet и `object_lexicon.csv`. 

После этого мы выбираем 20 задач: 16 LIBERO + 4 SimplerEnv-bridge. 

Для выбранных задач размечаем grounded semantic frames: target, reference, relation, forbidden, success predicates, а затем пишем Tier-1 variants: `en_canonical`, `en_paraphrase`, `mt_russian`, `ru_literal`, `ru_free_order`, `ru_case_swap`, `ru_negation`, `code_switch`. 

Все варианты проходят валидатор и native check. 

Цель v0 - чистая разметка, чтобы через неделю/две запустить первые VLA-прогоны и получить таблицы SR / wrong-object / relation / negation / Δlang.

## Сбор SLAVA

SLAVA - это **grounded simulation benchmark**: каждая инструкция должна быть привязана к реальной сцене симулятора, реальным объектам, реальным изображениям, sim handles, слотам и проверяемым success/failure predicates.

Главный порядок работы такой:

```
LIBERO / SimplerEnv task + init state
-> RGB renders: agentview + wrist
-> реальные объекты сцены: sim handles, позы, видимость
-> object inventory + RU lexicon
-> отбор пригодных сцен
-> grounded semantic frame: slots, roles, predicates
-> EN/RU/code-switch minimal pairs
-> schema validator
-> native check
-> freeze v0
-> первые прогоны
```

# Scope пилота v0

Пилот v0 состоит из **20 задач**:

```
16 задач LIBERO
4 задачи SimplerEnv-bridge
```

- **LIBERO** - основная разметка. Там есть BDDL-сцены, fixed init states, OffScreenRenderEnv, доступ к позам/контактам/success predicates.
- **SimplerEnv-bridge** - маленький bridge-трек для GreenVLA / pointing probe.
- Расширение SimplerEnv и custom BDDL-сцены - это для v1.0, не сейчас.

Картинки обязательны: для каждой задачи × init state нужно сохранить `agentview_rgb.png` и `wrist_rgb.png`. Отдельного датасета фотографий нет; вход модели - это рендеры симулятора. Задача без сохранённых картинок в SLAVA не попадает.

**Не начинаем с написания русских инструкций.** Сначала нужно пройти по средам и собрать inventory:

```
task_uid
canonical_en
bddl_file / env metadata
init_state_id
agentview image
wrist image
objects_raw
sim handles
object poses
visibility
candidate target/reference/distractors
```

Только после отбора сцен мы пишем русские варианты.

# Deliverables до авторинга языка

## D1 - `task_inventory.jsonl`

Цель: ≥ **100 candidate-сцен**.

Одна строка = одна сцена:

```
task × init_state
```

Формат:

```json
upd
{
  "task_uid": "libero_spatial_003_seed000",
  "suite": "libero_spatial",
  "task_id": 3,
  "canonical_en": "put the cream cheese in the bowl",
  "source": {
    "environment": "LIBERO",
    "commit": "8f1084e3132a39270c3a13ebe37270a43ece2a01",
    "task_name": "put_the_cream_cheese_in_the_bowl",
    "bddl_file": "libero/libero/bddl_files/libero_spatial/example.bddl",
    "init_state_id": 0
  },
  "images": {
    "agentview_rgb": "images/libero_spatial_003_seed000_agentview.png",
    "wrist_rgb": "images/libero_spatial_003_seed000_wrist.png"
  },
  "objects_raw": [
    {
      "sim_handle": "...",
      "raw_name": "...",
      "pose_xyz": [0.0, 0.0, 0.0],
      "visible_agentview": true,
      "visible_wrist": "visible_partial"
    }
  ],
  "success_predicates": [],
  "candidate_slots": {
    "action": null,
    "target": null,
    "reference": null,
    "relation": null,
    "forbidden_candidates": []
  },
  "usable_for_slava": null,
  "notes": ""
}

old:
{
  "task_uid": "libero_spatial_003_seed000",
  "suite": "libero_spatial",
  "task_id": 3,
  "init_state_id": 0,
  "canonical_en": "put the cream cheese in the bowl",
  "bddl_file": "...",
  "images": {
    "agentview_rgb": "images/libero_spatial_003_seed000_agentview.png",
    "wrist_rgb": "images/libero_spatial_003_seed000_wrist.png"
  },
  "objects_raw": [
    {
      "sim_handle": "...",
      "raw_name": "...",
      "pose_xyz": [0.0, 0.0, 0.0],
      "visible_agentview": true,
      "visible_wrist": false
    }
  ],
  "candidate_slots": {
    "action": null,
    "target": null,
    "reference": null,
    "relation": null,
    "forbidden_candidates": []
  },
  "usable_for_slava": null,
  "notes": ""
}
```

Плюс нужен **screenshot sheet**: HTML или PDF-простыня по всем кандидатам:

```
картинка agentview
картинка wrist
canonical_en
список objects_raw
видимые объекты
notes
```

Видимость объекта проверять глазами по рендеру, а не только по автоматическому флагу. В исходной инструкции это прямо выделено как обязательный шаг перед выбором D3.

## D2 - `object_lexicon.csv`

До написания инструкций нужно зафиксировать, как реальные ассеты называются по-английски и по-русски.

Формат csv:

```json
raw_name,category_en,category_ru,color_en,color_ru,allowed_synonyms_ru,usable_v0,notes
red_mug,mug,кружка,red,красная,"чашка",yes,
blue_bowl,bowl,миска,blue,синяя,"чаша",yes,
green_sponge,sponge,губка,green,зелёная,"",yes,
cream_cheese,cream cheese,сливочный сыр,white,белый,"сыр",no,визуально неочевиден; оставить для hard lexical v1.0
alphabet_soup,soup can,банка супа,"no",неестественно по-русски
```

Правило:

```
Если объект нельзя естественно и однозначно назвать по-русски
ИЛИ его трудно опознать на рендере,
то usable_v0 = no.
```

Для v0 предпочтительны:

```
кружка / чашка
миска
тарелка
губка
кубик / блок
ящик
корзина
поднос
плита
раковина / мойка
```

Не надо выкидывать странные объекты навсегда. Они могут стать hard-lexical axis в v1.0/appendix.

## D3 - `selected_tasks_v0.jsonl`

После D1 и D2 мы вместе выбираем **20 задач**:

```
16 LIBERO
4 SimplerEnv-bridge
```

Выбор делается по screenshot sheet. Только после утверждения `selected_tasks_v0.jsonl` начинается авторинг русских вариантов. Это важно: D3 в плане явно стоит до написания русских осей.

# Критерии отбора сцен

## Хорошая сцена

Сцена подходит для v0, если:

```
1. Объекты видны в agentview.
2. Объекты естественно называются по-русски.
3. Есть чёткий target.
4. Для relation task есть чёткий reference.
5. Есть проверяемый success predicate.
6. Желательно есть distractor.
7. Можно написать естественные RU / code-switch variants.
8. Объекты не летают и не в текстурах
```

Пример хорошей сцены:

```
objects:
  red mug
  blue bowl
  blue mug

canonical:
  place the red mug to the right of the blue bowl
```

Почему хорошо:

```
target = red mug
reference = blue bowl
distractor = blue mug
relation = right_of
ru_negation ложится естественно:
  "не синюю кружку, а красную..."
case/role stress ложится естественно
wrong-object grounding измерим
```

---

## Плохая сцена

```
canonical:
  put the alphabet soup in the basket
```

Почему плохо для v0:

```
объект лексически странный;
по-русски звучит неестественно;
визуально неочевиден;
нет хорошего distractor;
нет relation;
case_swap невозможен.
```

Такие сцены не брать в v0.

## Нормальная частичная сцена

```
canonical:
  pick up the green sponge

scene:
  green sponge
  yellow sponge
```

Хорошо для:

```
ru_literal
ru_negation
code_switch
attribute binding
wrong-object grounding
```

Плохо для:

```
relation binding
case_swap target/reference
```

Это нормально. Не каждая задача должна покрывать все оси. Если ось неприменима, пишем:

```json
"axis_na": {
  "ru_case_swap": "not naturally applicable: no reversible target-reference relation"
}
```

В исходном плане это тоже зафиксировано: некоторые задачи покрывают только часть осей, а валидатор должен разрешать `axis_na` с причиной.

# Квоты v0 - они ориентировочные

Для 20 задач:

| Тип задачи | Количество |
| --- | --- |
| Spatial relation: left/right/on/next_to | 8 |
| Pick / object selection среди distractors | 5 |
| Container: put X in drawer/bowl/basket/sink | 4 |
| Surface: put X on plate/tray/table | 3 |

По distractors:

| Требование | Минимум |
| --- | --- |
| Задач с distractor | 10 / 20 |
| Same-category distractor | 5 / 20 |
| Same-color distractor | 5 / 20 |

По языковым осям:

| Требование | Минимум |
| --- | --- |
| Задач, где реализуем `ru_case_swap` / role-stress | 6 / 20 |
| Задач, где реализуем `ru_negation` | 12 / 20 |

# Схема фрейма v0.2

Одна строка в `frames_v0.jsonl` = одна selected task + init state.

Обязательные поля:

```
task_uid
suite
task_id
init_state_id
frame_version
canonical_en
bddl_file / env metadata
images.agentview_rgb
images.wrist_rgb
scene.objects
slots
variants
validation
token_len
```

`bbox2d_*`, `mask_id_*`, segmentation/depth - nullable в v0.

Почему bbox не обязателен: первые поведенческие метрики считаются из sim-состояния - поз, контактов и предикатов. Картинка нужна модели, sim_handle нужен авторазметчику, а маски нужны только для позднего visual oracle.

Шаблон:

```yaml
task_uid: libero_spatial_003_seed000
suite: libero_spatial
task_id: 3
init_state_id: 0
frame_version: "0.2"
canonical_en: "place the red mug to the right of the blue bowl"
bddl_file: "..."

images:
  agentview_rgb: images/libero_spatial_003_seed000_agentview.png
  wrist_rgb: images/libero_spatial_003_seed000_wrist.png
  agentview_segmentation: null
  wrist_segmentation: null
  depth: null

scene:
  objects:
    - id: mug_red_1
      sim_handle: red_mug
      raw_name: red_mug
      category_en: mug
      category_ru: кружка
      color_en: red
      color_ru: красная
      pose_xyz_initial: [0.12, -0.31, 0.84]
      visible_agentview: true
      visible_wrist: true
      bbox2d_agentview: null
      mask_id_agentview: null
      role: target

    - id: bowl_blue_1
      sim_handle: blue_bowl
      raw_name: blue_bowl
      category_en: bowl
      category_ru: миска
      color_en: blue
      color_ru: синяя
      pose_xyz_initial: [0.18, -0.12, 0.84]
      visible_agentview: true
      visible_wrist: true
      bbox2d_agentview: null
      mask_id_agentview: null
      role: reference

    - id: mug_blue_1
      sim_handle: blue_mug
      raw_name: blue_mug
      category_en: mug
      category_ru: кружка
      color_en: blue
      color_ru: синяя
      pose_xyz_initial: [0.05, -0.20, 0.84]
      visible_agentview: true
      visible_wrist: true
      bbox2d_agentview: null
      mask_id_agentview: null
      role: distractor

slots:
  action: place
  target: mug_red_1
  reference: bowl_blue_1
  relation: right_of
  forbidden: [mug_blue_1]
  success_predicates:
    - type: spatial_relation
      relation: right_of
      arg1: mug_red_1
      arg2: bowl_blue_1

variants:
  en_canonical: "place the red mug to the right of the blue bowl"
  en_paraphrase: "put the red mug so that it ends up on the right side of the blue bowl"
  mt_russian: null
  ru_literal: null
  ru_free_order: null
  ru_case_swap: null
  ru_negation: null
  code_switch: null
  ru_translit: null
  ru_colloquial: null
  ru_anaphora: null

axis_na: {}

validation:
  author: "student_name"
  native_check: pending
  naturalness: {}
  equivalence: {}
  notes: ""

token_len: {}
```

# Instruction variants для v0

Для пилота v0 обязательные Tier-1 variants:

```
en_canonical
en_paraphrase
mt_russian
ru_literal
ru_free_order
ru_case_swap или axis_na
ru_negation или axis_na
code_switch
```

Желательные, если быстро пойдёт:

```
ru_translit
ru_colloquial
```

Exploratory, не main claim:

```
ru_anaphora
```

# Правила авторинга вариантов

Общее правило:

```
Один вариант = один лингвистический механизм.
Слоты должны сохраняться.
Нельзя добавлять подсказки, которых нет в canonical task.
Нельзя менять target/reference/relation, если это не специально размеченная contrast pair.
```

## `en_paraphrase`

Нужен для контроля это просто OOD instruction string

Пример:

```
en_canonical:
place the red mug to the right of the blue bowl

en_paraphrase:
put the red mug so that it ends up on the right side of the blue bowl
```

Важно: сохраняем content words:

```
red
mug
right
blue
bowl
```

`en_paraphrase` критичен, потому что основной очищенный языковой эффект считается как:

```
Δlang = gap(RU-axis) - gap(en_paraphrase)
```

Без этого ревьюер скажет: модель падает не на русском, а на любой непривычной формулировке. Этот контроль в основном дизайне выделен как ключевая защита от OOD-конфаунда.

## `mt_russian`

Сырой машинный перевод `en_canonical`.

Правило:

```
Не редактировать.
Не улучшать.
Не нормализовать.
```

Храним также систему перевода:

```json
"mt_metadata": {
  "system": "Google Translate",
  "date": "2026-07-16"
}
```

## `ru_literal`

Естественная русская инструкция.

Пример:

```
поставь красную кружку справа от синей миски
```

Правила:

```
использовать object_lexicon;
названия объектов консистентны;
не литературничать;
не добавлять лишние шаги.
```

Плохо:

```
осуществи перемещение красной кружки в правую область относительно синей миски
```

Хорошо:

```
поставь красную кружку справа от синей миски
```

## `ru_free_order`

Естественный русский порядок слов, отличный от literal.

Пример:

```
справа от синей миски поставь красную кружку
```

Правила:

```
должно звучать естественно
не делать “Yoda-Russian”
слоты не меняются
```

Плохо:

```
кружку красную справа миски синей поставь
```

## `ru_case_swap` / role-stress

Это ключевая русская ось. Она проверяет связывание ролей через морфологию.

Хороший пример:

```
чашку поставь на тарелку
тарелку поставь на чашку
```

Или:

```
красную кружку поставь рядом с синей миской
синюю миску поставь рядом с красной кружкой
```

Правила:

```
нужна физическая обратимость
target/reference должны быть реально разными объектами
если честный swap невозможен - axis_na с причиной
не писать кривой вариант ради заполнения поля
```

## `ru_negation`

Нужен реально существующий forbidden object.

Пример:

```
не синюю кружку, а красную поставь справа от синей миски
```

Правила:

```
forbidden object должен быть в scene.objects;
forbidden object должен быть перепутываемым;
target не должен попадать в forbidden;
метрика потом: forbidden_object_touch.
```

Плохо:

```
не ошибись и возьми красную кружку
```

Это не создаёт measurable negation failure.

## `code_switch`

Используем русский синтаксис + английские noun phrases.

Пример:

```
поставь red mug справа от blue bowl
```

Правила:

```
глагол чаще русский
EN noun phrases не склоняем
object names должны совпадать с EN lexicon
не превращать в случайную кашу
```

## `ru_translit`

Одна схема транслитерации на весь benchmark.

Пример:

```
postav krasnuyu kruzhku sprava ot siney miski
```

Зачем: отделить эффект кириллицы/токенизации от эффекта русского языка.

## `ru_colloquial`

Разговорная, но разрешимая референция.

Пример:

```
поставь красную штуку справа от синей миски
```

Правила:

```
должен существовать только один разумный referent
если штука может означать несколько объектов — не использовать
лучше оставить для v0.1/v1.0, если есть сомнения
```

## `ru_anaphora`

Только внутри одной инструкции, без диалоговой памяти.

Пример:

```
возьми красную кружку и поставь её справа от синей миски
```

Это exploratory axis. Не строим на ней main claim, потому что VLA часто single-turn.

# QA pipeline

Порядок:

```
LLM draft
-> ручная доводка 
-> validate_frames.py
-> native check
-> freeze slava-pilot-v0
-> первые прогоны
-> правки
-> slava-tier1-v1.0
```

Валидатор должен проверять:

```
1. Все обязательные файлы картинок существуют.
2. Все sim_handle существуют в живой среде.
3. Все object ids уникальны.
4. target есть в scene.objects.
5. reference есть в scene.objects, если relation != none.
6. forbidden ids есть в scene.objects.
7. target не входит в forbidden.
8. action из допустимого реестра.
9. relation из допустимого реестра.
10. success_predicates не пустые.
11. ru_negation не заполнен, если forbidden пустой.
12. ru_case_swap либо заполнен парно, либо есть axis_na.
13. Все variants используют ключи из реестра.
14. Есть token_len для нужных токенизаторов.
15. Есть native_check status.
16. Для каждого axis_na есть reason.
```

QA-конвейер в исходном плане включает именно schema validation, проверку sim_handle против среды, наличие картинок, `axis_na`, token length, native check и freeze-теги.

# Native check

Для каждого RU-варианта нужно проверить:

```
naturalness: 1–5
equivalence: 1–5
ambiguity: 1–5
```

Порог:

```
naturalness >= 4
equivalence >= 4
ambiguity >= 4
```

Если ниже - переписать или поставить `axis_na`.

В `validation_report.md` записать:

```
сколько задач проверено
сколько вариантов переписано
средний naturalness
средний equivalence
средний ambiguity
типичные ошибки
примеры исправлений
```

Финальный набор должен быть human-verified; LLM можно использовать только для черновиков. Это важно для отстройки от translationese-подхода

# Visual oracle: не блокирует v0

Для v0 не нужны bbox/masks.

| Версия | Что есть | Зачем |
| --- | --- | --- |
| v0 | RGB + sim handles + poses + contacts | behavioral и slot-level metrics |
| v0.1 | projection 3D object center → 2D crosshair | visual-grounding oracle и pointing-зонд GreenVLA |
| v1.0 | instance segmentation / bbox / masks | strict visual oracle и красивые figures |

# Auto-labeling для первых прогонов

Параллельно с benchmark нужно готовить rollout logger.

На каждом шаге логировать:

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

Из этого автоматически считать:

```
first_contact_object
wrong_object_rate
forbidden_object_touch
final_spatial_predicate
relation_success
conditional_execution_success
action_divergence_to_en
```

Это ядро Phase 2: first-contact даёт target/wrong-object metrics, forbidden touch - negation violation, final predicate - relation success, conditional execution отделяет grounding failure от физического failure.

Формат `rollout_annotations.jsonl`:

```json
{
  "run_id": "openvla_libero_spatial_003_ru_literal_seed000",
  "model": "OpenVLA-OFT",
  "task_uid": "libero_spatial_003_seed000",
  "variant": "ru_literal",
  "instruction": "поставь красную кружку справа от синей миски",
  "seed": 0,
  "success": false,
  "first_contact_object": "mug_blue_1",
  "target_object": "mug_red_1",
  "reference_object": "bowl_blue_1",
  "wrong_object": true,
  "forbidden_object_touched": false,
  "final_relation_success": false,
  "conditional_execution_success": null,
  "failure_type_auto": "target_grounding_error",
  "notes": ""
}
```

Ручная валидация: проверить первые **100 rollouts** и оценить точность auto-labeler.

# Failure labels

Использовать только фиксированный набор:

```
success
target_grounding_error
reference_grounding_error
relation_binding_error
negation_error
physical_execution_error
no_action_or_timeout
unclear
```

Правила:

```
target_grounding_error:
  робот первым тронул не target.

reference_grounding_error:
  target выбран правильно, но relation строится относительно неправильного reference.

relation_binding_error:
  target и reference правильные, но left/right/on/in/near выполнено неверно.

negation_error:
  робот тронул forbidden object.

physical_execution_error:
  target выбран правильно, intent правильный, но физически не получилось: уронил, не схватил, не дотащил.

no_action_or_timeout:
  нет осмысленного действия.

unclear:
  невозможно уверенно определить.
```

Не использовать свободные метки:

```
"bad Russian"
"model confused"
"weird"
"failed"
```

# Первые deliverables:

```
D1 task_inventory.jsonl: ≥100 candidate scenes
D1 screenshot sheet
D2 object_lexicon.csv v0
проба camera_segmentations: максимум 0.5 дня
```

```
20 selected frames
все Tier-1 variants
validate_frames.py green
native-check passed
tag: slava-pilot-v0
export prompts для первых прогонов
```

## После делаем:

```
первые прогоны
rollout logger
rollout_annotations.jsonl
первая таблица SR по variants
первая таблица wrong-object / forbidden-touch / relation-success
v0.1: projection 3D centers -> 2D crosshair
pointing-зонд GreenVLA, если возможно
```

## Table - behavioral pilot

| Variant | SR | First-contact target acc | Wrong-object rate | Relation success | Forbidden touch |
| --- | --- | --- | --- | --- | --- |
| en_canonical |  |  |  |  |  |
| en_paraphrase |  |  |  |  |  |
| mt_russian |  |  |  |  |  |
| ru_literal |  |  |  |  |  |
| ru_free_order |  |  |  |  |  |
| ru_case_swap |  |  |  |  |  |
| ru_negation |  |  |  |  |  |
| code_switch |  |  |  |  |  |

---

## Table - cleaned language effect

| Effect | Formula | Value |
| --- | --- | --- |
| gap_en_paraphrase | SR_en_canonical − SR_en_paraphrase |  |
| gap_ru_literal | SR_en_canonical − SR_ru_literal |  |
| Δlang_ru_literal | gap_ru_literal − gap_en_paraphrase |  |
| Δlang_ru_free_order | gap_ru_free_order − gap_en_paraphrase |  |
| Δlang_ru_negation | gap_ru_negation − gap_en_paraphrase |  |
| Δlang_code_switch | gap_code_switch − gap_en_paraphrase |  |

`Δlang` - главная метрика пилота, потому что она отделяет языковой эффект от простого instruction-string OOD. В основном дизайне она также задана как основной статистический эффект.

# Definition of Done: сцена v0

Сцена считается готовой, если:

```
[ ] agentview_rgb сохранён.
[ ] wrist_rgb сохранён.
[ ] task_uid уникален.
[ ] canonical_en заполнен.
[ ] bddl_file / env metadata заполнены.
[ ] Все реальные объекты внесены в scene.objects.
[ ] Все usable objects есть в object_lexicon.csv.
[ ] sim_handles сверены с живой средой.
[ ] target размечен.
[ ] reference размечен или null, если relation = none.
[ ] relation размечен.
[ ] success_predicates заполнены.
[ ] forbidden заполнен для negation или пустой.
[ ] Tier-1 variants написаны или axis_na с причиной.
[ ] Русские variants прошли native check.
[ ] validate_frames.py проходит без ошибок.
```

# Definition of Done: pilot v0

Пилот готов, если:

```
[ ] Есть 20 задач: 16 LIBERO + 4 SimplerEnv-bridge.
[ ] Есть ≥100 candidate scenes в task_inventory.
[ ] Есть screenshot sheet.
[ ] Есть object_lexicon.csv.
[ ] Есть frames_v0.jsonl.
[ ] Есть validate_frames.py.
[ ] Есть export_prompts.py.
[ ] Все обязательные картинки существуют.
[ ] Все sim_handles проверены.
[ ] Все Tier-1 variants готовы.
[ ] Native check passed.
[ ] Есть tag slava-pilot-v0.
[ ] Есть первые prompts для OpenVLA/GreenVLA-style eval.
```