---
name: slava-review-dashboards
description: Build the browser dashboards this project uses for every manual review pass (visibility, frames/native check, scene selection, auto-label validation) — the generate/apply script pair, what has to be on a card for a verdict to be possible, and the interaction rules that make 100+ cards bearable. Use when adding a new review pass or changing an existing dashboard.
---

# Review dashboards: the shape that works here

Every manual pass in this project has converged on the same shape, and the user
has asked for it by name more than once ("для ручной разметки предпочитаю
удобные визуальные интерфейсы: карточки, изображения, фильтры, счётчики"). Do
not invent a new interaction model per pass — extend this one.

Existing instances: `generate_visibility_review.py`, `generate_frames_review.py`,
`generate_screenshot_sheet.py`, `generate_selected_scenes.py`,
`generate_label_review.py`. Each has an `apply_*.py` twin.

## The script pair, not one script

```
scripts/generate_<pass>_review.py   →  data/<pass>_review.html   (regenerable, gitignored)
        ↓ human edits in the browser, exports JSON
scripts/apply_<pass>_review.py      →  writes verdicts into the data file
```

Why a pair and not an in-place editor: the HTML is a derived artifact that can
be regenerated at any time (it is in `.gitignore` for exactly this reason),
while the verdicts are data. Keeping the write path in a separate script means
a regenerated dashboard never silently loses a review, and the apply step can
validate and report before touching anything.

**The apply script must report agreement, not just write.** `apply_label_review.py`
prints agreement with the auto-labeller, a Wilson interval, and a confusion
table of disagreements — that is the actual deliverable of the pass; the JSONL
it writes is just where it lands.

## What has to be on a card

The rule that matters, learned on the auto-label pass: **a verdict that only
sees the conclusion cannot disagree with it.** Put the evidence the automation
used on the card, next to the automation's answer:

- the media itself, playing — for rollouts that means both cameras animating,
  because a frozen arm and an arm reaching-and-missing look identical in a
  first/last frame pair;
- the raw signals the labeller reduced to one word (first contact, gripper
  trace, everything touched, final relation) — not only its verdict;
- the instruction or the field being judged, verbatim;
- what the automation decided, clearly marked as such.

## Interaction rules (each of these was asked for)

- **One click per verdict.** Buttons, not `<select>` — a dropdown is open-then-pick,
  and over 100 cards that is 200 clicks for 100 decisions. Clicking the active
  choice clears it, so a misclick is fixable.
- **Keyboard for the common case.** `1`/`2` act on the card at the centre of the
  viewport, so a fast pass never touches the mouse.
- **Short human captions on controls, schema identifiers in the export.** The
  buttons say «не тот target»; the JSON carries `target_grounding_error`.
- **Autoplay only near the viewport** (`IntersectionObserver`), otherwise 100
  animated cards melt the tab.
- **Persist to `localStorage` on every change**, and keep the key and record
  shape stable across regenerations — the user reviews in one tab while the
  generator is edited in another, and a refresh must not lose progress. Always
  say this out loud when handing over a regenerated dashboard.
- **A visible counter and an explicit export button.** Progress in
  `localStorage` is not something an agent can read; the exported JSON is.

## Prefilling the automation's answer: allowed, but never as the "done" signal

The reviewer will ask for the automatic values to be pre-selected, and they are
right that it is faster — most cards are correct, so agreeing should cost one
keystroke, not a click per field. The trap is that a prefilled card looks
answered, which would silently turn "how often is the labeller wrong" into "how
often did the human bother to disagree".

The shape that keeps both: prefill the controls, but track an explicit
`reviewed` flag set only by a human action (Enter confirms as-is and scrolls to
the next card; any click or `1`/`2` also sets it). Only reviewed cards go into
the export, and each carries `kept_auto` so a later pass can separate "confirmed
identical" from "edited". Progress counters count reviewed, not filled.

State the anchoring cost out loud when handing the dashboard over — prefilling
does bias a reviewer toward agreement, and that limitation belongs in whatever
the pass reports, not just in the code.

## Frames: relative paths, not base64

Inlining ~24 frames × 100 episodes as data URIs produces a tens-of-megabytes
file that is slow to open and pointless: `rollouts/` sits on the same disk as
`data/`, and neither is in git, so there is nothing to make portable. Reference
`../rollouts/final/<pool>/episodes/<run_id>/camera/...` and keep the HTML at a
few hundred KB. (The exception is `docs/rollout_report.html`, which *is*
published — that one copies WebP clips next to itself via `--for-pages`.)

## Sampling: stratify, and say how

When a pass covers a sample rather than everything, stratify it and document the
rule in the module docstring. `generate_label_review.py` takes up to 30%
successes, then one episode per (model, failure label) cell, then fills
proportionally — because the first 100 rows of the annotations file are almost
entirely one model and one variant, and accuracy measured there would describe
that corner rather than the dataset. Fix the seed so the same sample comes back.
