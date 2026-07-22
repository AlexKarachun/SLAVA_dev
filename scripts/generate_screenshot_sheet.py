#!/usr/bin/env python3
"""Generate a browsable HTML sheet from the SLAVA task inventory."""

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


def display_value(value: Any) -> str:
    if value is None:
        return '<span class="null">null</span>'
    if value is True:
        return '<span class="bool true">true</span>'
    if value is False:
        return '<span class="bool false">false</span>'
    return html.escape(str(value))


def render_tree(value: Any) -> str:
    """Render arbitrary JSON without dropping any fields or values."""
    if isinstance(value, dict):
        rows = "".join(
            f'<div class="tree-row"><span class="tree-key">{html.escape(str(key))}</span>'
            f'<div class="tree-value">{render_tree(child)}</div></div>'
            for key, child in value.items()
        )
        return f'<div class="tree dict">{rows}</div>'
    if isinstance(value, list):
        if not value:
            return '<span class="empty">[]</span>'
        rows = "".join(
            f'<div class="tree-row"><span class="tree-key">[{index}]</span>'
            f'<div class="tree-value">{render_tree(child)}</div></div>'
            for index, child in enumerate(value)
        )
        return f'<div class="tree list">{rows}</div>'
    return display_value(value)


def image_source(
    relative_path: str | None, *, inventory_dir: Path, output_dir: Path
) -> tuple[str | None, bool]:
    if not relative_path:
        return None, False
    image_path = inventory_dir / relative_path
    source = os.path.relpath(image_path, output_dir).replace(os.sep, "/")
    return source, image_path.is_file()


def render_images(record: dict[str, Any], inventory_dir: Path, output_dir: Path) -> str:
    images = record.get("images") or {}
    panels = []
    for key, label in (("agentview_rgb", "Agent view"), ("wrist_rgb", "Wrist view")):
        raw_path = images.get(key)
        source, exists = image_source(raw_path, inventory_dir=inventory_dir, output_dir=output_dir)
        if source and exists:
            content = (
                f'<a href="{html.escape(source, quote=True)}" target="_blank">'
                f'<img src="{html.escape(source, quote=True)}" loading="lazy" '
                f'alt="{html.escape(label, quote=True)}"></a>'
            )
        elif raw_path:
            content = f'<div class="missing">Missing: {html.escape(str(raw_path))}</div>'
        else:
            content = '<div class="unavailable">Not available</div>'
        panels.append(f'<figure><figcaption>{label}</figcaption>{content}</figure>')
    return '<div class="images">' + "".join(panels) + "</div>"


def visibility_label(value: Any) -> str:
    if value is True:
        return "visible"
    if value is False:
        return "not visible"
    if value == "visible_partial":
        return "partial"
    return "-"


def visibility_rank(value: Any) -> int:
    """Order visibility values for minimum-threshold scene filters."""
    if value is True:
        return 2
    if value == "visible_partial":
        return 1
    return 0


def minimum_visibility_rank(objects: list[dict[str, Any]], camera_key: str) -> int:
    specified_ranks = [
        visibility_rank(obj.get(camera_key))
        for obj in objects
        if obj.get(camera_key) is not None
    ]
    if not specified_ranks:
        return 0
    return min(specified_ranks)


def render_objects(objects: list[dict[str, Any]]) -> str:
    if not objects:
        return '<p class="empty">No objects</p>'
    rows = []
    for obj in objects:
        name = obj.get("raw_name") or obj.get("sim_handle") or "unnamed"
        handle = obj.get("sim_handle")
        handle_suffix = "" if not handle or handle == name else f" · {html.escape(str(handle))}"
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(name))}<span class=\"muted\">{handle_suffix}</span></td>"
            f"<td>{html.escape(visibility_label(obj.get('visible_agentview')))}</td>"
            f"<td>{html.escape(visibility_label(obj.get('visible_wrist')))}</td>"
            "</tr>"
        )
    return (
        '<table class="objects"><thead><tr><th>Object</th><th>Agent view</th>'
        f'<th>Wrist view</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
    )


def visible_object_names(objects: list[dict[str, Any]], camera_key: str) -> list[str]:
    return [
        str(obj.get("raw_name") or obj.get("sim_handle") or "unnamed")
        for obj in objects
        if obj.get(camera_key) is True or obj.get(camera_key) == "visible_partial"
    ]


def render_small(record: dict[str, Any]) -> str:
    objects = record.get("objects_raw") or []
    agent_visible = visible_object_names(objects, "visible_agentview")
    wrist_visible = visible_object_names(objects, "visible_wrist")
    return f"""
      <h2>{html.escape(str(record.get('canonical_en') or ''))}</h2>
      <section>
        <h3>Objects raw</h3>
        {render_objects(objects)}
      </section>
      <section class="visible-summary">
        <h3>Visible objects</h3>
        <p><strong>Agent view:</strong> {html.escape(', '.join(agent_visible) or 'none')}</p>
        <p><strong>Wrist view:</strong> {html.escape(', '.join(wrist_visible) or 'none')}</p>
      </section>
      <section><h3>Notes</h3><p class="notes">{display_value(record.get('notes'))}</p></section>
    """


def render_card(
    record: dict[str, Any], index: int, mode: str, inventory_dir: Path, output_dir: Path
) -> str:
    uid = str(record.get("task_uid") or f"scene-{index}")
    suite = str(record.get("suite") or "unknown")
    objects = record.get("objects_raw") or []
    agent_min = minimum_visibility_rank(objects, "visible_agentview")
    wrist_min = minimum_visibility_rank(objects, "visible_wrist")
    if mode == "small":
        body = render_small(record)
        searchable_fields = {
            "task_uid": record.get("task_uid"),
            "canonical_en": record.get("canonical_en"),
            "objects_raw": record.get("objects_raw"),
            "notes": record.get("notes"),
        }
        searchable = json.dumps(searchable_fields, ensure_ascii=False).lower()
    else:
        body = f'<div class="full-record">{render_tree(record)}</div>'
        searchable = json.dumps(record, ensure_ascii=False).lower()
    return f"""
    <article class="scene" data-suite="{html.escape(suite, quote=True)}"
             data-agent-min="{agent_min}" data-wrist-min="{wrist_min}"
             data-search="{html.escape(searchable, quote=True)}">
      <div class="scene-identity">
        <span class="scene-index">Scene index: {index}</span>
        <code class="scene-name">{html.escape(uid)}</code>
      </div>
      {render_images(record, inventory_dir, output_dir)}
      <div class="content">{body}</div>
    </article>
    """


def generate_html(records: list[dict[str, Any]], mode: str, input_path: Path, output_path: Path) -> str:
    suites = sorted({str(record.get("suite") or "unknown") for record in records})
    cards = "".join(
        render_card(record, index, mode, input_path.parent, output_path.parent)
        for index, record in enumerate(records, 1)
    )
    suite_options = "".join(
        f'<option value="{html.escape(suite, quote=True)}">{html.escape(suite)}</option>'
        for suite in suites
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SLAVA task inventory — {html.escape(mode)}</title>
  <style>
    :root {{ color-scheme: light; --border:#d8dee8; --muted:#64748b; --bg:#f4f6f9; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--bg); color:#172033; font:14px/1.45 system-ui,sans-serif; }}
    header {{ position:sticky; top:0; z-index:2; display:flex; gap:12px; align-items:center;
      padding:12px 20px; background:#172033; color:white; box-shadow:0 2px 8px #0003; }}
    header h1 {{ margin:0 auto 0 0; font-size:18px; }}
    header input, header select {{ min-width:180px; padding:8px 10px; border:0; border-radius:6px; }}
    main {{ max-width:1500px; margin:auto; padding:20px; }}
    .scene {{ display:grid; grid-template-columns:minmax(360px, 44%) 1fr; gap:20px; position:relative;
      margin:0 0 22px; padding:54px 20px 20px; background:white; border:1px solid var(--border); border-radius:10px;
      box-shadow:0 2px 5px #1e293b12; break-inside:avoid; }}
    .scene-identity {{ position:absolute; inset:13px 20px auto; display:flex; gap:14px; align-items:baseline;
      padding-bottom:9px; border-bottom:1px solid var(--border); overflow:hidden; }}
    .scene-index {{ flex:none; color:var(--muted); font-size:12px; font-weight:700; }}
    .scene-name {{ overflow:hidden; color:#334155; font-size:12px; text-overflow:ellipsis; white-space:nowrap; }}
    .images {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; align-content:start; }}
    figure {{ margin:0; }} figcaption {{ margin-bottom:5px; font-weight:700; }}
    img {{ display:block; width:100%; height:auto; border-radius:6px; background:#e2e8f0; }}
    .missing,.unavailable {{ display:grid; place-items:center; min-height:170px; padding:12px;
      border:1px dashed #b8c2d1; border-radius:6px; color:var(--muted); text-align:center; }}
    .missing {{ color:#b91c1c; }} h2 {{ margin:0 30px 14px 0; font-size:20px; }}
    h3 {{ margin:15px 0 7px; font-size:14px; }} p {{ margin:5px 0; }}
    table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:6px 8px; border:1px solid var(--border); text-align:left; }}
    th {{ background:#f8fafc; }} .muted,.null,.empty {{ color:var(--muted); }} .true {{ color:#15803d; }} .false {{ color:#b91c1c; }}
    .notes {{ white-space:pre-wrap; }} .tree {{ border-left:1px solid var(--border); margin-left:7px; padding-left:10px; }}
    .tree-row {{ display:grid; grid-template-columns:minmax(130px, 28%) 1fr; gap:10px; padding:3px 0; }}
    .tree-key {{ color:#475569; font-weight:650; overflow-wrap:anywhere; }} .tree-value {{ overflow-wrap:anywhere; min-width:0; }}
    body.mode-full {{ min-width:max-content; }}
    body.mode-full header {{ min-width:2400px; }}
    body.mode-full main {{ width:2440px; max-width:none; margin:0; }}
    body.mode-full .scene {{ width:2400px; grid-template-columns:700px 1fr; }}
    body.mode-full .tree-row {{ grid-template-columns:320px minmax(900px, 1fr); }}
    body.mode-full .tree-key, body.mode-full .tree-value {{ overflow-wrap:normal; word-break:normal; }}
    body.mode-full .tree-key {{ white-space:nowrap; }}
    .hidden {{ display:none; }}
    @media (max-width:900px) {{
      body.mode-small .scene {{ grid-template-columns:1fr; }}
      body.mode-small header {{ flex-wrap:wrap; }}
      body.mode-small header h1 {{ width:100%; }}
    }}
    @media print {{ header {{ position:static; }} .scene {{ box-shadow:none; }} }}
  </style>
</head>
<body class="mode-{html.escape(mode, quote=True)}">
  <header>
    <h1>SLAVA inventory · {len(records)} scenes · {html.escape(mode)} mode</h1>
    <input id="search" type="search" placeholder="Search scenes…">
    <select id="suite"><option value="">All suites</option>{suite_options}</select>
    <select id="agent-threshold" title="Every object must meet this Agent view visibility">
      <option value="0">Agent: any</option>
      <option value="1">Agent: partial+</option>
      <option value="2">Agent: visible</option>
    </select>
    <select id="wrist-threshold" title="Every object must meet this Wrist view visibility">
      <option value="0">Wrist: any</option>
      <option value="1">Wrist: partial+</option>
      <option value="2">Wrist: visible</option>
    </select>
    <span id="shown">{len(records)} shown</span>
  </header>
  <main>{cards}</main>
  <script>
    const cards = [...document.querySelectorAll('.scene')];
    const search = document.querySelector('#search');
    const suite = document.querySelector('#suite');
    const agentThreshold = document.querySelector('#agent-threshold');
    const wristThreshold = document.querySelector('#wrist-threshold');
    const shown = document.querySelector('#shown');
    function applyFilters() {{
      const query = search.value.trim().toLowerCase();
      const agentMin = Number(agentThreshold.value);
      const wristMin = Number(wristThreshold.value);
      let count = 0;
      for (const card of cards) {{
        const visible = (!query || card.dataset.search.includes(query)) &&
          (!suite.value || card.dataset.suite === suite.value) &&
          Number(card.dataset.agentMin) >= agentMin &&
          Number(card.dataset.wristMin) >= wristMin;
        card.classList.toggle('hidden', !visible);
        if (visible) count++;
      }}
      shown.textContent = `${{count}} shown`;
    }}
    search.addEventListener('input', applyFilters);
    suite.addEventListener('change', applyFilters);
    agentThreshold.addEventListener('change', applyFilters);
    wristThreshold.addEventListener('change', applyFilters);
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input JSONL inventory")
    parser.add_argument("--mode", choices=("small", "full"), default="small")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output HTML (default: data/screenshot_sheet_<mode>.html)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(f"Inventory not found: {input_path}")
    output_path = (
        args.output.resolve()
        if args.output is not None
        else input_path.parent / f"screenshot_sheet_{args.mode}.html"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records = load_jsonl(input_path)
    validate_inventory(records)
    document = generate_html(records, args.mode, input_path, output_path)
    output_path.write_text(document, encoding="utf-8")
    print(f"Wrote {len(records)} scenes to {output_path} ({args.mode} mode)")


if __name__ == "__main__":
    main()
