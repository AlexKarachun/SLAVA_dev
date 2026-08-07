---
name: slava-token-len
description: Compute/interpret token_len + token_len_metadata in data/pilot_v0_release/frames_v0.jsonl using real tokenizers (not an estimate). Use when filling token_len for new/changed scenes, adding a tokenizer, or re-running after mt_russian/new variants get filled.
---

# SLAVA token_len

Source of truth: `task.md` QA item 14 ("Есть token_len для нужных
токенизаторов") — it names no shape and no tokenizer list. Both were decided
with the user in chat, not invented unilaterally, and are recorded in
`src/slava_inventory/frames_schema.py` (`TOKEN_LEN_TOKENIZERS`,
`TOKEN_LEN_CHECKPOINTS`) as the single source of truth going forward.

## Shape

`token_len`: `{tokenizer_key: {variant_key: int}}` — tokenizer-first, so one
script run can fill a whole tokenizer's column across all scenes.
`token_len_metadata`: `{tokenizer_key: hf_checkpoint_id}`, mirrors
`mt_metadata`'s null-until-filled pattern (null while `token_len == {}`,
required once non-empty). Both must be fully populated together — no partial
states — validated in `frames_schema.py`. `token_len` keys must match exactly
`TOKEN_LEN_TOKENIZERS`, and each tokenizer's inner dict must match exactly
the *currently filled* `variants.*` keys (so `axis_na` variants and the
still-null `mt_russian` are correctly absent, not zero).

## Tokenizer set (one key per backbone family in task.md's "Модели и среды" table)

Several table entries share a tokenizer — action-tuned checkpoints normally
reuse the base VLM's tokenizer unchanged, so they collapse to one key rather
than getting a separate one each:

| key | HF checkpoint | also covers |
| --- | --- | --- |
| `qwen3_vl` | `Qwen/Qwen3-VL-4B-Instruct` | GreenVLA (R0-base/R1-bridge) |
| `openvla_oft` | `moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10` | Prismatic |
| `paligemma` | `google/paligemma-3b-pt-224` | π0/π0.5 (lerobot) — same gemma tokenizer, confirmed via `paligemma_variant: gemma_2b` in `lerobot/pi0_libero_base`'s config.json |
| `smolvla` | `HuggingFaceTB/SmolVLM2-500M-Video-Instruct` | (lerobot's `smolvla_base` config.json names this exact checkpoint as `vlm_model_name`) |

The `moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10` choice
over the bare `openvla/openvla-7b` base matters: it's the author's official
OFT checkpoint fine-tuned on exactly the LIBERO spatial+object+goal suites
this pilot uses, not an arbitrary same-architecture stand-in.

`lerobot/pi0_*` and `lerobot/smolvla_*` model repos do **not** ship their own
`tokenizer.json` — they're policy checkpoints that reference an underlying
VLM by name in `config.json` (`paligemma_variant` / `vlm_model_name`). Don't
try `AutoTokenizer.from_pretrained("lerobot/pi0_libero_base")` directly, it
fails; resolve to the underlying VLM checkpoint first.

`google/paligemma-3b-pt-224` is a **gated** HF repo: needs an account that
accepted the license, `huggingface-cli login` (or `HF_TOKEN` env var) done
once per machine. `Qwen3-VL`, `openvla-7b-oft-*`, and `SmolVLM2` are not
gated.

## Environment

Project's system/notebook Python does not have `transformers` — deliberately
kept out of `requirements-notebook.txt` (this is a heavy, occasional-use
dependency, not core pipeline). A dedicated venv lives at
`.venv-tokenizers/` (gitignored, not `.venv-tokenizers` in the repo):

```bash
.venv-tokenizers/bin/python scripts/compute_token_len.py
python3 scripts/validate_frames.py   # ordinary system python is enough for this
```

Loading `moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10`'s
tokenizer prints a "custom code" warning because its `config.json` has an
`auto_map` pointing at OpenVLA's custom model class — **always pass
`trust_remote_code=False` explicitly** (`compute_token_len.py` does). The
tokenizer itself is a standard fast Llama-family tokenizer and loads fine
without executing any repo code; don't be tempted to pass
`trust_remote_code=True` to silence the warning, that would run arbitrary
code from a third-party repo for no benefit.

## When to re-run

`scripts/build_frames_v0.py` (the LLM-draft regenerator) always resets
`token_len`/`token_len_metadata` to `{}`/`null`, same as it does for
`mt_russian`/`mt_metadata` and `validation.native_check` — it's a draft
generator, not the final-state writer. Re-run `compute_token_len.py`
after: any `build_frames_v0.py` regeneration, any edit to `variants.*` text
(dashboard corrections change token counts), or once `mt_russian` gets a
real MT pass (it's excluded from `token_len` until then purely because it's
still `null`, not by design — rerun picks it up automatically once filled).

## Что ещё стирает повторный запуск `build_frames_v0.py` (уточнено 08.08.2026)

Список сбрасываемого шире, чем описано выше. Регенерация обнуляет также
**`ru_translit`, `ru_colloquial`, `ru_anaphora`** (сейчас заполнены для всех 20
сцен пилота) и возвращает `validation.native_check` в `"pending"`, а
`validation.author` — в строку LLM-черновика.

**Жёсткое правило: не запускать `build_frames_v0.py` поверх файла, прошедшего
native check, без предварительного дифа и слияния.** На 20 сценах потеря
восстанавливалась вручную; на 120–180 она означает выброшенный проход ручной
проверки.
