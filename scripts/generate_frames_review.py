#!/usr/bin/env python3
"""Generate an editable HTML native-check dashboard for data/frames_v0.jsonl.

For each of the 20 selected scenes shows the renders, the grounded object
roles (target/reference/distractor/forbidden/background, editable), the
action/relation slots (editable), and every Tier-1 instruction variant with
editable text plus naturalness/equivalence/ambiguity (1-5) scores per
task.md's "Native check" section. Changes are staged client-side and
exported via "Download corrections" as JSON for
scripts/apply_frames_review.py.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "frames_v0.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "frames_review.html"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_inventory.io_utils import load_jsonl  # noqa: E402
from slava_inventory.frames_schema import (  # noqa: E402
    ACTION_VALUES,
    ROLE_VALUES,
    validate_frames,
)

RELATION_VALUES = ["on", "in", "in_front_of", "left_of", "right_of", "next_to", ""]
SCORED_VARIANTS = [
    "ru_literal",
    "ru_free_order",
    "ru_case_swap",
    "ru_negation",
    "code_switch",
    "ru_colloquial",
    "ru_anaphora",
]
# ru_translit is a mechanical, deterministic transliteration of ru_literal
# (one fixed scheme for the whole benchmark) -- shown for eyeballing like
# en_paraphrase, but not native-check scored: "naturalness" doesn't apply to
# a script transform, and equivalence/ambiguity are inherited from
# ru_literal by construction (see slava-instruction-variants).
TEXT_VARIANTS = ["en_paraphrase", "ru_translit", *SCORED_VARIANTS]
AXIS_NA_VARIANTS = {"ru_case_swap", "ru_negation", "ru_colloquial", "ru_anaphora"}


def image_source(relative_path: str | None, *, base_dir: Path, output_dir: Path) -> tuple[str | None, bool]:
    if not relative_path:
        return None, False
    image_path = base_dir / relative_path
    source = os.path.relpath(image_path, output_dir).replace(os.sep, "/")
    return source, image_path.is_file()


def render_object_row(obj: dict[str, Any], task_uid: str, forbidden_ids: list[str]) -> str:
    oid = str(obj["id"])
    role_buttons = "".join(
        f'<button type="button" class="rolebtn" data-role="{r}">{r}</button>' for r in sorted(ROLE_VALUES)
    )
    is_forbidden = oid in forbidden_ids
    forbidden_checkbox = (
        f'<label class="forbidden-toggle"><input type="checkbox" class="forbidden-check" '
        f'data-task="{html.escape(task_uid, quote=True)}" data-object="{html.escape(oid, quote=True)}"'
        f'{" checked" if is_forbidden else ""}> forbidden (ru_negation)</label>'
    )
    return f"""
    <tr class="obj-row" data-task="{html.escape(task_uid, quote=True)}" data-object="{html.escape(oid, quote=True)}"
        data-initial-role="{html.escape(obj['role'], quote=True)}">
      <td><code>{html.escape(oid)}</code></td>
      <td>{html.escape(obj['category_ru'])} · {html.escape(obj['color_ru'])}
        <br><small>{html.escape(obj['category_en'])} / {html.escape(obj['color_en'])}</small></td>
      <td><div class="role-group">{role_buttons}</div>{forbidden_checkbox}</td>
    </tr>
    """


def render_variant_block(frame: dict[str, Any], field: str) -> str:
    task_uid = str(frame["task_uid"])
    value = frame["variants"].get(field)
    axis_na = frame.get("axis_na", {})
    na_reason = axis_na.get(field, "")
    naturalness = frame["validation"]["naturalness"].get(field)
    equivalence = frame["validation"]["equivalence"].get(field)
    ambiguity = frame["validation"]["ambiguity"].get(field)

    can_be_na = field in AXIS_NA_VARIANTS
    na_toggle_html = ""
    if can_be_na:
        checked = " checked" if value is None else ""
        na_toggle_html = (
            f'<label class="na-toggle"><input type="checkbox" class="na-check" '
            f'data-task="{html.escape(task_uid, quote=True)}" data-field="{field}"{checked}> axis_na</label>'
        )

    score_html = ""
    if field in SCORED_VARIANTS:
        score_html = '<div class="scores">' + "".join(
            f'<label>{metric[:3]}<input type="number" min="1" max="5" class="score-input" '
            f'data-task="{html.escape(task_uid, quote=True)}" data-field="{field}" data-metric="{metric}" '
            f'value="{val if val is not None else ""}"></label>'
            for metric, val in (("naturalness", naturalness), ("equivalence", equivalence), ("ambiguity", ambiguity))
        ) + "</div>"

    return f"""
    <div class="variant-block" data-variant="{field}">
      <div class="variant-head"><b>{field}</b>{na_toggle_html}</div>
      <textarea class="variant-text" data-task="{html.escape(task_uid, quote=True)}" data-field="{field}"
        rows="2" {'disabled' if can_be_na and value is None else ''}>{html.escape(value or '')}</textarea>
      <textarea class="na-reason" data-task="{html.escape(task_uid, quote=True)}" data-field="{field}"
        rows="1" placeholder="причина axis_na"
        style="display:{'block' if can_be_na and value is None else 'none'}">{html.escape(na_reason)}</textarea>
      {score_html}
    </div>
    """


def render_scene(frame: dict[str, Any], base_dir: Path, output_dir: Path) -> str:
    uid = str(frame["task_uid"])
    images = frame["images"]
    agent_src, agent_ok = image_source(images.get("agentview_rgb"), base_dir=base_dir, output_dir=output_dir)
    wrist_src, wrist_ok = image_source(images.get("wrist_rgb"), base_dir=base_dir, output_dir=output_dir)

    def img_panel(src, ok, label, present):
        if src and ok:
            return f'<figure><figcaption>{label}</figcaption><a href="{html.escape(src, quote=True)}" target="_blank"><img src="{html.escape(src, quote=True)}" loading="lazy"></a></figure>'
        if not present:
            return f'<figure><figcaption>{label}</figcaption><div class="unavailable">N/A</div></figure>'
        return f'<figure><figcaption>{label}</figcaption><div class="missing">missing file</div></figure>'

    images_html = (
        '<div class="images">'
        + img_panel(agent_src, agent_ok, "Agent view", True)
        + img_panel(wrist_src, wrist_ok, "Wrist view", bool(images.get("wrist_rgb")))
        + "</div>"
    )

    forbidden_ids = frame["slots"]["forbidden"]
    objects_html = "".join(
        render_object_row(o, uid, forbidden_ids) for o in frame["scene"]["objects"]
    )
    action_options = "".join(
        f'<option value="{a}"{" selected" if a == frame["slots"]["action"] else ""}>{a}</option>'
        for a in sorted(ACTION_VALUES)
    )
    relation_options = "".join(
        f'<option value="{r}"{" selected" if (r or None) == frame["slots"]["relation"] else ""}>{r or "(none)"}</option>'
        for r in RELATION_VALUES
    )
    variants_html = "".join(render_variant_block(frame, f) for f in TEXT_VARIANTS)

    native_check = frame["validation"]["native_check"]
    native_options = "".join(
        f'<option value="{v}"{" selected" if v == native_check else ""}>{v}</option>'
        for v in ("pending", "passed", "failed")
    )
    notes = frame["validation"].get("notes", "")

    search_blob = " ".join(
        [uid, str(frame["canonical_en"])]
        + [str(frame["variants"].get(f) or "") for f in TEXT_VARIANTS]
    ).lower()

    return f"""
    <article class="scene" data-suite="{html.escape(frame['suite'], quote=True)}"
             data-native="{html.escape(native_check, quote=True)}"
             data-search="{html.escape(search_blob, quote=True)}">
      <div class="scene-head">
        <code class="scene-uid">{html.escape(uid)}</code>
        <span class="scene-canonical">{html.escape(str(frame['canonical_en']))}</span>
        <span class="scene-badges"><span class="badge badge-{native_check}">{native_check}</span></span>
      </div>
      <div class="scene-body">
        <div class="left-col">
          {images_html}
          <table class="objects">
            <colgroup><col class="col-id"><col class="col-lexicon"><col class="col-role"></colgroup>
            <thead><tr><th>id</th><th>lexicon</th><th>role</th></tr></thead>
            <tbody>{objects_html}</tbody></table>
          <div class="slot-row">
            <label>action <select class="slot-select" data-task="{html.escape(uid, quote=True)}" data-field="action">{action_options}</select></label>
            <label>relation <select class="slot-select" data-task="{html.escape(uid, quote=True)}" data-field="relation">{relation_options}</select></label>
          </div>
        </div>
        <div class="right-col">
          <div class="variants">{variants_html}</div>
          <div class="validation-row">
            <label>native_check <select class="native-select" data-task="{html.escape(uid, quote=True)}">{native_options}</select></label>
            <textarea class="notes-input" data-task="{html.escape(uid, quote=True)}" rows="2" placeholder="notes">{html.escape(notes)}</textarea>
          </div>
        </div>
      </div>
    </article>
    """


def generate_html(frames: list[dict[str, Any]], input_path: Path, output_path: Path) -> str:
    suites = sorted({str(f["suite"]) for f in frames})
    suite_options = "".join(f'<option value="{html.escape(s, quote=True)}">{html.escape(s)}</option>' for s in suites)
    cards = "".join(render_scene(f, input_path.parent, output_path.parent) for f in frames)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SLAVA frames v0.2 native check</title>
<style>
  :root {{
    color-scheme: light dark;
    --border:#d8dee8; --muted:#64748b; --bg:#f4f6f9; --text:#172033;
    --card-bg:#ffffff; --row-bg:#fafbfc; --th-bg:#f8fafc; --input-bg:#ffffff;
    --img-bg:#e2e8f0; --shadow:#1e293b12; --dirty-bg:#eff6ff; --dirty-border:#93c5fd;
    --header-bg:#172033; --header-fg:#ffffff; --header-chip:#1f2b44;
    --na-bg:#fffbeb; --uid-color:#334155;
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --border:#334155; --muted:#94a3b8; --bg:#0b1220; --text:#e2e8f0;
    --card-bg:#16213a; --row-bg:#111a2d; --th-bg:#1a2942; --input-bg:#0f172a;
    --img-bg:#334155; --shadow:#00000055; --dirty-bg:#173154; --dirty-border:#3b82f6;
    --header-bg:#0b1220; --header-fg:#e2e8f0; --header-chip:#1a2942;
    --na-bg:#3a2f13; --uid-color:#94a3b8;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --border:#334155; --muted:#94a3b8; --bg:#0b1220; --text:#e2e8f0;
      --card-bg:#16213a; --row-bg:#111a2d; --th-bg:#1a2942; --input-bg:#0f172a;
      --img-bg:#334155; --shadow:#00000055; --dirty-bg:#173154; --dirty-border:#3b82f6;
      --header-bg:#0b1220; --header-fg:#e2e8f0; --header-chip:#1a2942;
      --na-bg:#3a2f13; --uid-color:#94a3b8;
    }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text); font:14px/1.45 system-ui,sans-serif; }}
  header {{ position:sticky; top:0; z-index:5; display:flex; gap:10px; align-items:center; flex-wrap:wrap;
    padding:12px 20px; background:var(--header-bg); color:var(--header-fg); box-shadow:0 2px 8px #0003; }}
  header h1 {{ margin:0 auto 0 0; font-size:16px; }}
  header input, header select, header button {{ padding:8px 10px; border:0; border-radius:6px; font:inherit; }}
  header input, header select {{ background:var(--input-bg); color:var(--text); }}
  header button {{ background:#2563eb; color:white; cursor:pointer; font-weight:600; }}
  header button:hover {{ background:#1d4ed8; }}
  header button#theme-toggle {{ background:var(--header-chip); }}
  header button#theme-toggle:hover {{ background:#2c3f60; }}
  header label {{ display:flex; align-items:center; gap:6px; background:var(--header-chip); padding:6px 10px; border-radius:6px; }}
  main {{ max-width:1500px; margin:auto; padding:20px; }}
  .scene {{ margin:0 0 16px; padding:14px 16px; background:var(--card-bg); border:1px solid var(--border); border-radius:10px;
    box-shadow:0 2px 5px var(--shadow); }}
  .scene-head {{ display:flex; gap:12px; align-items:baseline; flex-wrap:wrap; margin-bottom:10px;
    padding-bottom:8px; border-bottom:1px solid var(--border); }}
  .scene-uid {{ font-size:12px; color:var(--uid-color); }}
  .scene-canonical {{ font-weight:600; }}
  .scene-badges {{ margin-left:auto; }}
  .badge {{ padding:2px 8px; border-radius:999px; font-size:11px; font-weight:700; }}
  .badge-pending {{ background:#fef3c7; color:#92400e; }}
  .badge-passed {{ background:#dcfce7; color:#166534; }}
  .badge-failed {{ background:#fee2e2; color:#991b1b; }}
  .scene-body {{ display:grid; grid-template-columns:minmax(320px,420px) minmax(0,1fr); gap:16px; }}
  .images {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; }}
  figure {{ margin:0; min-width:0; }} figcaption {{ margin-bottom:4px; font-weight:700; font-size:12px; color:var(--muted); }}
  img {{ display:block; width:100%; border-radius:6px; background:var(--img-bg); }}
  .missing, .unavailable {{ display:grid; place-items:center; min-height:100px; border:1px dashed var(--border);
    border-radius:6px; color:var(--muted); font-size:12px; }}
  table.objects {{ width:100%; table-layout:fixed; border-collapse:collapse; margin-top:10px; font-size:12px; }}
  table.objects th, table.objects td {{ padding:5px 6px; border:1px solid var(--border); text-align:left;
    vertical-align:top; overflow-wrap:anywhere; }}
  table.objects th {{ background:var(--th-bg); }}
  table.objects col.col-id {{ width:34%; }}
  table.objects col.col-lexicon {{ width:28%; }}
  table.objects col.col-role {{ width:38%; }}
  .role-group {{ display:flex; gap:3px; flex-wrap:wrap; }}
  .forbidden-toggle {{ display:flex; align-items:center; gap:4px; margin-top:5px; font-size:10px; color:#991b1b; }}
  .rolebtn {{ padding:3px 5px; font-size:10px; border:1px solid var(--border); border-radius:4px; background:var(--th-bg); color:var(--text); cursor:pointer; white-space:nowrap; }}
  .rolebtn.active {{ background:#2563eb; color:white; border-color:#2563eb; }}
  .slot-row {{ display:flex; gap:12px; margin-top:10px; font-size:12px; }}
  .slot-row select {{ margin-left:4px; }}
  .variant-block {{ border:1px solid var(--border); border-radius:8px; padding:8px 10px; margin-bottom:8px; background:var(--row-bg); }}
  .variant-block.dirty {{ background:var(--dirty-bg); border-color:var(--dirty-border); }}
  .variant-head {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:5px; font-size:12px; }}
  .na-toggle {{ font-size:11px; color:var(--muted); display:flex; gap:4px; align-items:center; }}
  textarea, select, input {{ background:var(--input-bg); color:var(--text); }}
  textarea {{ width:100%; font:inherit; border:1px solid var(--border); border-radius:5px; padding:5px 7px; resize:vertical; }}
  textarea.na-reason {{ margin-top:5px; background:var(--na-bg); }}
  .scores {{ display:flex; gap:10px; margin-top:5px; font-size:11px; color:var(--muted); }}
  .scores input {{ width:44px; margin-left:3px; padding:2px 4px; border:1px solid var(--border); border-radius:4px; }}
  .validation-row {{ display:flex; gap:10px; align-items:flex-start; margin-top:6px; font-size:12px; }}
  .validation-row select {{ margin-left:4px; }}
  .notes-input {{ flex:1; }}
  .hidden {{ display:none; }}
  #status {{ position:fixed; right:16px; bottom:16px; background:var(--header-bg); color:var(--header-fg); padding:10px 14px;
    border-radius:8px; font-size:13px; box-shadow:0 4px 12px #0004; z-index:10; }}
  @media (max-width:1000px) {{ .scene-body {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<header>
  <h1>SLAVA frames v0.2 · native check · {len(frames)} scenes</h1>
  <input id="search" type="search" placeholder="Search task_uid / instruction / text…">
  <select id="suite"><option value="">All suites</option>{suite_options}</select>
  <select id="native-filter">
    <option value="">any native_check</option>
    <option value="pending">pending</option>
    <option value="passed">passed</option>
    <option value="failed">failed</option>
  </select>
  <button id="download-btn">Download corrections</button>
  <button id="theme-toggle" type="button" title="Toggle dark/light theme">🌙 Dark</button>
  <span id="shown"></span>
</header>
<main>{cards}</main>
<div id="status">0 changes staged</div>
<script>
// --- theme toggle ---
(function() {{
  const STORAGE_KEY = 'slava-frames-theme';
  const root = document.documentElement;
  const btn = document.querySelector('#theme-toggle');
  function apply(theme) {{
    root.dataset.theme = theme;
    btn.textContent = theme === 'dark' ? '☀️ Light' : '🌙 Dark';
  }}
  const saved = localStorage.getItem(STORAGE_KEY);
  const systemDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  apply(saved || (systemDark ? 'dark' : 'light'));
  btn.addEventListener('click', () => {{
    const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    apply(next);
    localStorage.setItem(STORAGE_KEY, next);
  }});
}})();

const cards = [...document.querySelectorAll('.scene')];
const search = document.querySelector('#search');
const suite = document.querySelector('#suite');
const nativeFilter = document.querySelector('#native-filter');
const shown = document.querySelector('#shown');
const statusEl = document.querySelector('#status');
const changes = new Map(); // key -> op object

function applyFilters() {{
  const q = search.value.trim().toLowerCase();
  let count = 0;
  for (const card of cards) {{
    const visible = (!q || card.dataset.search.includes(q)) &&
      (!suite.value || card.dataset.suite === suite.value) &&
      (!nativeFilter.value || card.dataset.native === nativeFilter.value);
    card.classList.toggle('hidden', !visible);
    if (visible) count++;
  }}
  shown.textContent = count + ' shown';
}}
[search, suite, nativeFilter].forEach(el => el.addEventListener('input', applyFilters));
applyFilters();

function stage(key, op) {{
  changes.set(key, op);
  statusEl.textContent = changes.size + ' changes staged';
}}

// --- object role buttons ---
document.querySelectorAll('.obj-row').forEach(row => {{
  const task = row.dataset.task, object = row.dataset.object, initial = row.dataset.initialRole;
  const buttons = row.querySelectorAll('.rolebtn');
  buttons.forEach(btn => btn.classList.toggle('active', btn.dataset.role === initial));
  buttons.forEach(btn => btn.addEventListener('click', () => {{
    buttons.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const key = `role\\u241f${{task}}\\u241f${{object}}`;
    if (btn.dataset.role === initial) {{ changes.delete(key); }}
    else {{ stage(key, {{op: 'set_role', task_uid: task, object_id: object, value: btn.dataset.role}}); }}
  }}));
}});

// --- forbidden (ru_negation target) checkbox, independent from role ---
document.querySelectorAll('.forbidden-check').forEach(cb => {{
  const initial = cb.checked;
  cb.addEventListener('change', () => {{
    const task = cb.dataset.task, object = cb.dataset.object;
    const key = `forbidden\\u241f${{task}}\\u241f${{object}}`;
    if (cb.checked === initial) {{ changes.delete(key); }}
    else {{ stage(key, {{op: 'toggle_forbidden', task_uid: task, object_id: object, value: cb.checked}}); }}
  }});
}});

// --- action / relation selects ---
document.querySelectorAll('.slot-select').forEach(sel => {{
  const initial = sel.value;
  sel.addEventListener('change', () => {{
    const task = sel.dataset.task, field = sel.dataset.field;
    const key = `slot\\u241f${{task}}\\u241f${{field}}`;
    const value = sel.value === '' ? null : sel.value;
    if (sel.value === initial) {{ changes.delete(key); }}
    else {{ stage(key, {{op: 'set_slot', task_uid: task, field, value}}); }}
  }});
}});

// --- variant text + axis_na ---
document.querySelectorAll('.variant-text').forEach(ta => {{
  const initial = ta.value;
  ta.addEventListener('input', () => {{
    const task = ta.dataset.task, field = ta.dataset.field;
    const key = `variant\\u241f${{task}}\\u241f${{field}}`;
    if (ta.value === initial) {{ changes.delete(key); }}
    else {{ stage(key, {{op: 'set_variant', task_uid: task, field, value: ta.value}}); ta.closest('.variant-block').classList.add('dirty'); }}
  }});
}});
document.querySelectorAll('.na-check').forEach(cb => {{
  cb.addEventListener('change', () => {{
    const task = cb.dataset.task, field = cb.dataset.field;
    const block = cb.closest('.variant-block');
    const ta = block.querySelector('.variant-text');
    const reasonTa = block.querySelector('.na-reason');
    ta.disabled = cb.checked;
    reasonTa.style.display = cb.checked ? 'block' : 'none';
    const key = `axisna\\u241f${{task}}\\u241f${{field}}`;
    stage(key, {{op: 'set_axis_na', task_uid: task, field, enabled: cb.checked, reason: reasonTa.value, text: ta.value}});
    block.classList.add('dirty');
  }});
}});
document.querySelectorAll('.na-reason').forEach(ta => {{
  ta.addEventListener('input', () => {{
    const task = ta.dataset.task, field = ta.dataset.field;
    const key = `axisna\\u241f${{task}}\\u241f${{field}}`;
    const cb = ta.closest('.variant-block').querySelector('.na-check');
    stage(key, {{op: 'set_axis_na', task_uid: task, field, enabled: cb.checked, reason: ta.value, text: ta.closest('.variant-block').querySelector('.variant-text').value}});
    ta.closest('.variant-block').classList.add('dirty');
  }});
}});

// --- scores ---
document.querySelectorAll('.score-input').forEach(inp => {{
  const initial = inp.value;
  inp.addEventListener('input', () => {{
    const task = inp.dataset.task, field = inp.dataset.field, metric = inp.dataset.metric;
    const key = `score\\u241f${{task}}\\u241f${{field}}\\u241f${{metric}}`;
    if (inp.value === initial) {{ changes.delete(key); }}
    else {{ stage(key, {{op: 'set_score', task_uid: task, field, metric, value: inp.value === '' ? null : Number(inp.value)}}); inp.closest('.variant-block').classList.add('dirty'); }}
  }});
}});

// --- native_check + notes ---
document.querySelectorAll('.native-select').forEach(sel => {{
  const initial = sel.value;
  sel.addEventListener('change', () => {{
    const task = sel.dataset.task;
    const key = `validation\\u241f${{task}}\\u241fnative_check`;
    if (sel.value === initial) {{ changes.delete(key); }}
    else {{ stage(key, {{op: 'set_validation', task_uid: task, field: 'native_check', value: sel.value}}); }}
  }});
}});
document.querySelectorAll('.notes-input').forEach(ta => {{
  const initial = ta.value;
  ta.addEventListener('input', () => {{
    const task = ta.dataset.task;
    const key = `validation\\u241f${{task}}\\u241fnotes`;
    if (ta.value === initial) {{ changes.delete(key); }}
    else {{ stage(key, {{op: 'set_validation', task_uid: task, field: 'notes', value: ta.value}}); }}
  }});
}});

document.querySelector('#download-btn').addEventListener('click', () => {{
  const out = [...changes.values()];
  const blob = new Blob([JSON.stringify(out, null, 1)], {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'frames_review_corrections.json';
  a.click();
}});
</script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input.resolve()
    output_path = args.output.resolve()
    frames = load_jsonl(input_path)
    validate_frames(frames)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = generate_html(frames, input_path, output_path)
    output_path.write_text(document, encoding="utf-8")
    print(f"Wrote {len(frames)} scenes to {output_path}")


if __name__ == "__main__":
    main()
