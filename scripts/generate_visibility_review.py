#!/usr/bin/env python3
"""Generate an editable HTML visibility-review dashboard from task_inventory.jsonl.

Shows every object of every scene with its current visible_agentview /
visible_wrist status next to the agentview/wrist renders. Values can be
changed in the browser; changed cells are tracked client-side and can be
exported as a corrections file for scripts/apply_visibility_review.py.

Optionally overlays low-confidence AI suggestions (produced by a batch
visibility-review pass) as clickable hints, without ever silently writing
them into task_inventory.jsonl.
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
DEFAULT_INPUT = PROJECT_ROOT / "data" / "task_inventory.jsonl"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_inventory.io_utils import load_jsonl  # noqa: E402
from slava_inventory.schema import validate_inventory  # noqa: E402


def image_source(relative_path: str | None, *, inventory_dir: Path, output_dir: Path) -> tuple[str | None, bool]:
    if not relative_path:
        return None, False
    image_path = inventory_dir / relative_path
    source = os.path.relpath(image_path, output_dir).replace(os.sep, "/")
    return source, image_path.is_file()


def load_hints(path: Path | None) -> dict[str, dict[str, Any]]:
    """Return {(task_uid, sim_handle, field): {suggested_value, note}}."""
    hints: dict[str, dict[str, Any]] = {}
    if not path or not path.is_file():
        return hints
    for entry in json.loads(path.read_text()):
        key = f"{entry['task_uid']}␟{entry['sim_handle']}␟{entry['field']}"
        hints[key] = {"suggested_value": entry.get("suggested_value"), "note": entry.get("note", "")}
    return hints


def render_scene(record: dict[str, Any], inventory_dir: Path, output_dir: Path, hints: dict[str, Any]) -> str:
    uid = str(record["task_uid"])
    suite = str(record["suite"])
    images = record.get("images") or {}
    wrist_present = bool(images.get("wrist_rgb"))
    agent_src, agent_ok = image_source(images.get("agentview_rgb"), inventory_dir=inventory_dir, output_dir=output_dir)
    wrist_src, wrist_ok = image_source(images.get("wrist_rgb"), inventory_dir=inventory_dir, output_dir=output_dir)

    def img_panel(src, ok, label):
        if src and ok:
            return f'<figure><figcaption>{label}</figcaption><a href="{html.escape(src, quote=True)}" target="_blank"><img src="{html.escape(src, quote=True)}" loading="lazy"></a></figure>'
        if label == "Wrist view" and not wrist_present:
            return f'<figure><figcaption>{label}</figcaption><div class="unavailable">N/A (no wrist camera)</div></figure>'
        return f'<figure><figcaption>{label}</figcaption><div class="missing">missing file</div></figure>'

    images_html = '<div class="images">' + img_panel(agent_src, agent_ok, "Agent view") + img_panel(wrist_src, wrist_ok, "Wrist view") + "</div>"

    rows = []
    scene_pending = 0
    scene_hinted = 0
    for obj in record.get("objects_raw") or []:
        handle = str(obj.get("sim_handle"))
        raw_name = str(obj.get("raw_name") or "")
        cells = []
        for field, cam_present, label in (
            ("visible_agentview", True, "agent"),
            ("visible_wrist", wrist_present, "wrist"),
        ):
            value = obj.get(field)
            hint_key = f"{uid}␟{handle}␟{field}"
            hint = hints.get(hint_key)
            if not cam_present:
                cells.append(f'<td class="vis-cell na">N/A</td>')
                continue
            if value is None:
                scene_pending += 1
            if hint:
                scene_hinted += 1
            hint_html = ""
            if hint:
                sv = hint["suggested_value"]
                sv_label = {"true": "visible", "false": "not visible", "visible_partial": "partial"}.get(json.dumps(sv), str(sv))
                note = html.escape(str(hint.get("note") or ""))
                hint_html = (
                    f'<div class="hint" title="{note}">AI guess: <b>{html.escape(sv_label)}</b>'
                    f' <button type="button" class="hint-apply" data-value=\'{json.dumps(sv)}\'>use</button></div>'
                )
            cells.append(
                f'<td class="vis-cell" data-task="{html.escape(uid, quote=True)}" '
                f'data-handle="{html.escape(handle, quote=True)}" data-field="{field}">'
                f'<div class="toggle-group" data-initial=\'{json.dumps(value)}\'>'
                f'<button type="button" class="vbtn v-unknown" data-value="null">?</button>'
                f'<button type="button" class="vbtn v-true" data-value="true">visible</button>'
                f'<button type="button" class="vbtn v-partial" data-value="&quot;visible_partial&quot;">partial</button>'
                f'<button type="button" class="vbtn v-false" data-value="false">not visible</button>'
                f'</div>{hint_html}</td>'
            )
        rows.append(
            f'<tr><td><code>{html.escape(handle)}</code><br><small>{html.escape(raw_name)}</small></td>'
            + "".join(cells)
            + "</tr>"
        )

    table = (
        '<table class="objects"><thead><tr><th>object</th><th>agent view</th><th>wrist view</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )
    return f"""
    <article class="scene" data-suite="{html.escape(suite, quote=True)}"
             data-pending="{scene_pending}" data-hinted="{scene_hinted}"
             data-search="{html.escape((uid + ' ' + str(record.get('canonical_en') or '')).lower(), quote=True)}">
      <div class="scene-head">
        <code class="scene-uid">{html.escape(uid)}</code>
        <span class="scene-canonical">{html.escape(str(record.get('canonical_en') or ''))}</span>
        <span class="scene-badges">
          {'<span class="badge badge-pending">' + str(scene_pending) + ' pending</span>' if scene_pending else ''}
          {'<span class="badge badge-hint">' + str(scene_hinted) + ' AI hints</span>' if scene_hinted else ''}
        </span>
      </div>
      <div class="scene-body">
        {images_html}
        <div class="table-wrap">{table}</div>
      </div>
    </article>
    """


def generate_html(records: list[dict[str, Any]], input_path: Path, output_path: Path, hints: dict[str, Any]) -> str:
    suites = sorted({str(r["suite"]) for r in records})
    cards = "".join(render_scene(r, input_path.parent, output_path.parent, hints) for r in records)
    suite_options = "".join(f'<option value="{html.escape(s, quote=True)}">{html.escape(s)}</option>' for s in suites)
    total_objects = sum(len(r.get("objects_raw") or []) for r in records)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SLAVA visibility review</title>
<style>
  :root {{ color-scheme: light; --border:#d8dee8; --muted:#64748b; --bg:#f4f6f9; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:#172033; font:14px/1.45 system-ui,sans-serif; }}
  header {{ position:sticky; top:0; z-index:5; display:flex; gap:10px; align-items:center; flex-wrap:wrap;
    padding:12px 20px; background:#172033; color:white; box-shadow:0 2px 8px #0003; }}
  header h1 {{ margin:0 auto 0 0; font-size:17px; }}
  header input, header select, header button {{ padding:8px 10px; border:0; border-radius:6px; font:inherit; }}
  header button {{ background:#2563eb; color:white; cursor:pointer; font-weight:600; }}
  header button:hover {{ background:#1d4ed8; }}
  header label {{ display:flex; align-items:center; gap:6px; background:#1f2b44; padding:6px 10px; border-radius:6px; }}
  main {{ max-width:1400px; margin:auto; padding:20px; }}
  .scene {{ margin:0 0 16px; padding:14px 16px; background:white; border:1px solid var(--border); border-radius:10px;
    box-shadow:0 2px 5px #1e293b12; }}
  .scene-head {{ display:flex; gap:12px; align-items:baseline; flex-wrap:wrap; margin-bottom:10px;
    padding-bottom:8px; border-bottom:1px solid var(--border); }}
  .scene-uid {{ font-size:12px; color:#334155; }}
  .scene-canonical {{ font-weight:600; }}
  .scene-badges {{ margin-left:auto; display:flex; gap:6px; }}
  .badge {{ padding:2px 8px; border-radius:999px; font-size:11px; font-weight:700; }}
  .badge-pending {{ background:#fef3c7; color:#92400e; }}
  .badge-hint {{ background:#dbeafe; color:#1e40af; }}
  .scene-body {{ display:grid; grid-template-columns:340px 1fr; gap:16px; }}
  .images {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; align-content:start; }}
  figure {{ margin:0; }} figcaption {{ margin-bottom:4px; font-weight:700; font-size:12px; color:var(--muted); }}
  img {{ display:block; width:100%; border-radius:6px; background:#e2e8f0; }}
  .missing, .unavailable {{ display:grid; place-items:center; min-height:120px; border:1px dashed #b8c2d1;
    border-radius:6px; color:var(--muted); font-size:12px; text-align:center; padding:8px; }}
  table.objects {{ width:100%; border-collapse:collapse; }}
  table.objects th, table.objects td {{ padding:6px 8px; border:1px solid var(--border); text-align:left; vertical-align:top; }}
  table.objects th {{ background:#f8fafc; font-size:12px; }}
  .toggle-group {{ display:flex; gap:3px; flex-wrap:wrap; }}
  .vbtn {{ padding:4px 7px; font-size:11px; border:1px solid var(--border); border-radius:5px; background:#f8fafc;
    cursor:pointer; color:#334155; }}
  .vbtn.active.v-true {{ background:#16a34a; color:white; border-color:#16a34a; }}
  .vbtn.active.v-partial {{ background:#f59e0b; color:white; border-color:#f59e0b; }}
  .vbtn.active.v-false {{ background:#dc2626; color:white; border-color:#dc2626; }}
  .vbtn.active.v-unknown {{ background:#94a3b8; color:white; border-color:#94a3b8; }}
  .vis-cell.dirty {{ background:#eff6ff; }}
  .vis-cell.na {{ color:var(--muted); text-align:center; }}
  .hint {{ margin-top:5px; font-size:11px; color:#1e40af; background:#eff6ff; border:1px solid #bfdbfe;
    border-radius:5px; padding:3px 6px; }}
  .hint-apply {{ font-size:10px; padding:1px 6px; margin-left:4px; border-radius:4px; border:1px solid #1e40af;
    background:white; color:#1e40af; cursor:pointer; }}
  .hidden {{ display:none; }}
  #status {{ position:fixed; right:16px; bottom:16px; background:#172033; color:white; padding:10px 14px;
    border-radius:8px; font-size:13px; box-shadow:0 4px 12px #0004; z-index:10; }}
  @media (max-width:900px) {{ .scene-body {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<header>
  <h1>SLAVA visibility review · {len(records)} scenes · {total_objects} objects</h1>
  <input id="search" type="search" placeholder="Search task_uid / instruction…">
  <select id="suite"><option value="">All suites</option>{suite_options}</select>
  <label><input type="checkbox" id="only-pending"> only pending (null)</label>
  <label><input type="checkbox" id="only-hinted"> only AI-flagged</label>
  <button id="download-btn">Download corrections</button>
  <span id="shown"></span>
</header>
<main>{cards}</main>
<div id="status">0 changes staged</div>
<script>
const cards = [...document.querySelectorAll('.scene')];
const search = document.querySelector('#search');
const suite = document.querySelector('#suite');
const onlyPending = document.querySelector('#only-pending');
const onlyHinted = document.querySelector('#only-hinted');
const shown = document.querySelector('#shown');
const statusEl = document.querySelector('#status');
const changes = new Map(); // key task\\u241fhandle\\u241ffield -> value

function cellKey(cell) {{ return cell.dataset.task + '\\u241f' + cell.dataset.handle + '\\u241f' + cell.dataset.field; }}

function applyFilters() {{
  const q = search.value.trim().toLowerCase();
  let count = 0;
  for (const card of cards) {{
    const visible = (!q || card.dataset.search.includes(q)) &&
      (!suite.value || card.dataset.suite === suite.value) &&
      (!onlyPending.checked || Number(card.dataset.pending) > 0) &&
      (!onlyHinted.checked || Number(card.dataset.hinted) > 0);
    card.classList.toggle('hidden', !visible);
    if (visible) count++;
  }}
  shown.textContent = count + ' shown';
}}
[search, suite, onlyPending, onlyHinted].forEach(el => el.addEventListener('input', applyFilters));
applyFilters();

function renderCell(cell) {{
  const group = cell.querySelector('.toggle-group');
  const key = cellKey(cell);
  const current = changes.has(key) ? changes.get(key) : JSON.parse(group.dataset.initial);
  for (const btn of group.querySelectorAll('.vbtn')) {{
    const v = btn.dataset.value === 'null' ? null : JSON.parse(btn.dataset.value);
    btn.classList.toggle('active', v === current);
  }}
  cell.classList.toggle('dirty', changes.has(key));
}}

document.querySelectorAll('.vis-cell:not(.na)').forEach(cell => {{
  renderCell(cell);
  cell.querySelectorAll('.vbtn').forEach(btn => {{
    btn.addEventListener('click', () => {{
      const v = btn.dataset.value === 'null' ? null : JSON.parse(btn.dataset.value);
      const group = cell.querySelector('.toggle-group');
      const initial = JSON.parse(group.dataset.initial);
      const key = cellKey(cell);
      if (v === initial) {{ changes.delete(key); }} else {{ changes.set(key, v); }}
      renderCell(cell);
      statusEl.textContent = changes.size + ' changes staged';
    }});
  }});
}});

document.querySelectorAll('.hint-apply').forEach(btn => {{
  btn.addEventListener('click', () => {{
    const cell = btn.closest('.vis-cell');
    const v = JSON.parse(btn.dataset.value);
    const group = cell.querySelector('.toggle-group');
    const initial = JSON.parse(group.dataset.initial);
    const key = cellKey(cell);
    if (v === initial) {{ changes.delete(key); }} else {{ changes.set(key, v); }}
    renderCell(cell);
    statusEl.textContent = changes.size + ' changes staged';
  }});
}});

document.querySelector('#download-btn').addEventListener('click', () => {{
  const out = [];
  for (const [key, value] of changes.entries()) {{
    const [task_uid, sim_handle, field] = key.split('\\u241f');
    out.push({{task_uid, sim_handle, field, value}});
  }}
  const blob = new Blob([JSON.stringify(out, null, 1)], {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'visibility_corrections.json';
  a.click();
}});
</script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--hints", type=Path, default=None, help="Optional JSON list of low-confidence AI hints")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"Inventory not found: {input_path}")
    output_path = (args.output.resolve() if args.output is not None else input_path.parent / "visibility_review.html")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records = load_jsonl(input_path)
    validate_inventory(records)
    hints = load_hints(args.hints)
    document = generate_html(records, input_path, output_path, hints)
    output_path.write_text(document, encoding="utf-8")
    print(f"Wrote {len(records)} scenes ({sum(len(r.get('objects_raw') or []) for r in records)} objects) to {output_path}")
    print(f"Loaded {len(hints)} AI hints")


if __name__ == "__main__":
    main()
