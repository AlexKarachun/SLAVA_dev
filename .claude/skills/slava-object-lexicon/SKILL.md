---
name: slava-object-lexicon
description: Add or edit rows in data/object_lexicon.csv (category, semantic subtype, canonical EN/RU name, visual attributes, color, recoverability, synonyms, usable_v0). Use when a new raw_name/asset needs a lexicon entry, or when scaling scene collection past the 20-scene pilot to 120–180-task full-sets.
---

> ## ⚠ Какой файл размечать (актуально с 08.08.2026)
>
> В репозитории теперь ДВА набора, и перепутать их легко:
>
> - `data/task_inventory.jsonl` + `data/pilot_v0_release/frames_v0.jsonl` —
>   **замороженный пилот** (20 сцен, tag `slava-pilot-v0`). Не редактировать.
> - `data/full_set/task_inventory.jsonl` — **пул полномасштабного набора**,
>   896 сцен, 5312 объектов. Вся текущая работа здесь.
>
> Дашборды для полного набора генерируйте с `--input data/full_set/task_inventory.jsonl`
> и `--output` внутрь `data/full_set/`, иначе скрипт по умолчанию возьмёт пилот.
> Обзор пула — `data/full_set/README.md`.

# SLAVA object lexicon authoring

Source of truth for the *contract*: `AGENTS.md`'s "Object lexicon" section
and the live header of `data/object_lexicon.csv`. Read both before editing —
`task.md`'s D2 section (line ~393) shows an older, simpler column set
(`raw_name,category_en,category_ru,color_en,color_ru,allowed_synonyms_ru,
usable_v0,notes`) that predates `semantic_subtype_*`/`canonical_name_*`/
`visual_attributes_*`/`semantic_identity_visually_recoverable` — those fields
exist in the real CSV and are not optional extras, don't drop them because
`task.md`'s example doesn't show them. This mismatch is a known,
already-flagged drift; don't silently "fix" it back toward the old shape.

## Order of evidence, always in this order

```
1. real scene render (agentview, then wrist if present)
2. raw_name + sim_handle from task_inventory.jsonl
3. BDDL task semantics (data/libero_bddl/...)
4. HOPE mesh/texture (data/HOPE_3D_models/.../google_16k/texture_map.png), only if a HOPE object
5. only then: the lexicon decision
```

Never fill a row from `raw_name` alone. `raw_name` is often generic
(`alphabet_soup`, `wine_bottle`) and tells you nothing about what's actually
recognizable in the 256×256 render.

## Column-by-column

- `category_en/category_ru` — broad form factor: `can/банка`,
  `bottle/бутылка`, `brick pack/брикет`. Not the specific product.
- `semantic_subtype_en/semantic_subtype_ru` — the content/product identity
  from metadata (HOPE label, BDDL raw_name): `tomato sauce/томатный соус`.
  This is exactly the thing `semantic_identity_visually_recoverable` judges.
- `canonical_name_en/canonical_name_ru` — the natural full name used as the
  default authoring candidate: `tomato sauce can/банка томатного соуса`. Not
  an unconditional "always use this exact string," though — `en_canonical`
  (LIBERO's own task name) sometimes already commits to a shorter or
  subtype-based word for a given object, and every variant including
  `code_switch` should mirror that, not the CSV field, in those cases; see
  `slava-instruction-variants`'s "Referring strategy" section for the full
  decision rule.
- `visual_attributes_en/visual_attributes_ru` — short, observable
  differentiators independent of subtype: shape, dominant color, lid,
  label presence. For VLA grounding, one stable differentiator is usually
  enough; don't write a catalog description. If the render doesn't actually
  show what the mesh texture shows (e.g. label too small/blurry at
  render resolution), describe the render, not the asset.
- `semantic_identity_visually_recoverable` — `yes` / `no` / `review`. Can a
  human tell the *subtype* (not just the category) from the current render
  alone? A crisp, unambiguous full-res texture on the asset does **not**
  prove `yes` — recoverability is judged against the actual scene render,
  since that's what a VLA model would see. This is the same distinction that
  bit us on inherited visibility for composite sub-objects (see
  `slava-scene-roles`): "the source asset clearly shows X" is a different
  question from "this particular render/crop shows X." **A `no` here does
  not disqualify a scene or force `usable_v0=no`** — several pilot scenes
  (`butter`/`cream_cheese`/`milk`/`tomato_sauce`, all recoverable=`no`) are
  in the frozen 20-scene set and are fine, *because* the instruction
  variants all name the object by the same non-recoverable subtype word that
  LIBERO's own `en_canonical` already uses (see `slava-instruction-
  variants`'s "Referring strategy" section) — the limitation is symmetric
  across EN and RU, so it doesn't bias the language comparison. What this
  field actually gates is the *authoring* decision of which lexicon word a
  variant is allowed to use for that object, not scene eligibility on its
  own.
- `color_ru` must agree in gender with the noun in `canonical_name_ru`.
- `allowed_synonyms_ru` — same physical object, not its contents or a
  broader category. Don't merge two physical categories just because their
  Russian glosses sound similar, and don't mechanically bolt a color onto a
  synonym if the synonym's grammatical gender differs from the canonical
  name's (a synonym swap can silently break `color_ru` agreement). **Only
  the literal string in this field is a sanctioned alternative name for
  authoring** — a real near-miss from the pilot's `ru_colloquial` authoring
  pass: `flat_stove`'s row has `canonical_name_ru="электроплитка"`,
  `allowed_synonyms_ru="настольная плита"`; the natural spoken clipping
  "плитка" (dropping the "электро-" prefix) is genuinely common Russian and
  was the first draft for a colloquial variant, but it isn't what the CSV
  actually sanctions for this row, and got used anyway before a lexicon
  cross-check caught it. If a better synonym exists but isn't in the CSV,
  add it to the CSV first (and flag the addition) — don't let it slip into
  variant text unsanctioned; that's exactly the kind of drift this column
  exists to prevent. Currently one synonym per row (no established
  multi-value convention) — if a second synonym is ever genuinely needed,
  that's a schema question to raise explicitly, not to solve by picking a
  delimiter unilaterally.
- `usable_v0` — `no` if the object can't be named naturally and
  unambiguously in Russian, or can't be reliably recognized on the render.
  Don't discard `no` rows — they're a candidate pool for a future
  hard-lexical axis (v1.0/appendix), not dead weight.
- Russian fields use `е`, never `ё`. This is a lexicon-local formatting rule,
  not a project-wide writing-style rule.

## This CSV is not just a glossary — it's what every prompt is authored *against*

The lexicon only earns its keep if `frames_v0.jsonl`'s `scene.objects` and
every instruction variant actually draw from it consistently. That's a
separate discipline from writing correct CSV rows (see
`slava-instruction-variants`'s "Referring strategy" section for *which*
lexicon field an instruction should use for a given object, and its "Lexicon
cross-check" section for how to verify it did). Don't consider a lexicon
batch done just because the CSV rows look right in isolation — the actual
failure mode found at pilot scale (a `ru_colloquial` variant using an
unsanctioned synonym, a `code_switch` NP that didn't match `canonical_name_
en`) only shows up when you diff authored prompt text against the CSV,
row by row, after authoring, not while writing the CSV itself.

## Scaling from 20 to 120–180-task full-sets

The pilot's lexicon is small enough to eyeball for cross-row consistency by
hand. At 120–180-task full-sets, do an explicit consistency pass instead of trusting
memory:

- group rows by `category_en` and sanity-check that `color_ru` genders match
  `canonical_name_ru` genders across the whole group, not just within one
  row you just wrote;
- check for near-duplicate `raw_name`s that got different `canonical_name_ru`
  wording (copy-paste drift is the likely failure mode at this scale, not a
  wrong individual judgment call);
- re-open `screenshot_sheet_small.html` / `screenshot_sheet_full.html`
  (`scripts/generate_screenshot_sheet.py`) after a lexicon batch, don't just
  trust the CSV in isolation — it's the merged inventory×lexicon view and is
  what actually catches render-vs-lexicon mismatches;
- after frames/variants are authored, run a lexicon↔prompt cross-check pass
  (see `slava-instruction-variants`'s "Lexicon cross-check" section) as an
  actual script over every scene, not a read-through — at 20 scenes a
  careful read-through mostly worked but still missed real bugs (the
  `code_switch` article, the untranslated `basket_1` reference, a colloquial
  synonym not in `allowed_synonyms_ru`); at 120–180-task full-sets a read-through won't
  scale and will miss more, not less. The check is mechanical: for every
  object actually named in a variant (target/reference/forbidden), pull its
  lexicon row by `raw_name` and confirm the word used is one of
  `canonical_name_*`/`semantic_subtype_*`/`color_*`/`allowed_synonyms_ru` (or
  a scene-safe bare truncation of one, per the modifier-dropping rule) — flag
  anything that isn't, don't silently assume it's fine because it reads
  naturally.

## Контракт полей

Актуальные таблицы полей lexicon и `quota_eligibility` — в
[`docs/DATA_SCHEMAS.md`](../../../docs/DATA_SCHEMAS.md); сверено с живыми данными
08.08.2026. Там же описан `referring_strategy`, который на этапе авторинга
инструкций полагается записывать во фрейм, а не держать в голове.
