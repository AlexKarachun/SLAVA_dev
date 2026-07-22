# Agent instructions for SLAVA_dev

Read `PROJECT_CONTEXT.md` completely before changing this repository. It is the
project handoff and contains the scientific objective, current state, data
contract, and non-negotiable decisions. Read `README.md` for the short project
overview and deployment commands.

Key invariants:

- The candidate inventory has 102 scene instances: 90 LIBERO + 12 SimplerEnv.
- One row means one reproducible `task × init state`, not one trajectory.
- LIBERO renders immediately after `set_init_state`; `settle_steps` must remain 0.
- SimplerEnv WidowX has no wrist camera; `wrist_rgb` must remain null there.
- Preserve human review fields when regenerating or merging collector outputs.
- Every inventory row must pass the strict canonical v1 schema in
  `schemas/task_inventory.schema.json`; do not add ad-hoc fields.
- Store repository-relative runtime paths plus pinned commits; do not introduce
  machine-specific `/workspace/...` paths into portable manifest fields.
- Do not start Russian instruction authoring before the scene inventory,
  screenshot review, object lexicon, and selected-task manifest are approved.
- LIBERO HDF5 demonstrations are not needed by the scene collectors, but
  `scripts/bootstrap.sh` downloads them for later model and trajectory work.
  Do not make inventory collection depend on those files.
