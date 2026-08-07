---
name: slava-visibility-review
description: Judge and record visible_agentview/visible_wrist for scene objects in task_inventory.jsonl (via data/visibility_review.html), including known pitfalls around composite/addressable objects and partial visibility. Use when doing or reviewing visibility labeling, especially when scaling from the 20-scene pilot to 120–180-task full-sets.
---

> **В свежем клоне `data/visibility_review.html` нет** — файл gitignore'ится.
> Сгенерировать соответствующим скриптом из `scripts/` перед разметкой.

# SLAVA object visibility review

Source of truth: `AGENTS.md`'s "Canonical inventory contract" section for
the value semantics, and `scripts/generate_visibility_review.py` /
`data/visibility_review.html` for the actual editable dashboard. This skill
is about judgment calls the dashboard's UI doesn't make for you.

## The four values

- `true` — confidently visible and recognizable.
- `"visible_partial"` — partially visible but still identifiable (e.g. a
  cabinet mostly off-frame on the wrist camera, but its handle/edge is
  there). This is a real, legitimate value — don't collapse it to `true` or
  `false` to save a decision.
- `false` — not visible, or visible but not recognizable as that object.
- `null` — not yet reviewed, or no camera for this scene (SimplerEnv WidowX
  has no wrist camera; wrist fields stay `null` and are treated as N/A in
  filters, not as "not visible").

## What the label actually attests to

`visible_agentview`/`visible_wrist` is a judgment about the *whole physical
object* (one `sim_handle`), made once per scene per camera. That's coarser
than "can a VLA model ground the specific thing the instruction refers to"
whenever the instruction refers to a *part* of that object (a particular
drawer, a particular side) rather than the object as a whole — see
`slava-scene-roles`'s composite-object section for the concrete case this
bit us on: a cabinet's overall visibility was `true`/`visible_partial`, but
that says nothing about whether its three individual drawers are
distinguishable from each other, especially on the wrist camera. If a frame
addresses a sub-part of an object, the whole-object visibility label is a
starting assumption, not a verified fact for that sub-part — re-check it
against the actual render at frame-authoring time.

## Three tools exist for this — know which one is current

The repo accumulated three different visibility-marking approaches over
time; they are not interchangeable, and only the third is the current entry
point for new work:

1. **`InventoryReviewer`** (`src/slava_inventory/notebook_ui.py`, used from
   `notebooks/01_collect_and_review_inventory.ipynb`) — the original,
   heaviest form: one Jupyter widget screen per scene combining the
   `usable_for_slava` decision, `candidate_slots`, *and* per-object
   agent/wrist visibility dropdowns (`unknown/visible/visible_partial/
   not_visible`) all at once. Built for D1's initial scene-by-scene triage,
   where visibility was just one of several judgments being made together.
2. **`VisibilityReviewer`** (same file) — a second, faster Jupyter widget
   decoupled from the scene-acceptance decision: visibility-only, with
   "All visible: agent"/"All visible: wrist" bulk buttons and a
   jump-to-first-pending filter. Built because marking visibility for every
   object of every scene one dropdown at a time (approach 1) didn't scale
   even at pilot size — bulk-accept-then-fix-exceptions is faster than
   one-by-one when most objects in most scenes really are visible.
3. **`scripts/generate_visibility_review.py` → `data/visibility_review.html`**
   (+ `apply_visibility_review.py`, `sync_selected_tasks_visibility.py`) —
   the current, browser-based dashboard, not a notebook. This is the one
   `AGENTS.md`'s "Основные точки входа" and the README point to now; use
   this for new work unless you have a specific reason to fall back to a
   notebook (e.g. no browser access in the environment). Adds two things
   the notebook tools don't have:
   - an optional `--hints path/to/review_hints.json` overlay of low-confidence
     AI-suggested values (`{task_uid, sim_handle, field, suggested_value,
     note}` per entry) shown as a clickable "AI guess: ... [use]" badge next
     to the real control — the suggestion is never written automatically,
     a human still has to click it, and unclicked hints leave the field
     exactly as it was;
   - `sync_selected_tasks_visibility.py`, a required step after applying
     corrections: `task_inventory.jsonl` (full pool) and
     `selected_tasks_v0.jsonl` (the frozen subset, or its full-set
     successor) both carry copies of `objects_raw[].visible_*`. Editing the
     dashboard only touches the inventory; forgetting to run the sync step
     leaves the frozen manifest holding stale visibility values — a second,
     easy-to-miss source-of-truth split, distinct from the inherited
     parent→sub-object one described below.

If you're asked to do a visibility pass at 120–180-task full-set scale and no browser
dashboard is practical for the setting you're in, the two notebook classes
are still there and still work — but pick `VisibilityReviewer` (bulk-first)
over `InventoryReviewer` (one dropdown at a time) for a visibility-only pass;
save `InventoryReviewer` for when scene-acceptance and slot candidates need
review in the same pass.

## Judgment calls that come up repeatedly

- A camera showing the object at the very edge of frame, small, or partly
  occluded by the gripper/another object → `visible_partial`, not `true`.
  Don't round up because you can technically tell it's there.
- An object visible but whose identity is only inferable from position/
  context (not actually seen) → this is a `false` on `visible_*`, separate
  from the lexicon's `semantic_identity_visually_recoverable` question. The
  visibility field is "is the object there and locatable," recoverability is
  "can you tell *which specific subtype* it is" — don't conflate the two
  when one is `true` and the other should legitimately be `no`/`review`.
- Wrist camera absent (SimplerEnv) vs wrist camera present but showing
  nothing useful: the former is `null`/N/A, the latter is a real `false` or
  `visible_partial` judgment — don't default both to `null`.

## Scaling from 20 to 120–180-task full-sets

At pilot scale, cross-checking every scene by eye was feasible. At ~200:

- batch by `raw_name`/fixture first — most visibility judgments for a
  recurring fixture (same cabinet, same stove) across many init states will
  be identical if the camera pose and fixture placement don't change; don't
  re-derive from scratch each time, but do spot-check a few per fixture
  rather than copy-pasting blind, since object placement (not camera pose)
  does vary between init states;
  the pilot's own composite-object gap is exactly what happens when a
  once-per-object judgment gets propagated to something it wasn't measuring;
- when a dashboard-vs-screenshot-sheet discrepancy shows up, don't
  rationalize it — `AGENTS.md` requires diffing the two on the same data and
  fixing the source of disagreement, not picking whichever looks more
  convenient;
- keep `notes` for any one-off judgment call that isn't covered by the rules
  above; if the same kind of one-off keeps recurring, that's the signal to
  turn it into a new rule here rather than re-deciding it every time.
