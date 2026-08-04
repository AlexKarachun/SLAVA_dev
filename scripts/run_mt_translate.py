#!/usr/bin/env python3
"""Fill variants.mt_russian (+ mt_metadata) in data/pilot_v0_release/frames_v0.jsonl with a
real machine-translation pass over variants.en_canonical -- task.md's
`mt_russian` rule:

    Сырой машинный перевод en_canonical.
    Не редактировать. Не улучшать. Не нормализовать.

Service: DeepL API (decided with the user after Google Translate access
didn't work out; task.md's own "Google Translate" is an example, not a
requirement). Raw response text is stored verbatim -- this script must never
rewrite, trim, or "clean up" what DeepL returns.

Requires a DeepL API key in the DEEPL_API_KEY environment variable (never
pass it on the command line or hardcode it -- it stays out of shell history
and this repo). The user's key is a fish universal variable (`set -Ux
DEEPL_API_KEY ...`), which only fish processes see -- run this script via
`fish -c`, not plain bash:

    fish -c '.venv-tokenizers/bin/python scripts/run_mt_translate.py'

Free-tier keys end in ':fx' and must hit api-free.deepl.com (not
api.deepl.com); this script always uses the free-tier host. DeepL requires
header-based auth (Authorization: DeepL-Auth-Key ...) -- the older
form-body auth_key parameter was deprecated November 2025 and returns a 403.
"""

from __future__ import annotations

import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_inventory.io_utils import load_jsonl, save_jsonl  # noqa: E402

DEFAULT_FRAMES = PROJECT_ROOT / "data" / "pilot_v0_release" / "frames_v0.jsonl"
DEEPL_URL = "https://api-free.deepl.com/v2/translate"
MT_SYSTEM = "DeepL API (api-free.deepl.com, EN->RU)"


def translate(text: str, api_key: str) -> str:
    data = urllib.parse.urlencode(
        {"text": text, "source_lang": "EN", "target_lang": "RU"}
    ).encode()
    req = urllib.request.Request(
        DEEPL_URL, data=data, headers={"Authorization": f"DeepL-Auth-Key {api_key}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"DeepL translate failed ({exc.code}): {exc.read().decode()}") from exc
    return payload["translations"][0]["text"]


def main() -> None:
    api_key = os.environ.get("DEEPL_API_KEY")
    if not api_key:
        raise SystemExit(
            "DEEPL_API_KEY is not set in this process's environment. "
            "If it's a fish universal variable, run this script via: "
            "fish -c '.venv-tokenizers/bin/python scripts/run_mt_translate.py'"
        )

    frames = load_jsonl(DEFAULT_FRAMES)
    date = datetime.date.today().isoformat()
    for frame in frames:
        en_canonical = frame["variants"]["en_canonical"]
        frame["variants"]["mt_russian"] = translate(en_canonical, api_key)
        frame["mt_metadata"] = {"system": MT_SYSTEM, "date": date}
        print(f"{frame['task_uid']}: {en_canonical!r} -> {frame['variants']['mt_russian']!r}")

    save_jsonl(frames, DEFAULT_FRAMES)
    print(f"Filled mt_russian for {len(frames)} records -> {DEFAULT_FRAMES}")
    print(
        "token_len is now stale (missing the mt_russian column) -- rerun "
        "compute_token_len.py before validate_frames.py."
    )


if __name__ == "__main__":
    main()
