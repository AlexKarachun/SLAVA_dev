# Third-party skills

The following skill directories in `.claude/skills/` are copied from an
external project, not authored for SLAVA_dev:

- `brainstorming`, `dispatching-parallel-agents`, `executing-plans`,
  `finishing-a-development-branch`, `receiving-code-review`,
  `requesting-code-review`, `subagent-driven-development`,
  `systematic-debugging`, `test-driven-development`, `using-git-worktrees`,
  `using-superpowers`, `verification-before-completion`, `writing-plans`,
  `writing-skills`

Source: [obra/superpowers](https://github.com/obra/superpowers), a general
software-development-methodology skill library (TDD, systematic debugging,
plan-before-code, subagent-driven development, code review) — not specific
to this project. Copied at version `6.2.0`, commit `44c9b2d6e889982ac18c27d05a19fefe335194e1`
(2026-07-28), MIT license (`superpowers-LICENSE` in this directory,
copyright Jesse Vincent).

Copied in rather than left as a user-scope `claude plugin install` so they
travel with `git clone` onto other machines (e.g. a rented GPU server),
per the project's `slava-session-handoff` policy of committing everything
the next session needs. To pick up upstream updates, re-copy from a fresh
`claude plugin install superpowers@superpowers-dev` (or `git clone
https://github.com/obra/superpowers`) rather than hand-editing these files —
they're a vendored snapshot, not SLAVA_dev-authored content.
