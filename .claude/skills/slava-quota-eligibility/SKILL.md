---
name: slava-quota-eligibility
description: Mark quota_eligibility flags in task_inventory.jsonl (spatial_relation, pick_with_distractors, container, surface, has_distractor, same_category_distractor, same_color_distractor, ru_case_swap, ru_negation) and select a manifest that meets task.md's v0 quotas. Use when labeling scenes for quota fit or selecting a task set, especially past the 20-scene pilot.
---

# SLAVA quota-eligibility labeling

Source of truth: `AGENTS.md`'s "Мнемонические правила разметки квот" section
— the operational rules below are copied there verbatim and must stay in
sync with it; if you refine a rule, update both places. Quota targets
themselves live in `task.md`'s "Квоты v0" section (line ~546) — they're
explicitly marked "ориентировочные" (indicative), not hard requirements, so
treat under/over-shooting by a little as a discussion point, not a blocker.

## Always check evidence before labeling, never the task name alone

Task names lie by omission (`open_the_middle_drawer_of_the_cabinet` doesn't
tell you there's a `has_distractor` opportunity via the other drawers).
Check, in this order: `objects_raw`/BDDL/success condition, the object
lexicon, and every available RGB angle — same evidence order as
`slava-object-lexicon`.

## The nine flags

- `spatial_relation=true` — only for `left/right/on/next_to`. `front`,
  `between`, `in` don't count just because they're spatial-sounding. `on`
  can double-count for `surface` if that quota's own condition is also met.
- `pick_with_distractors=true` — target is pickable *and* there's at least
  one visible, plausible alternative pick. Background clutter alone doesn't
  qualify.
- `container=true` — natural `put X in drawer/bowl/basket/sink`.
- `surface=true` — natural `put X on plate/tray/table`. Racks, towels, and
  arbitrary surfaces don't count.
- `has_distractor=true` — a visible object or distinguishable part with
  which a plausible-but-checkably-wrong action exists. A `reference` object
  isn't automatically a distractor, but it can be one if picking it instead
  of target would itself be a plausible wrong pick.
- `same_category_distractor=true` — distractor shares `category_en` with
  target, per the lexicon — compare by lexicon category, not by surface
  similarity (color/packaging).
- `same_color_distractor=true` — distractor shares target's main `color_en`
  and the render actually confirms it. A matching label detail isn't enough.
- `ru_case_swap=true` — target and reference are two real, separately
  manipulable objects whose roles can flip and still be physically sensible
  and checkable. Two cubes: usually yes. `object → container`,
  `carrot → plate`, fixture-as-reference, or one side being a composite
  sub-object (a drawer): no, these are asymmetric pairs — see
  `slava-scene-roles` and `slava-instruction-variants` for why.
- `ru_negation=true` — a natural `не X, а Y` is possible, both candidates are
  visually grounded, and acting on the forbidden one is an unambiguous,
  checkable error. Any random extra object in the scene isn't sufficient —
  the forbidden candidate has to be genuinely confusable with target.

## A real gap the pilot found and fixed

`ru_case_swap` eligibility was internally inconsistent across otherwise
identical init states of the same task (`false` for 5 of 7 init states of
`pick_up_the_black_bowl_from_table_center_and_place_it_on_the_plate`, `true`
for the other 2) with no scene-composition difference — a labeling bug, not
a real distinction. If you find eligibility disagreeing across init states
of the *same* task with the *same* object set, that's a red flag to
re-render and compare before trusting either label, not a sign the earlier
label was deliberately scene-specific.

## Selecting a manifest against the quotas

D3 selection (`selected_tasks_v0.jsonl`) happens only after `task_inventory`
and `object_lexicon` are both settled — don't start authoring RU instruction
variants before the manifest is frozen, per `AGENTS.md`'s benchmark-order
diagram. When scaling the manifest size up (20 → ~200), re-derive quota
counts from the actual `quota_eligibility` fields across the candidate pool
rather than assuming the pilot's proportions generalize — a bigger pool
changes which quotas are the binding constraint.

## Контракт полей

Актуальные таблицы полей lexicon и `quota_eligibility` — в
[`docs/DATA_SCHEMAS.md`](../../../docs/DATA_SCHEMAS.md); сверено с живыми данными
08.08.2026. Там же описан `referring_strategy`, который на этапе авторинга
инструкций полагается записывать во фрейм, а не держать в голове.

## Масштабирование квот: две копии константы, которые разъедутся

Числа квот в task.md («Квоты v0») — абсолютные счётчики для 20 задач
(`ru_case_swap` 6/20, `ru_negation` 12/20 и т.д.), и сам task.md называет их
«ориентировочными».

> **Читать их на полном наборе как доли — НАШЕ решение, а не требование
> контракта.** В task.md о масштабировании квот не сказано ничего. Идея
> разумная (абсолютный счётчик для двадцати задач бессмысленно прикладывать к
> ста восьмидесяти), но это домысел: не выдавайте его за букву task.md и не
> считайте закрытым вопросом, если пользователь захочет иной способ.

Осторожно: целевое число `"ru_case_swap": 6` захардкожено в **двух** местах —
`scripts/generate_selected_scenes.py` и `src/slava_inventory/notebook_ui.py`.
Менять надо оба, иначе отбор и интерфейс будут расходиться молча.
