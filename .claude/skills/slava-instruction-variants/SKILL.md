---
name: slava-instruction-variants
description: Author Tier-1 instruction variants (en_paraphrase, ru_literal, ru_free_order, ru_case_swap, ru_negation, code_switch) for a SLAVA grounded_frame. Use when writing or reviewing variants.* in data/pilot_v0_release/frames_v0.jsonl, or when scaling frame authoring from the 20-scene pilot to the full set (120-180 tasks x 12-13 variants per task.md). Records two pilot defects that must not repeat: axes authored but never exported, and ru_case_swap being a probe whose success predicate must NOT be swapped.
---

# SLAVA instruction-variant authoring

Source of truth: `task.md` sections "Instruction variants для v0" and
"Правила авторинга вариантов" (around line 828 onward), and `AGENTS.md`'s
"Главный принцип: это VLA-бенчмарк". Read both before authoring — this skill
is the *operational* layer (how to do it well, what we got wrong the first
time), not a replacement for the schema definition.

## The one rule everything else follows

> Один вариант = один лингвистический механизм. Слоты (target/reference/
> relation) должны сохраняться. Нельзя добавлять подсказки, которых нет в
> canonical task, и нельзя менять target/reference/relation, если это не
> специально размеченная contrast pair (`ru_case_swap`, `ru_negation`).

Every variant is a controlled edit along exactly one axis. If you catch
yourself changing two things at once (wording *and* word order, e.g.), you've
drifted into a different variant's job.

## These are VLA prompts, not literary translation

We over-wrote this on the first 20-scene pass and had to trim it back. A VLA
policy consumes the instruction as a short, direct command — every extra
clause is something the language-grounding stage has to parse for no
analytical benefit, and it also makes `token_len` diverge from
`en_canonical`/`mt_russian` for no reason.

Concrete fixes made during the pilot review, keep repeating this pattern:

| Over-written (rejected) | Trimmed (kept) | Why |
| --- | --- | --- |
| `shove the plate forward until it sits in front of the stove` | `shove the plate to the front of the stove` | the `until it sits...` clause just restates the relation already in the verb phrase |
| `grab the black bowl sitting at the center of the table and set it down on the plate` | `grab the black bowl at the center of the table and set it on the plate` | `sitting`/`down` add zero disambiguating content |
| `pick up the green block and place it on top of the yellow block` | `pick up the green block and place it on the yellow block` | `on top of` vs `on` — `on` already matches the `relation` slot name, no extra clarity gained |
| `grab X and drop it into the basket` (all 4 basket tasks) | `grab X and put it into the basket` | `drop` implies careless/from-height manner not present in canonical `place` — a manner shift, not a pure paraphrase, so it also *failed equivalence*, not just concision |

Rule of thumb: if a clause could be deleted without a native speaker asking
"wait, which one?", delete it.

## Referring strategy: which lexicon field to use, and why RU must mirror `en_canonical`

`task.md` calls this "referring_strategy" and says it's a per-instruction
decision, not a lexicon field: name the object by `semantic_subtype`
(`butter`) or by `visual_attributes` if the subtype doesn't actually read on
the render. It doesn't spell out the decision procedure beyond that — this
is what the pilot's full lexicon-cross-check pass (20 scenes, every RU/EN
variant, see `slava-object-lexicon`'s recoverability section) established as
the operational rule. Get this wrong and it's invisible in a normal
read-through — it only surfaces when you diff variant text against the CSV
row by row.

**The controlling constraint: `en_canonical` is immutable (it's LIBERO's own
literal task name), so it has already made the referring-strategy decision
for this task — every other variant, RU included, must mirror that same
decision, not re-derive its own.** Two concrete patterns this produces:

1. **Subtype vs. full canonical name.** Several HOPE grocery items in the
   pilot (`butter`, `cream_cheese`, `milk`, `tomato_sauce`, and their
   distractors) have `semantic_identity_visually_recoverable=no` — a human
   genuinely cannot read the product identity off the render at its actual
   resolution. Despite that, `en_canonical` (`"pick up the butter..."`)
   names them by `semantic_subtype_en`, not the fuller
   `canonical_name_en`/`canonical_name_ru` (`butter package`/`брикет
   масла`). RU must do the same (`масло`, not `брикет масла`) —
   **not** switch to `visual_attributes` strategy just because RU authoring
   happens after the recoverability problem was noticed. Switching only on
   the RU side would silently make RU harder than EN for a reason that has
   nothing to do with language (an uncontrolled referring-strategy
   confound baked straight into `Δlang`). The non-recoverability is a
   property of the *scene* (already fixed at D3 scene selection), and it's
   symmetric across EN/RU, so it doesn't bias the language comparison — but
   only as long as every variant, RU included, keeps mirroring what
   `en_canonical` already committed to.
2. **Modifier-dropping.** `canonical_name_ru`/`_en` sometimes carries a
   modifier `en_canonical` itself never uses — `wine_rack`'s canonical is
   "винная стойка"/"wine rack" but `en_canonical` says only `"...on the
   rack"`; `flat_stove`'s canonical is "электроплитка"/"portable stove" but
   `en_canonical` says only `"...the stove"`. RU (and `code_switch`'s
   English NP) should mirror the *bare* word actually in play
   (`стойку`/`rack`, `плиту`/`stove`), not force in the modifier just
   because the CSV field technically has it. This is safe exactly when
   dropping the modifier stays unambiguous given what else is in the scene
   (only one rack-shaped, one stove-shaped object here) — if two objects in
   the scene could both plausibly answer to the bare word, keep the
   modifier or the color instead.

Getting the *object* right (correct `raw_name` → correct row) but the
*strategy* wrong (grabbing `canonical_name_ru` when `en_canonical` uses the
subtype, or vice versa) is the failure mode this section exists to prevent.
When scaling to 120–180-task full-sets: for every new task, read `en_canonical` first,
identify which word it actually uses for each named object, and let *that*
— not a fixed field-priority rule — decide what every other variant uses for
that object.

## Per-variant checklist

### `en_paraphrase`
- Keep every content word from `en_canonical` (object names, spatial terms,
  colors) — this is the OOD-wording control, not a vocabulary test. See
  `task.md` line ~881.
- It anchors `Δlang = gap(RU-axis) − gap(en_paraphrase)` — if it's not a
  genuinely fluent, equally-terse English paraphrase, that baseline is
  contaminated and every downstream RU-gap number becomes uninterpretable.
- You (the agent) can review this one yourself even when the human reviewer
  isn't confident in English — it's the one variant that doesn't require
  Russian native-check, but it still needs *your* honest quality pass, not a
  rubber stamp. Check for: same content words, same or shorter length, no
  manner/register drift (see `drop` vs `put` above).

### `ru_literal`
- Natural, direct Russian imperative. Use `object_lexicon.csv` names, not
  invented synonyms — and see "Referring strategy" above for *which*
  lexicon field/word to use (mirror what `en_canonical` already committed
  to, don't independently pick `canonical_name_ru` vs `semantic_subtype_ru`
  vs a modifier-bearing form). No literary flourish — `task.md`'s explicit
  bad example: `осуществи перемещение красной кружки в правую область
  относительно синей миски` (bureaucratic paraphrase of "move") vs good:
  `поставь красную кружку справа от синей миски`.

### `ru_free_order`
- Natural Russian word order, genuinely different from `ru_literal`, not
  scrambled ("Yoda-Russian"). Slots must not change. Usually: front-load the
  reference/location clause, verb+target moves to the end.

### `ru_case_swap`
- Requires target and reference to be **two real, separately manipulable
  objects** where swapping which one moves still makes physical sense. Two
  cubes: yes. `предмет → корзина`, `бутылка → стойка`, any container/fixture
  as one side of the pair: no — write `axis_na` with the concrete physical
  reason instead of forcing a nonsensical variant. Composite sub-objects
  (drawers of one cabinet) never get `ru_case_swap` either — see
  `slava-scene-roles` skill — there's no second manipulable object, only a
  state change on one part.
- Never leave both `ru_case_swap: null` and no `axis_na` entry —
  `frames_schema.py` rejects that combination.

### `ru_negation`
- Needs a real `forbidden` object already present in `scene.objects` (see
  `slava-scene-roles`). The forbidden candidate must be genuinely confusable
  with the target (same rough category/plausible action target), not just
  "some other object in the scene."
- **Exception: a target/reference role-swap negation** ("pick X, not Y"
  where Y *is* the reference, e.g. `widowx_stack_cube`'s "возьми не желтый,
  а зеленый... и поставь на желтый" — yellow is the placement surface, not
  a distractor) needs **no** `forbidden` entry at all, and must NOT put the
  reference in `forbidden` (see `slava-scene-roles`'s hard invariant —
  reference in forbidden makes every legitimate success self-contradictory,
  since completing the task requires touching the reference). This kind of
  negation failure is caught by `target_grounding_error` (wrong first
  contact), a different signal than `forbidden_object_touch` entirely.
  `frames_schema.py`'s validator only demands non-empty `forbidden` for a
  filled `ru_negation` when the scene has a spare object beyond target/
  reference to name — a genuine 2-object scene is exempt.
- `task.md`'s bad example: `не ошибись и возьми красную кружку` — this names
  no forbidden object, so there's nothing for `forbidden_object_touch` to
  measure. Good pattern: `не X, а Y <verb+relation>` where X is exactly the
  id(s) in `slots.forbidden`.
- If a scene has more than one plausible wrong candidate (e.g. a 3-drawer
  cabinet where only the top drawer is named as forbidden even though the
  bottom one is equally plausible), it's fine to leave the un-named plausible
  distractor as `role: distractor` without adding it to `slots.forbidden` —
  `forbidden` tracks what the *sentence itself* names as wrong, not every
  physically-plausible wrong pick. Don't inflate `forbidden` to "be safe";
  it changes what `forbidden_object_touch` is diagnosing.

### `code_switch`
- Russian syntax, English noun phrases, verb usually stays Russian. Don't
  inflect the English noun phrase.
- The English NP must be the word `en_canonical` already established for
  that object — see "Referring strategy" above (same rule that governs
  `canonical_name_en` vs `semantic_subtype_en` vs modifier-dropping applies
  here verbatim, since `code_switch`'s English half is just `en_canonical`'s
  own word choice re-inserted into a Russian frame). Verified for all 20
  scenes in the pilot by cross-checking every `code_switch` NP against
  `en_canonical`/`object_lexicon.csv` programmatically — zero mismatches.
- A real mistake from the pilot review, now fixed: `turn_on_the_stove`'s
  `code_switch` briefly carried an English article (`включи the stove`) —
  every other scene's code_switch drops articles entirely when translating
  the NP (`открой middle drawer шкафа`, not `открой the middle drawer`).
  Check for stray `the`/`a` whenever you translate an NP into this axis.
- Another real mistake, now fixed: the four `pick_up_the_*_and_place_it_in_
  the_basket` scenes translated the target NP to English but left the
  reference (`basket_1`) in Russian (`в корзину`) while every other
  multi-object scene's code_switch translates *both* target and reference
  NPs. If a scene has a named reference object, code_switch should translate
  it too, not just the target.

### `mt_russian` (not authored, but adjacent)
- This is a real MT pass output (currently DeepL API — task.md's own
  "Google Translate" is just an example provider, not a requirement; see
  `slava-mt-russian` for the actual pipeline, auth, and how to switch
  provider), never LLM-written and never hand-edited — don't "clean it up"
  even if it reads awkwardly. Store `mt_metadata: {system, date}` alongside.
  If you're asked to fill this field with an LLM translation instead of a
  real MT call, stop and flag it — that silently breaks the `Δlang`
  baseline's validity, it's not a shortcut you can take unilaterally.

## The three "желательные"/exploratory variants (`ru_translit`, `ru_colloquial`, `ru_anaphora`)

`task.md` gives one short example each and little else. Authored for all 20
pilot scenes in one pass (previously all `null`) — this is the operational
rule set that pass established, keep following it when scaling to ~200.

### `ru_translit`
- Purely mechanical: transliterate `ru_literal` (not any other variant) with
  **one fixed scheme for the whole benchmark** — `task.md` explicitly
  requires a single scheme, not a per-scene judgment call. The pilot's
  scheme (verified byte-for-byte against `task.md`'s own worked example,
  `поставь красную кружку справа от синей миски` →
  `postav krasnuyu kruzhku sprava ot siney miski`):
  `а→a б→b в→v г→g д→d е→e ё→yo ж→zh з→z и→i й→y к→k л→l м→m н→n о→o п→p
  р→r с→s т→t у→u ф→f х→kh ц→ts ч→ch ш→sh щ→shch ъ→(dropped) ы→y ь→(dropped)
  э→e ю→yu я→ya`. Note `ь`/`ъ` are dropped entirely (no apostrophe) — that's
  what makes `поставь`→`postav` come out as it does in `task.md`'s own
  example, not a simplification the pilot introduced.
- Not native-check scored (see `slava-native-check`): "naturalness" doesn't
  apply to a script transform, and equivalence/ambiguity are inherited from
  whatever `ru_literal` already scored, by construction. Never write this by
  hand per scene — always derive it programmatically from `ru_literal`, or
  the "one fixed scheme" requirement will drift.

### `ru_colloquial`
- `task.md`'s only example replaces a specific noun with a vague one
  (`штука`) and warns: only do this if exactly one referent is plausible;
  if in doubt, skip it (`axis_na` or leave for v0.1). At pilot scale, most
  scenes have 3+ visible objects that could plausibly be called "a thing"
  (the shared libero_goal kitchen scene, the 5-7-distractor basket scenes),
  which makes the vague-noun device unsafe almost everywhere it would
  otherwise be tempting — using it in a scene with competing referents would
  silently turn a colloquial-register variant into an ambiguity bug.
- The pilot's operationalization, chosen specifically to keep ambiguity risk
  at zero while still producing a genuinely informal register: attach the
  colloquial imperative particle **`-ка`** to the main verb
  (`подними`→`подними-ка`, `положи`→`положи-ка`, etc. — for a two-verb
  sentence, attach it once, to the first verb only, matching natural spoken
  Russian), and, only where `object_lexicon.csv`'s `allowed_synonyms_ru`
  already sanctions an informal alternative for that exact object, swap to
  it (`wooden_cabinet`'s synonym `шкафчик`: `открой-ка средний ящик
  шкафчика`). Every other referring expression stays byte-identical to
  `ru_literal` — zero referential risk, because nothing about *which* object
  is named ever changes, only register markers.
- **Never invent a colloquial synonym that isn't literally in
  `allowed_synonyms_ru`, even if it's linguistically well-motivated.** A
  real near-miss from the pilot: `flat_stove`'s `canonical_name_ru` is
  "электроплитка"; the natural spoken clipping "плитка" (dropping the
  "электро-" prefix) is real, common Russian and was the first draft — but
  it isn't what `allowed_synonyms_ru` actually says for this row
  (`настольная плита`). Caught on a lexicon cross-check pass and fixed to
  `настольную плиту`/`настольной плиты` instead. If a genuinely better
  colloquial word exists but isn't in the CSV, the correct move is to
  propose adding it to `object_lexicon.csv` (and flag that to the user) —
  not to slip it into variant text unsanctioned. This is the same
  discipline as `code_switch`'s "match the lexicon, don't invent a gloss"
  rule, just for the Russian side.
- If a scene genuinely has no safe move at all (rare, given the `-ка`-only
  fallback almost always works), use `axis_na` with the concrete reason
  (too many plausible referents for any noun-level vagueness, not just "not
  sure").

### `ru_anaphora`
- `task.md`'s example decomposes a single-clause canonical instruction into
  two clauses, naming the target once and referring back to it with an
  overt pronoun (`возьми красную кружку и поставь её справа от синей
  миски`). The axis only makes sense where **(a)** the action is genuinely
  a two-step pick-then-place (something is grasped, then moved/placed
  relative to something else) and **(b)** `ru_literal` doesn't already use
  this exact device, or there's no room for a distinct contrast:
  - `action=open`/`turn_on` (single state-change on one object, nothing is
    picked up or carried) — always `axis_na`, there is no natural two-clause
    decomposition; forcing one would misdescribe the physical action.
  - `action=push` — also `axis_na`: pushing is one continuous motion, not a
    grasp-then-place pair; `"возьми X и толкни его"` would claim the robot
    picks the object up, which it doesn't.
  - `action=pick_place`/`stack` where `en_canonical`/`ru_literal` are
    single-clause (`put X on Y`, `stack X on Y`) — genuine, fillable
    contrast: decompose to `возьми X и <verb> его/её/это на/в Y`, picking
    the pronoun for `X`'s grammatical gender (`бутылка`→её,
    `масло`/`молоко`→его [neuter takes the same accusative form as
    masculine], `сыр`/`соус`/`кубик`→его). Double-check gender per object,
    the same discipline `object_lexicon.csv`'s `color_ru` agreement rule
    already requires — a mismatched pronoun is a naturalness bug the same
    way a mismatched `color_ru` gender is.
  - `action=pick_place` where `en_canonical` **already** phrases the task as
    two clauses with a pronoun (this pilot's `pick_up_the_black_bowl_from_
    table_center...`: `"...place it on the plate"`, and `ru_literal`
    mirrors it: `"...поставь ее на тарелку"`) — `axis_na`, because
    `ru_anaphora` would just duplicate `ru_literal` with no distinct
    contrast to offer. Don't fill a field just to fill it; a variant that's
    identical in mechanism to another variant isn't a second data point.

## Грамматика: обязательна везде, кроме `mt_russian`

Русские варианты, которые пишем мы (`ru_literal`, `ru_free_order`,
`ru_case_swap`, `ru_negation`, русская часть `code_switch`), должны быть
грамматически безупречны. Не из эстетики: неестественная или ошибочная
формулировка становится вторым изменением сверх исследуемой оси, и провал по
ней уже нельзя приписать языку — это ровно та объекция к результату, которую
дешевле снять заранее, чем оправдываться потом.

**`mt_russian` — исключение, и единственное.** Там ошибки не чинятся никогда:
это сырой машинный перевод, его кривизна и есть измеряемая величина (правило
`task.md`: «не редактировать, не улучшать, не нормализовать»; разбор — skill
`slava-mt-russian`). Живой пример из пилота, который регулярно принимают за наш
недосмотр: `«возьмите чёрную миску со середины стола»` — верно было бы
«с середины», но это выход DeepL, и он остаётся как есть.

Что проверять в своих вариантах, по опыту пилота:

- **предлог `с`/`со`** — `со` только перед стечением согласных, где иначе не
  выговорить (`со стола`, `со шкафа`, `со мной`), но `с середины`, `с тарелки`,
  `с полки`;
- **падеж после предлога** — `положи на тарелку` (винительный), `лежит на
  тарелке` (предложный); при перестановке слов в `ru_free_order` падежи не
  «съезжают»;
- **род и число прилагательного** согласованы с существительным из лексикона —
  особенно когда подставляется синоним из `allowed_synonyms_ru` с другим родом
  (правило лексикона, см. `slava-object-lexicon`);
- **вид глагола** — в инструкции роботу совершенный: `подними`, `поставь`, а не
  `поднимай`;
- **`ru_case_swap` остаётся грамматичным** после перестановки ролей: команда
  должна быть корректной русской фразой, просто с обратным смыслом — иначе
  измеряем не чувствительность к порядку, а реакцию на кривой текст.

Проверять глазами при native check (`slava-native-check`): формальной проверки
на это нет и быть не может.

## Before marking a scene done

Re-read the finished variant set for the scene against `en_canonical` in one
pass: does every variant refer to the same target, same reference, same
relation (except `ru_case_swap`/`ru_negation`, which contrast it on purpose)?
Is there a variant that's noticeably longer than the others for no reason?
That's the signal to trim.

## Lexicon cross-check, not just a read-through

A read-through catches phrasing problems but not silent lexicon drift —
the pilot's full re-audit (see `slava-object-lexicon`'s scaling section) ran
a small script per scene: for every named object (target/reference/
forbidden), pull `object_lexicon.csv`'s row by `raw_name` and check every RU
variant's noun/color choice against `canonical_name_ru`/`semantic_subtype_
ru`/`color_ru`/`allowed_synonyms_ru`, and every `code_switch` NP against
`canonical_name_en`/`semantic_subtype_en`. Do this as an actual script pass
at 120–180-task full-set scale, not eyeballing — it's what caught the `code_switch`
article/basket-translation bugs and the `ru_colloquial` "плитка" near-miss
documented above, none of which were visible from reading the sentences in
isolation.

## Написать вариант ≠ запустить его (дефект пилота, 08.08.2026)

**Во фреймах пилота заполнено 11 осей, а `scripts/export_prompts.py` выгружает
7.** В стол ушли `ru_free_order` (20 сцен), `ru_colloquial` (20), `ru_translit`
(20), `ru_anaphora` (11) — 71 написанная инструкция, по которой нет ни одного
эпизода. Трёх последних нет даже в `VARIANT_ORDER` генератора отчёта, то есть
они невидимы и в таблицах. Обнаружилось это только когда пользователь спросил,
почему в отчёте пустая строка.

Гейт — константа `PRIMARY_VARIANTS` в `scripts/export_prompts.py`. Она
зафиксирована по списку task.md «Сначала затравка» (6 primary + `mt_russian`), а
полный набор требует **12–13 осей** (task.md, «Потом полный набор»). То есть на
масштабе этот список неверен по построению, а не «забыли одну ось».

**Правило: ось считается сделанной, только когда она (а) заполнена во фреймах,
(б) добавлена в `PRIMARY_VARIANTS`, (в) добавлена в `VARIANT_ORDER` генератора
отчёта, (г) появилась в `prompts_*.jsonl` после перезапуска экспорта.** Три
множества должны совпадать; расхождение — потерянная работа, а не мелочь.
Проверять это стоит скриптом (в `validate_frames.py` напрашивается ассерт:
каждая непустая, не-`axis_na` ось присутствует в экспорте либо стоит в явном
списке исключений с причиной).

## `ru_case_swap` — зонд, а не задача

Самая контринтуитивная ось в наборе. Её легко «починить» и тем самым сломать.

**Предикат успеха намеренно НЕ переворачивается вместе с текстом.** Если
перевернуть и его, получится другая физическая задача с другой сложностью, и
провал станет неотличим от «стало объективно труднее». Поэтому
`slots.success_predicates` для этой оси остаются как у исходной сцены.

Следствие: `env_success` на этой оси отвечает на вопрос «сделал ли робот
ИСХОДНОЕ задание», то есть высокий SR означает «модель не заметила
перестановку». Успех считается отдельно — из финальных поз против перевёрнутой
инструкции (`auto_label._swapped_success`), а источник записывается в поле
`success_result_source`/`success_source` строки аннотации. **Не переворачивайте
`arg1`/`arg2` в предикатах при авторинге.**

Что показал пилот: у OpenVLA-OFT по старому критерию было 4/4, по правильному —
0/4. Единственная модель, воспроизводящая свою английскую базу, во всех четырёх
сценах выполнила исходную задачу и перестановки не заметила вовсе.

**Мина на полном наборе:** `_swapped_success` умеет только отношение `on`. На
`left_of`/`right_of`/`next_to`/`in` он возвращает `None`, и успех берётся из
предиката среды — то есть измеряется обратное задуманному. В пилоте все 8 сцен
были `on`, поэтому не выстрелило; квоты task.md по отношениям шире. С 08.08.2026
такие строки помечаются `success_source = "env_fallback_unsupported_relation"`,
чтобы это было видно в данных. **Перед сбором полного набора либо расширьте
`_swapped_success` на остальные отношения, либо не авторьте `ru_case_swap` вне
`on`.**

**Знаменатель у этой оси свой.** Она применима только там, где есть два реально
переставляемых предмета: в пилоте 8 сцен из 20. Её SR несопоставим с
`ru_literal` без стратификации; `axis_na` обязана фиксировать неприменимость.

## Черновики вариантов: `build_frames_v0.py` не масштабируется

Скрипт называют «LLM-draft regenerator», и это вводит в заблуждение. Внутри —
десять рукописных словарей `TEMPLATES` по семействам задач, с литеральными
русскими строками и картой ролей по литеральным `sim_handle`. На незнакомую
задачу он не обобщается никак. На 120–180 задачах это либо файл на несколько
тысяч строк, либо переписывание.

**Переход на данные вместо кода — предварительный шаг, а не рефакторинг «потом»:**
варианты и роли должны лежать в JSONL/CSV, ключом по семейству задачи, а скрипт
их потреблять.

