# Agent instructions for SLAVA_dev

Read `README.md` completely before changing this repository. It is the project
handoff and contains the scientific objective, data contract, setup commands,
current state, and non-negotiable decisions.

Key invariants:

- The candidate inventory has 102 scene instances: 90 LIBERO + 12 SimplerEnv.
- One row means one reproducible `task × init state`, not one trajectory.
- LIBERO renders immediately after `set_init_state`; `settle_steps` must remain 0.
- SimplerEnv WidowX has no wrist camera; `wrist_rgb` must remain null there.
- Preserve human review fields when regenerating or merging collector outputs.
- Store repository-relative runtime paths plus pinned commits; do not introduce
  machine-specific `/workspace/...` paths into portable manifest fields.
- Do not start Russian instruction authoring before the scene inventory,
  screenshot review, object lexicon, and selected-task manifest are approved.
- Never download the large LIBERO HDF5 demonstrations for this inventory task;
  BDDL, fixed init states, assets, and the simulator are sufficient.
