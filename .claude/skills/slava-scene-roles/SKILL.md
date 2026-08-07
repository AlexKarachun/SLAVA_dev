---
name: slava-scene-roles
description: Assign scene.objects roles (target/reference/distractor/background) and slots (target/reference/relation/forbidden/success_predicates) when authoring a SLAVA grounded_frame in data/pilot_v0_release/frames_v0.jsonl, including composite/addressable objects (e.g. a cabinet's individual drawers). Use when building or reviewing frames, especially when scaling past the 20-scene pilot.
---

# SLAVA scene grounding: roles, slots, composite objects

Source of truth: `AGENTS.md`'s "grounded semantic frames v0.2" entry and its
two mnemonic-rule subsections (composite objects; `task.md` contract), plus
`data/pilot_v0_release/frames_v0.schema.json` / `src/slava_inventory/frames_schema.py` for
the literal contract. This skill is the judgment layer on top of that
contract — the four roles look simple but the boundary cases are where the
pilot actually spent its time.

## The four roles are about the scene, not the sentence

- `target` — what the robot must act on. Exactly one per scene.
- `reference` — the object/place success is measured against. At most one;
  `null` if the action has no second object (`open`, `turn_on`).
- `distractor` — a *plausible wrong pick*: something the robot could
  plausibly make first contact with instead of target and be wrong. Judge
  this against `first_contact_object`/`wrong_object_rate` from `task.md`,
  which score whatever the robot touches *first*, regardless of whether that
  object even affords the instructed verb. **Do not scope distractor to
  "same affordance as this task's action"** — a real mistake from the pilot:
  in `open_the_middle_drawer_of_the_cabinet` and `turn_on_the_stove`, a
  wine bottle / cream cheese brick / plate / bowl sitting on the same table
  were first marked `background` on the reasoning "you can't open/turn-on a
  bottle." That's the wrong question. The right question is "could the
  robot's attention land on this graspable object instead of the true
  target?" — and for any small, graspable, salient tabletop prop shared in
  the scene, the answer is yes, independent of the current task's verb. Any
  small graspable prop (can/bottle/carton/box/dish/bowl/plate/brick
  pack/cube) present in the scene is a `distractor` candidate for *every*
  task set in that scene, not just tasks whose action-type matches it.
- `background` — visible, but not a plausible false-target for *first
  contact*. In practice this is large fixed fixtures/appliances/furniture
  the robot cannot pick up bodily (a cabinet body when none of its drawers
  are in play, a stove, a wine rack) — not "objects whose category doesn't
  match this task's verb." Most scene clutter that's actually `background`
  is exactly this: fixed, not graspable.

Note the resulting asymmetry with `ru_negation`/`forbidden`: a bottle can be
`distractor` (plausible wrong first-contact target) in `turn_on_the_stove`
even though it would be nonsensical to write `axis_na`-worthy negation text
like "не бутылку, а плиту включи" — negation needs the forbidden candidate to
share the instructed verb's affordance (see
`AGENTS.md`'s `ru_negation` mnemonic and `slava-instruction-variants`), while
`distractor` role only needs plausible wrong first contact. A `distractor`
object with no matching `forbidden`/`ru_negation` entry is normal and
expected — see the `forbidden` note above.

`forbidden` is **not a fifth role**. It's an independent list of ids in
`slots.forbidden` — the subset of `distractor` objects that a specific
`ru_negation` variant names as wrong. A `distractor` not in `forbidden` is a
normal, expected state — it means "this object could plausibly be grabbed
by mistake" without claiming the current instruction text calls it out by
name. Don't inflate `forbidden` to cover every distractor "just in case" —
it changes what `forbidden_object_touch` is diagnosing (see
`slava-instruction-variants`'s `ru_negation` section).

**Hard invariant, enforced by `validate_frames()` (found the hard way,
2026-08-05): `reference` must never be in `forbidden`.** This doc used to
say the forbidden subset was "usually distractor, occasionally reference" —
that "occasionally reference" was itself the bug, not a valid case: it
shipped in `widowx_stack_cube` (D4, `forbidden=[reference]`, a 2-object
stack scene with no distractor at all) and caused every legitimate success
— which necessarily involves contact with the reference object, since the
task's own relation ("stack X **on** Y") is defined *in terms of* touching
it — to auto-label as `negation_error` instead of `success`. The
`touched_objects ∩ forbidden` check that drives `negation_error` cannot
distinguish "touched the reference as required by the task" from "touched
a genuinely forbidden object"; putting `reference` in `forbidden` at all
makes the check self-contradictory (finishing the task correctly requires
triggering it). A "pick X, not Y" negation where Y is the reference itself
(a target/reference role-swap, not a third distractor) is correctly caught
by `target_grounding_error` (wrong first contact) instead — it does not
need `forbidden` at all, and `frames_schema.py`'s validator only requires
`forbidden` non-empty for `ru_negation` when the scene actually has a spare
object beyond target/reference for it to name.

## Composite / addressable objects (drawers, sub-parts of one physical thing)

When target or a distractor is an addressable *part* of one physical fixture
(a specific drawer of a cabinet, not the cabinet as a whole), model it as
synthetic sub-objects in `scene.objects`: same `sim_handle` (one physical
object in the sim), different `id` per part, each with its own `role`.

**The `id` must literally be the BDDL region name for that part** — the
fixture's `:target` name plus the region name from `:regions`, joined with a
single underscore (e.g. `wooden_cabinet_1_middle_region`,
`wooden_cabinet_1_top_region`), matching what the task's `:goal` predicate
and `task_inventory.jsonl`'s `success_predicates` already reference. Do not
invent a naming scheme (a real mistake from the pilot: `build_frames_v0.py`
first used `wooden_cabinet_1__middle_drawer` — double underscore, a made-up
`_drawer` suffix — which matched nothing in the BDDL file or in
`task_inventory`, and had to be fixed after the fact). Check the actual
`.bddl` file's `:regions` block before naming anything.

If the fixture has more named regions than you're using (e.g. a cabinet with
top/middle/bottom drawers when only one is the target), don't silently drop
the unused ones from `scene.objects` — a physically distinguishable,
addressable part that's visible in the render belongs in the scene
description even if it's just `role: distractor` with no `forbidden` entry.
The pilot's first pass omitted the third drawer entirely; it should have
been there as a background/distractor object from the start.

Composite sub-objects never get `ru_case_swap`: there's no second
manipulable object to swap roles with (`reference` stays `null`; both parts
are `target`/`distractor` within one physical object). That's a
`ru_negation`-only situation — write `axis_na` for `ru_case_swap` with that
reasoning.

**Known limitation to check every time, not assume:** `visible_agentview`/
`visible_wrist` for these synthetic sub-objects gets inherited wholesale from
the one physical-object visibility judgment made in `visibility_review.html`
("is the cabinet visible") — that human review never asked "can you tell
*this specific part* apart from its neighbor," which is a different, finer
question, especially on the wrist camera where the whole fixture is often
barely in frame. Before freezing a scene with a composite object, spot-check
the actual render yourself (crop and zoom, don't eyeball the thumbnail) to
confirm each addressable part is genuinely distinguishable, per camera, per
scene. Don't reuse the parent's `true`/`visible_partial` value on faith.

## `success_predicates`

Structured, not raw BDDL/inventory copy-paste:

- `{"type": "spatial_relation", "relation": ..., "arg1": target_id, "arg2": reference_id}` for two-object tasks;
- `{"type": "state", "predicate": "open"|"turned_on", "arg1": target_id}` for
  single-object state-change tasks (`open`, `turn_on`) — `task.md`'s
  schema example doesn't show this case explicitly, but it's a natural,
  contract-consistent extension, not a deviation. If you're extending the
  schema into genuinely new territory beyond this, say so explicitly per the
  `task.md`-contract rule in `AGENTS.md` rather than deciding silently.

All `arg1`/`arg2` must be ids that exist in this scene's `scene.objects`, not
raw BDDL region strings and not `task_inventory.jsonl` object ids from a
different id scheme.

## Before marking a scene done

Ask: does every visible, addressable thing in the render have a role? Is
there exactly one `target`? Is `reference` non-null iff `relation` is
non-null? Does every id in `forbidden` actually appear in the text of a
filled-in `ru_negation`? If any answer is "not sure," go look at the render
again — don't reason from the object list alone.

## `success_predicates` и `ru_case_swap`: не переворачивать

Для оси `ru_case_swap` предикат успеха остаётся **как у исходной сцены**.
Перевернуть `arg1`/`arg2` вместе с текстом — значит превратить зонд в другую
физическую задачу, и провал станет неотличим от «стало объективно труднее».
Успех по этой оси пересчитывается ниже по цепочке из финальных поз
(`auto_label._swapped_success`). Подробности и мина с отношениями кроме `on` —
skill `slava-instruction-variants`, раздел «`ru_case_swap` — зонд, а не задача».
