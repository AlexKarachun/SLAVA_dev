#!/usr/bin/env python3
"""Fill token_len (+ token_len_metadata) in data/pilot_v0_release/frames_v0.jsonl with real
tokenizer counts -- task.md QA item 14 ("Есть token_len для нужных
токенизаторов").

Tokenizer set and shape were decided with the user (task.md doesn't specify
either): one HF checkpoint per backbone family in task.md's "Модели и среды"
table, collapsing entries that share a tokenizer --
  qwen3_vl     Qwen/Qwen3-VL-4B-Instruct                                    (also GreenVLA)
  openvla_oft  moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10  (also Prismatic)
  paligemma    google/paligemma-3b-pt-224                                   (also pi0/pi0.5, same gemma tokenizer)
  smolvla      HuggingFaceTB/SmolVLM2-500M-Video-Instruct
See src/slava_inventory/frames_schema.py's TOKEN_LEN_TOKENIZERS/
TOKEN_LEN_CHECKPOINTS for the authoritative mapping this script reads from.

token_len is computed for every currently-filled variants.* field (mt_russian
stays out until a real MT pass fills it -- rerun this script afterward to
pick it up). Counts use tokenizer(text)["input_ids"] with default special
tokens, no prompt template.

Requires transformers/huggingface_hub, deliberately NOT part of the project's
lightweight requirements -- run via the dedicated venv:

    .venv-tokenizers/bin/python scripts/compute_token_len.py

paligemma is a gated HF checkpoint; `huggingface-cli login` (or an
HF_TOKEN env var) with an account that accepted the PaliGemma license is
required once per machine.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_inventory.io_utils import load_jsonl, save_jsonl  # noqa: E402
from slava_inventory.frames_schema import (  # noqa: E402
    TOKEN_LEN_CHECKPOINTS,
    validate_frames,
)

DEFAULT_FRAMES = PROJECT_ROOT / "data" / "pilot_v0_release" / "frames_v0.jsonl"


def load_tokenizers() -> dict[str, object]:
    from transformers import AutoTokenizer

    tokenizers = {}
    for key, checkpoint in TOKEN_LEN_CHECKPOINTS.items():
        print(f"loading {key} ({checkpoint}) ...")
        tokenizers[key] = AutoTokenizer.from_pretrained(checkpoint, trust_remote_code=False)
    return tokenizers


def main() -> None:
    frames = load_jsonl(DEFAULT_FRAMES)
    tokenizers = load_tokenizers()

    for frame in frames:
        variants = frame["variants"]
        filled = {key: text for key, text in variants.items() if text is not None}
        frame["token_len"] = {
            tok_key: {var_key: len(tok(text)["input_ids"]) for var_key, text in filled.items()}
            for tok_key, tok in tokenizers.items()
        }
        frame["token_len_metadata"] = dict(TOKEN_LEN_CHECKPOINTS)

    validate_frames(frames)
    save_jsonl(frames, DEFAULT_FRAMES)
    print(f"Computed token_len for {len(frames)} records -> {DEFAULT_FRAMES}")


if __name__ == "__main__":
    main()
