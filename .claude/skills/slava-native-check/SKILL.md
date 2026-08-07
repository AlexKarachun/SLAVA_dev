---
name: slava-native-check
description: Run or interpret the native-check pass on SLAVA RU instruction variants (data/frames_review.html) — naturalness/equivalence/ambiguity scoring, thresholds, native_check status, and what counts as done. Use when doing native check, reviewing scores, or scaling the review process past the 20-scene pilot.
---

> **В свежем клоне `data/frames_review.html` нет** — файл gitignore'ится.
> Сгенерировать: `python3 scripts/generate_frames_review.py`.

# SLAVA native check

Source of truth: `task.md`'s "Native check" section (line ~1128) for the
scoring contract, `scripts/generate_frames_review.py` /
`data/frames_review.html` for the actual dashboard, and
`scripts/apply_frames_review.py` for how corrections land back in
`frames_v0.jsonl`.

## Scope: which variants get scored

`SCORED_VARIANTS` in `generate_frames_review.py` — currently `ru_literal`,
`ru_free_order`, `ru_case_swap`, `ru_negation`, `code_switch`,
`ru_colloquial`, `ru_anaphora` — get naturalness/equivalence/ambiguity
inputs in the dashboard. `ru_colloquial`/`ru_anaphora` were added when those
two axes were first authored for all 20 pilot scenes (previously `null`
everywhere); if you add a new variant field to the schema, decide explicitly
whether it belongs in `SCORED_VARIANTS` — don't assume the dashboard picks
it up automatically, `render_variant_block` only scores fields listed there.

`en_paraphrase`/`en_canonical`/`ru_translit` are deliberately excluded:
"native check" means a Russian-native-speaker pass on genuine Russian-syntax
variants (code-switch is Russian syntax with English NPs, so it's in
scope). `en_paraphrase` is the English baseline used for the `Δlang` gap
metric elsewhere in the pipeline (see `slava-instruction-variants`), not
something a Russian native check evaluates. `ru_translit` is a mechanical,
deterministic transliteration of `ru_literal` — "naturalness" doesn't apply
to a script transform, and equivalence/ambiguity are inherited from
whatever `ru_literal` already scored, by construction, so scoring it again
would be redundant, not a second data point. All three still deserve an
agent quality pass (concision for `en_paraphrase`, correct/consistent
transliteration scheme for `ru_translit`), just not a 1–5 score in this
dashboard — they're listed in `TEXT_VARIANTS` (shown, editable) but not
`SCORED_VARIANTS`.

## The three metrics, and a real ambiguity in `task.md` about `ambiguity`

- **naturalness (1–5):** does this read as something a native speaker would
  actually say, not a stiff/literal translation.
- **equivalence (1–5):** same target/reference/relation, same content,
  nothing added or dropped relative to `en_canonical`.
- **ambiguity (1–5):** `task.md` never states the scale's polarity in
  words, but its pass threshold is `ambiguity >= 4` — the *same* direction
  as naturalness and equivalence (both unambiguously "higher = better").
  That only makes sense if this field is actually scoring **clarity /
  absence of ambiguity** (5 = one obvious referent, 1 = genuinely
  confusable), not "how ambiguous is this" in the literal sense of the word.
  **Resolved with the user during the pilot v0 freeze session:** higher =
  clearer (5 = maximally unambiguous), confirming the direction all 20
  pilot scenes were already scored in — no data changed. `expl.md` (this
  project's prior handoff, since removed) already noted the `ambiguity`
  field itself isn't in `task.md`'s own YAML schema example even though the
  Native-check section requires it — this metric has a documented history
  of being underspecified in `task.md`. If scaling past the pilot ever
  surfaces a case that reads oddly under "higher = clearer", re-confirm
  with the user rather than assuming the pilot answer generalizes silently.

## Thresholds and what to do below them

All three metrics need `>= 4` to pass. Below that: rewrite the variant (most
common outcome) or mark `axis_na` with a reason if the axis genuinely
doesn't apply to this scene (see `slava-instruction-variants` for when
`axis_na` is legitimate vs. a way to dodge a hard case).

`native_check` itself is a separate status field (`pending`/`passed`/
`failed`, see `NATIVE_CHECK_VALUES` in `frames_schema.py`), set once all
scored variants for that scene clear the thresholds (or have a justified
`axis_na`). Don't flip it to `passed` with scores still below 4 sitting in
`validation.naturalness`/`equivalence`/`ambiguity` — the dashboard lets you
do this manually, the schema doesn't stop you, so it's a discipline thing.

## What actually counted as "done" for pilot v0

`task.md`'s QA pipeline says `LLM draft -> ручная доводка -> validate_frames.py
-> native check -> freeze`, and the natural reading of "native check" is a
formal per-scene walkthrough of `data/frames_review.html` with recorded
scores. For the 20-scene pilot v0 freeze, the user explicitly decided his own
informal review of the RU rephrasings (reading them in conversation/IDE, not
a dashboard walkthrough with scores entered) was sufficient to count as the
human-verified native check — `validation.author`/`validation.notes` in
`frames_v0.jsonl` were updated to say so honestly (not "pending human
review"). This was a v0-scale, explicit, one-time call by the user, not a
new default. **Don't assume it applies automatically at 120–180-task full-sets** —
confirm with the user again whether an informal pass is still acceptable at
that volume, or whether a real per-scene dashboard walkthrough is expected.

## Recording the pass

`task.md` asks for a `validation_report.md` per pass: how many scenes
checked, how many variants rewritten, mean naturalness/equivalence/ambiguity,
typical errors, example fixes. At 20 scenes this was tracked informally in
conversation; at 120–180-task full-sets, actually write this artifact — it's also the
natural place to record which direction you're using for `ambiguity` so it
doesn't get re-litigated next pass.

## Applying corrections

Corrections come out of the dashboard as a JSON ops list (`set_role`,
`toggle_forbidden`, `set_slot`, `set_variant`, `set_axis_na`, `set_score`,
`set_validation`) and go back in via `scripts/apply_frames_review.py
corrections.json`, which re-derives `slots.target`/`slots.reference` from
`scene.objects[].role` and re-validates the whole file atomically. Never
hand-edit `frames_v0.jsonl` to apply a correction that the dashboard could
have expressed as an op — the re-derivation step is easy to forget by hand
and `validate_frames.py` won't catch a target/role mismatch that both sides
were edited to agree with each other incorrectly.
