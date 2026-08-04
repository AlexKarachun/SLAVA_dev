---
name: slava-mt-russian
description: Run or interpret the mt_russian machine-translation pass in data/frames_v0.jsonl (scripts/run_mt_translate.py) — MT provider auth (currently DeepL), raw/unedited output rule, how to switch provider, safe API-key handling, fish-vs-bash environment variable gotcha. Use when (re)running mt_russian, adding a scene, switching MT provider, or handling any new API credential in this project.
---

# SLAVA mt_russian

Source of truth: `task.md`'s `## mt_russian` section — "Сырой машинный
перевод `en_canonical`. Не редактировать. Не улучшать. Не нормализовать."
This is the one Tier-1 variant that must NOT be an LLM draft at all, not
even as a starting point — task.md's Google Translate example is just an
example provider, not a requirement (confirmed with the user after Google
Translate access didn't work out; DeepL is what's actually wired up now).

## Never touch the output text

Every other RU variant in `frames_v0.jsonl` is an LLM draft pending human
native check (`slava-instruction-variants`, `slava-native-check`).
`mt_russian` is the opposite: its entire value as a control condition is
that nobody — human or LLM — improves it. The pilot's 20 scenes already show
why this matters: DeepL's raw output is inconsistent between near-identical
source sentences (`"pick up the black bowl from table center..."` translated
as `"со средины стола"` for two init states and `"со середины стола"` for
the other two, same English string). That inconsistency is real signal about
what raw MT output looks like — don't normalize it away.

## Auth

`scripts/run_mt_translate.py` reads the key from the `DEEPL_API_KEY`
environment variable only — never accept it as a CLI arg or hardcode it
(keeps it out of shell history / `ps` / this repo). If a user pastes a key
directly in chat, treat it as compromised: tell them to rotate/revoke it
before using the new one, that's not optional.

**fish vs bash/zsh gotcha:** if the user's default shell is fish and they
set the key with `set -Ux DEEPL_API_KEY ...` (a fish *universal* variable),
it is invisible to bash/zsh child processes — including this harness's Bash
tool, which runs bash/zsh regardless of the user's login shell. `env | grep
DEEPL_API_KEY` in a plain Bash call will report NOT SET even though the
user's terminal has it. Check with `fish -c 'set -q DEEPL_API_KEY; and echo
SET'` instead, and run the actual script wrapped the same way:
`fish -c '.venv-tokenizers/bin/python scripts/run_mt_translate.py'`. Do not
ask the user to move the key into `~/.zshrc` just to work around this —
`fish -c` is the correct fix, not a shell migration.

**DeepL-specific:** free-tier keys end in `:fx` and only work against
`api-free.deepl.com` (not `api.deepl.com`, which is the paid-tier host and
returns 403 for a free key). DeepL deprecated form-body auth
(`auth_key=...` in the POST body) in November 2025 — it now requires header
auth (`Authorization: DeepL-Auth-Key <key>`) and returns a confusing 403
"Legacy authentication method" error otherwise, not an auth-failure-shaped
error. Both are handled in `run_mt_translate.py`; if DeepL changes their API
again, check the actual HTTPError body (`exc.read()`), not just the status
code — it's usually a clear JSON message.

## Switching MT provider

This has already happened once (task.md's own example was Google Translate;
the user couldn't get billing/access sorted, so we moved to DeepL — decided
explicitly with the user, not assumed). It will likely happen again (rate
limits, pricing, a provider not covering some language pair well). When it
does:

1. **Ask the user which service, don't default to task.md's example.**
   task.md names "Google Translate" only as an example of the shape
   (`mt_metadata: {system, date}`), not a requirement — say this explicitly
   when asking, so the user knows they're not locked into it.
2. Confirm how credentials will reach the script (see "API keys" below)
   *before* writing provider-specific code — auth mechanics vary a lot
   (DeepL: header `Authorization: DeepL-Auth-Key`, free vs pro host split;
   Google Cloud Translation: service-account JSON or API key + billing
   project; Yandex Translate: IAM token or API key + folder_id; a local
   NMT model needs no credential at all, just the `.venv-tokenizers`-style
   venv with `transformers`/`sentencepiece`, see `slava-token-len` for the
   pattern of running HF models locally).
3. Update `scripts/run_mt_translate.py`'s `translate()` function and
   `MT_SYSTEM` constant (goes verbatim into `mt_metadata.system` — make it
   specific enough to be reproducible, e.g. `"DeepL API
   (api-free.deepl.com, EN->RU)"`, not just `"DeepL"`).
4. Re-translate all scenes with the new provider — don't try to merge old
   and new provider output within one `frames_v0.jsonl`; `mt_metadata` is a
   single `{system, date}` per record, not per-provider-history.
5. Update this skill's provider-specific section (currently "DeepL-specific"
   below) to describe the new provider's quirks, and update
   `AGENTS.md`'s "Текущее состояние проекта" to say which provider is
   currently wired up.

## API keys and other secrets: general rule for this project

Not DeepL-specific — applies to any future credential (another MT provider,
a gated HF token, anything else this project ends up calling out to):

- **Never accept a secret as chat text.** If a user pastes one anyway
  (has happened once, with a DeepL key), don't use it as-is: tell them
  plainly it's now compromised (present in conversation history/logs) and
  ask them to rotate/revoke it in the provider's dashboard before using a
  replacement.
- **Always read secrets from an environment variable inside the script**
  (`os.environ["X_API_KEY"]`), never as a CLI argument (shows up in shell
  history and `ps`) and never hardcoded.
- **Verify presence, not value.** When checking a secret is set, print
  `SET`/`NOT SET`, never echo the actual value back into the conversation.
- Ask the user to persist the variable themselves in their shell config
  (or fish universal variable) and confirm when done — don't ask them to
  paste it, don't try to read shell history files to recover it.

## Downstream steps, in order

`mt_russian`/`mt_metadata` are only half the picture. After running
`run_mt_translate.py`:

1. `token_len` for the `mt_russian` variant is now missing (it didn't exist
   when `token_len` was last computed) — `validate_frames.py` will fail
   until you rerun `.venv-tokenizers/bin/python scripts/compute_token_len.py`
   (see `slava-token-len`). `run_mt_translate.py` deliberately does NOT call
   `validate_frames` itself for this reason — it would always fail on a
   fresh run.
2. `scripts/export_prompts.py`'s `PRIMARY_VARIANTS` list controls whether
   `mt_russian` prompts get exported — decided with the user to include it
   once real (it's its own row in task.md's "Table - behavioral pilot").
   Re-run `export_prompts.py` after a fresh MT pass to refresh
   `data/prompts_v0.jsonl`.
3. Only then `python3 scripts/validate_frames.py`.

`scripts/build_frames_v0.py` (the LLM-draft regenerator) always resets
`mt_russian`/`mt_metadata` to `null`, same as it does for `token_len` — it's
a draft generator, not the final-state writer. Re-running it means
re-running `run_mt_translate.py` too.
