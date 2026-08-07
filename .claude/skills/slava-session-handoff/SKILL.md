---
name: slava-session-handoff
description: Close out a SLAVA_dev session and prepare a clean start for the next chat — reconcile AGENTS.md's "Текущее состояние проекта" against actual repo/data state, sweep ALL existing skills (not just obviously-related ones) for staleness given this session's changes, update or add skills for new repeatable work, keep the skills list in sync, write a self-contained starter prompt and hand it to the user directly, and commit+push everything the next session needs (the next session may start from a fresh clone on different hardware in either direction — a GPU server, a local laptop, whatever's next). Use when the user says they're moving to a new chat, a new machine, wants a handoff, or asks to update AGENTS.md/skills at the end of a session.
---

TRIGGER — load this skill whenever the user signals the session is ending,
even briefly/informally, not just on an explicit "update AGENTS.md" ask:
"заканчиваем", "закругляемся", "на сегодня всё", "давай на этом закончим",
"переходим в новый чат", "wrapping up", "let's end here", "starting a new
chat next", or any direct request for a handoff/starter-prompt/status
update. If the phrase is ambiguous between "stop working right now, no
wrap-up needed" and "close out properly" (bare "заканчиваем" can go either
way), ask which one before silently picking one.

# SLAVA session handoff

`AGENTS.md` says outright: it replaces `expl.md` (a deleted snapshot file)
specifically so a new chat can start from `AGENTS.md` alone, with no need to
re-read prior conversation history. That only holds if the handoff is done
properly at the end of a session — this skill is the checklist for that.

## 1. Reconcile "Текущее состояние проекта" against reality, not against what it said before

**First, know what that section is for (changed 2026-08-05, when the repo was
prepared for handoff to a researcher).** It is a *snapshot* — where the
project stands, what is open, what needs the user — and it is meant to stay
short enough that an agent actually reads it before working. It is **not** a
session diary. The chronology of findings ("on date X we tried Y, it failed
because Z") belongs in the per-topic `slava-*` skills, together with the
evidence. The section previously was a running log and reached 1300+ lines,
at which point nobody could read it in full; it was cut back to ~100. Do not
regrow it. When you finish a session: put the *finding* in the right skill,
and touch this section only if the project's status or open questions
actually changed.

Don't just append a new paragraph describing this session's changes on top
of what's already there — that's how the section grows stale contradictions
(this happened once: a `token_len` paragraph from an earlier session still
said "`token_len` пустой `{}` везде, ждёт реальных токенизаторов" several
paragraphs above a *newer* paragraph correctly saying token_len was now
real; a stale `mt_russian: null` claim survived similarly). Concretely:

- Grep the status section for every field/script this session touched
  (`grep -n "token_len\|mt_russian\|export_prompts" AGENTS.md`) and check
  each hit is still true, not just the paragraph you added — a
  straightforward grep beats rereading four screens of prose. Particular
  contradictions to check for after data-pipeline work: "ещё не
  существует" / "заблокирован" / "null" claims about something you just
  built or filled.
- If an old paragraph is now superseded, rewrite or delete it in place —
  don't leave both the old and new claims in the file for a future agent to
  have to arbitrate.
- Re-run whatever validator matters (here: `python3 scripts/validate_frames.py`)
  after any edit that could have drifted from the data, even doc-only edits,
  as a sanity check that the file and the data still agree.

## 2. Sweep ALL existing skills for staleness, not just the ones the session touched

This is easy to skip because it doesn't feel like "this session's work" —
but a skill can go stale from a change made somewhere else entirely. If this
session changed a field name, a script's behavior, a file path, a decided
default, or a data-contract shape that an *unrelated* skill mentions or
assumes, that skill is now wrong even though nobody was thinking about it.
Concretely: `ls .claude/skills/`, then for each skill not already touched
this session, grep it for the names of whatever changed
(`grep -rn "<field or script name>" .claude/skills/`) and read any hits in
context — a passing mention that's now inaccurate is worth a one-line fix
even in a skill that isn't "about" this session's topic.

## 3. Update or add skills for anything genuinely repeatable

Not every session needs a new skill. The bar (same one `AGENTS.md` states
for quota mnemonics): did this session do a nontrivial thing that will need
doing again, where getting it wrong once already cost real back-and-forth?
Signals from this project's history: a provider integration with
non-obvious auth (`slava-mt-russian`), an environment-setup dependency that
isn't part of the default install (`slava-token-len`'s `.venv-tokenizers`),
a data-contract decision task.md left unspecified that got resolved with
the user (both of the above record their shape decisions). A one-off
scene-specific fix belongs in that record's `notes` field, not a skill.

**Sweep for what went right, not only for what broke.** The bar is the same
(will this need doing again?), but the signals are different and easy to miss
because nothing failed: something the user praised or told you to keep doing,
a trick that visibly saved time or removed a risk, and any explanation you
had to give the user more than once. All three are repeatable knowledge that
otherwise dies with the chat — a later session then reinvents the approach,
usually worse. Record the *why*, not the compliment: "the reviewer needs both
cameras playing plus the evidence the labeller used, or they cannot disagree
with it" is reusable; "the user liked the dashboard" is not.

When updating an existing skill instead of writing a new one: prefer
extending it over creating a near-duplicate. `slava-mt-russian` started as
"how to run the DeepL pass" and grew a "how to switch provider" section
instead of spawning a separate `slava-mt-provider-switching` skill, because
both are about the same `mt_russian` field and the same script entry point.
If a skill's frontmatter `description` no longer covers what the file
actually contains after an edit (a common miss — the body grows, the
one-line summary doesn't), update the description too; it's the only part
of the skill visible before it's loaded, and a stale description means the
next session won't know to load it for the new content.

## 4. Keep the skills list in AGENTS.md in sync with `.claude/skills/`

`AGENTS.md`'s "Agent skills для повторяемых задач разметки" section lists
every skill with a one-line summary of what it's for. `ls .claude/skills/`
and diff that against the list by hand — a new skill file with no AGENTS.md
entry is invisible to a future agent that only reads AGENTS.md (per this
skill's own premise in the header above), and a stale entry describing a
skill that no longer matches its file is actively misleading.

## 5. Write a self-contained starter prompt for the next chat

The next chat has zero memory of this conversation — the prompt is the only
thing it gets beyond `AGENTS.md` itself. Structure that has worked in this
project:

1. Explicit read order: `AGENTS.md` in full, then `README.md`, then the
   specific `task.md` section(s) relevant to what's left (not the whole
   file — point at section headers), then `git status`.
2. One line stating what's already done and confirmed, with an explicit
   "don't reopen this without a concrete reason" — point at which skills
   hold the reasoning, don't re-paste it into the prompt.
3. The actual remaining work, phrased as open questions to raise with the
   user before acting where a decision is genuinely the user's to make —
   not as a to-do list the agent should just execute. If a session ended
   with unresolved questions (a scale direction, a stray artifact in an
   external file, a soft non-blocking issue), list them explicitly by name
   — they're easy to lose track of if left implicit in "see AGENTS.md".
4. An explicit boundary on scope: what NOT to start without the user asking
   (e.g. "don't scale to 120–180-task full-sets", "don't tag the freeze without
   explicit go-ahead") — carried over from the current session's own scope
   boundary, not invented fresh.
5. Any live operational gotcha that would otherwise cost a repeat
   back-and-forth in the new chat (e.g. this project's fish-vs-bash
   environment variable visibility issue, or "never accept secrets as chat
   text") — one line, pointing at the skill that has the full detail.

Keep it as dense as the examples already used in this project's handoffs —
a few paragraphs, not a full re-derivation of the project. The next agent
can and should read `AGENTS.md` itself for anything that doesn't change
what it should ask or do next.

## 6. Final end-to-end sanity pass before ending

Do this last, after every other step above, not just after the last edit
you happened to make:

- Reread every file you touched this handoff (`AGENTS.md`, any edited
  skills, the starter prompt) start to finish, not diff-by-diff. Diffs show
  what changed but not whether the *surrounding* text still reads
  coherently — this is how the `token_len`/`mt_russian` contradiction
  described in step 1 was actually caught, not by reviewing the edit that
  introduced it.
- Re-run the project's validator(s) one more time after all doc edits are
  in (`python3 scripts/validate_frames.py` here) — cheap insurance that a
  doc-only pass didn't somehow coincide with a data edit going stale.
- Run `git status --short` and check it actually matches what the starter
  prompt / AGENTS.md's "Git" paragraph claims is untracked — a file added
  mid-session is easy to forget to mention.

## 7. Commit and push everything needed to continue on another machine

This overrides `AGENTS.md`'s general "only commit on explicit instruction"
rule specifically for the handoff step: the user's standing instruction is
that a session close commits and pushes whatever the next session needs,
because that next session may start from a fresh `git clone` on a different
machine (e.g. a rented GPU server) with no access to this conversation or
this working tree. A handoff that leaves things uncommitted defeats its own
purpose — the starter prompt tells the next agent to read `AGENTS.md`, but
that only works if `AGENTS.md` (and the skills it points at) are actually on
the remote.

Concretely, at the end of every handoff:

- `git status --short` — everything modified/untracked that represents
  finished, already-discussed-with-the-user work (this handoff's `AGENTS.md`
  and skill edits at minimum, but also any other session output the user
  already approved the substance of during the conversation) gets staged and
  committed. Don't re-litigate content the user already signed off on earlier
  in the session just because it's now commit time.
- Exclude what's deliberately not meant for git: check `AGENTS.md`'s own
  "Git" paragraph and any `.gitignore` for things like
  `data/HOPE_3D_models/` (large, intentionally untracked) or
  `.venv-tokenizers/` (gitignored on creation) — don't sweep those in with a
  broad `git add -A`.
- If something in the diff is genuinely new/unapproved — work in progress
  the user hasn't actually confirmed, not just "hasn't been asked about
  committing specifically" — flag it and ask rather than silently including
  or silently excluding it. The bar is "did the user already approve this
  content", not "did they say the word commit".
- Commit with a message describing what the handoff covers, then `git push`
  (branch and any new tags, e.g. a freeze tag created earlier in the
  session) to `origin`. A commit sitting local-only is just as unreachable
  from a fresh clone as an uncommitted change.
- Report in the handoff status what got pushed (commit hash, branch, tags)
  and confirm `git status --short` is clean afterward (modulo the
  deliberately-untracked exceptions above) — don't leave the user to
  discover mid-server-setup that something didn't make it.
- If this session also produced large data the next session needs but that
  deliberately isn't going into git (raw rollout output, generated datasets,
  anything the "exclude what's deliberately not meant for git" bullet above
  applies to), don't just leave it implicit that "it's on this machine
  somewhere" — package it (a zip is the default unless the user asks for
  something else) and give the exact retrieval command (`scp`/`rsync` over
  the machine's own SSH port is usually simplest for a single user — see
  this image's `vast_agents`/README for the concrete host/port on a Vast.ai
  box). State plainly whether the machine's disk is ephemeral (check
  whatever this environment's equivalent of `workspace_is_volume` is) — if
  it is, the human needs to know the data disappears on
  stop/recycle/destroy, not just that it's "also available as a zip."

## 8. Deliver the starter prompt directly to the user, and call out environment differences

The starter prompt from step 5 is not a filing task — the user has to
physically carry it into the next session themselves (paste it into a new
chat window, hand it to a different tool, carry it to different hardware
entirely). Always put the final version directly in the chat response as a
copy-pasteable block, in addition to anything durable like AGENTS.md — a
prompt that exists only inside a commit is invisible to someone about to
open a blank chat with no history.

Before finalizing it, check whether the *environment* the next session will
run in differs from this one — not just the project stage. Concrete signals:
different OS/hardware (a rented GPU server vs. a local laptop, x86 vs. Apple
silicon), a capability this session relied on that won't exist there (CUDA,
a specific conda env, a background service left running), or a different
starting filesystem state (fresh `git clone` vs. this exact working tree,
data that lives only on this machine's disk and has to be fetched
separately). If any of these differ, say so explicitly and near the top of
the prompt, in concrete terms — "this part of the pipeline needs CUDA and
won't run on your machine" beats leaving the new agent to discover it by
trying and failing. A prompt that silently assumes environment parity with
the session that wrote it wastes the new agent's first real stretch of work
rediscovering the difference the hard way.
