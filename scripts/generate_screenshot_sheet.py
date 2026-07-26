#!/usr/bin/env python3
"""Generate a browsable HTML sheet from the SLAVA task inventory."""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "task_inventory.jsonl"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_inventory.io_utils import LEXICON_COLUMNS, load_jsonl  # noqa: E402
from slava_inventory.schema import validate_inventory  # noqa: E402


def load_lexicon(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Object lexicon not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != LEXICON_COLUMNS:
            raise ValueError(
                f"{path}: expected columns {LEXICON_COLUMNS}, got {reader.fieldnames}"
            )
        rows = list(reader)

    lexicon: dict[str, dict[str, str]] = {}
    for line_number, row in enumerate(rows, 2):
        if None in row:
            raise ValueError(f"{path}:{line_number}: too many CSV values")
        raw_name = row["raw_name"].strip()
        if not raw_name:
            raise ValueError(f"{path}:{line_number}: raw_name is empty")
        if raw_name in lexicon:
            raise ValueError(f"{path}:{line_number}: duplicate raw_name {raw_name!r}")
        if row["usable_v0"] not in {"yes", "no", "review"}:
            raise ValueError(
                f"{path}:{line_number}: usable_v0 must be yes, no, or review"
            )
        lexicon[raw_name] = {column: row[column].strip() for column in LEXICON_COLUMNS}
    return lexicon


def validate_lexicon_coverage(
    records: list[dict[str, Any]], lexicon: dict[str, dict[str, str]]
) -> None:
    inventory_names = {
        str(obj["raw_name"])
        for record in records
        for obj in record.get("objects_raw", [])
    }
    missing = sorted(inventory_names - set(lexicon))
    if missing:
        raise ValueError(f"Object lexicon is missing raw_name values: {missing}")


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


def lexicon_value(value: str) -> str:
    return html.escape(value) if value else '<span class="muted">-</span>'


def render_lexicon(lexicon: dict[str, dict[str, str]]) -> str:
    counts = {"yes": 0, "no": 0, "review": 0}
    rows = []
    for raw_name, lexical in lexicon.items():
        usable = lexical["usable_v0"]
        counts[usable] += 1
        rows.append(
            "<tr>"
            f"<td><code>{html.escape(raw_name)}</code></td>"
            f"<td>{lexicon_value(lexical['category_en'])}</td>"
            f"<td>{lexicon_value(lexical['category_ru'])}</td>"
            f"<td>{lexicon_value(lexical['color_en'])}</td>"
            f"<td>{lexicon_value(lexical['color_ru'])}</td>"
            f"<td>{lexicon_value(lexical['allowed_synonyms_ru'])}</td>"
            f'<td><span class="v0-badge v0-{html.escape(usable, quote=True)}">'
            f"{html.escape(usable)}</span></td>"
            f"<td>{lexicon_value(lexical['notes'])}</td>"
            "</tr>"
        )
    return (
        '<section class="lexicon-overview">'
        '<div class="lexicon-heading"><div>'
        "<h2>Object lexicon</h2>"
        f'<p>{len(lexicon)} objects from <code>object_lexicon.csv</code></p>'
        "</div>"
        '<div class="lexicon-counts">'
        f'<span class="v0-badge v0-yes">yes {counts["yes"]}</span>'
        f'<span class="v0-badge v0-no">no {counts["no"]}</span>'
        f'<span class="v0-badge v0-review">review {counts["review"]}</span>'
        "</div></div>"
        '<div class="lexicon-wrap"><table class="lexicon-table"><thead><tr>'
        "<th>raw_name</th><th>category_en</th><th>category_ru</th><th>color_en</th>"
        "<th>color_ru</th><th>allowed_synonyms_ru</th><th>usable_v0</th><th>notes</th>"
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
        "</section>"
    )


def scene_v0_status(
    objects: list[dict[str, Any]], lexicon: dict[str, dict[str, str]]
) -> tuple[str, list[str]]:
    statuses = [
        (str(obj["raw_name"]), lexicon[str(obj["raw_name"])]["usable_v0"])
        for obj in objects
    ]
    blocked = [raw_name for raw_name, status in statuses if status == "no"]
    if blocked:
        return "no", blocked
    if statuses and all(status == "yes" for _, status in statuses):
        return "yes", []
    return "unknown", []


def render_objects(
    objects: list[dict[str, Any]], lexicon: dict[str, dict[str, str]]
) -> str:
    if not objects:
        return '<p class="empty">No objects</p>'
    rows = []
    for obj in objects:
        name = obj.get("raw_name") or obj.get("sim_handle") or "unnamed"
        handle = obj.get("sim_handle")
        lexical = lexicon[str(name)]
        usable = lexical["usable_v0"]
        rows.append(
            f'<tr class="v0-{html.escape(usable, quote=True)}">'
            f"<td>{html.escape(str(name))}</td>"
            f"<td>{display_value(handle)}</td>"
            f"<td>{html.escape(visibility_label(obj.get('visible_agentview')))}</td>"
            f"<td>{html.escape(visibility_label(obj.get('visible_wrist')))}</td>"
            f"<td>{lexicon_value(lexical['category_en'])}</td>"
            f"<td>{lexicon_value(lexical['category_ru'])}</td>"
            f"<td>{lexicon_value(lexical['color_en'])}</td>"
            f"<td>{lexicon_value(lexical['color_ru'])}</td>"
            f"<td>{lexicon_value(lexical['allowed_synonyms_ru'])}</td>"
            f'<td><span class="v0-badge v0-{html.escape(usable, quote=True)}">'
            f"{html.escape(usable)}</span></td>"
            f"<td>{lexicon_value(lexical['notes'])}</td>"
            "</tr>"
        )
    return (
        '<div class="objects-wrap"><table class="objects"><thead><tr>'
        "<th>raw_name</th><th>sim_handle</th><th>visible_agentview</th>"
        "<th>visible_wrist</th><th>category_en</th><th>category_ru</th>"
        "<th>color_en</th><th>color_ru</th><th>allowed_synonyms_ru</th>"
        "<th>usable_v0</th><th>notes</th>"
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    )


def visible_object_names(objects: list[dict[str, Any]], camera_key: str) -> list[str]:
    return [
        str(obj.get("raw_name") or obj.get("sim_handle") or "unnamed")
        for obj in objects
        if obj.get(camera_key) is True or obj.get(camera_key) == "visible_partial"
    ]


def render_small(
    record: dict[str, Any], lexicon: dict[str, dict[str, str]]
) -> str:
    objects = record.get("objects_raw") or []
    agent_visible = visible_object_names(objects, "visible_agentview")
    wrist_visible = visible_object_names(objects, "visible_wrist")
    v0_status, blocked = scene_v0_status(objects, lexicon)
    blocked_text = ", ".join(blocked)
    if v0_status == "yes":
        v0_summary = '<span class="scene-v0 scene-v0-yes">All objects usable for v0</span>'
    elif v0_status == "no":
        v0_summary = (
            '<span class="scene-v0 scene-v0-no">Contains v0=no objects</span>'
            f'<span class="blocked-objects">{html.escape(blocked_text)}</span>'
        )
    else:
        v0_summary = '<span class="scene-v0 scene-v0-unknown">Lexicon review incomplete</span>'
    return f"""
      <h2>{html.escape(str(record.get('canonical_en') or ''))}</h2>
      <section class="v0-summary">{v0_summary}</section>
      <section>
        <h3>Objects and lexicon</h3>
        {render_objects(objects, lexicon)}
      </section>
      <section class="visible-summary">
        <h3>Visible objects</h3>
        <p><strong>Agent view:</strong> {html.escape(', '.join(agent_visible) or 'none')}</p>
        <p><strong>Wrist view:</strong> {html.escape(', '.join(wrist_visible) or 'none')}</p>
      </section>
      <section><h3>Notes</h3><p class="notes">{display_value(record.get('notes'))}</p></section>
    """


def render_card(
    record: dict[str, Any],
    index: int,
    mode: str,
    inventory_dir: Path,
    output_dir: Path,
    lexicon: dict[str, dict[str, str]],
) -> str:
    uid = str(record.get("task_uid") or f"scene-{index}")
    suite = str(record.get("suite") or "unknown")
    objects = record.get("objects_raw") or []
    agent_min = minimum_visibility_rank(objects, "visible_agentview")
    wrist_min = minimum_visibility_rank(objects, "visible_wrist")
    wrist_na = not bool((record.get("images") or {}).get("wrist_rgb"))
    v0_status, _ = scene_v0_status(objects, lexicon)
    if mode == "small":
        body = render_small(record, lexicon)
        searchable_fields = {
            "task_uid": record.get("task_uid"),
            "canonical_en": record.get("canonical_en"),
            "objects_raw": record.get("objects_raw"),
            "object_lexicon": [lexicon[str(obj["raw_name"])] for obj in objects],
            "notes": record.get("notes"),
        }
        searchable = json.dumps(searchable_fields, ensure_ascii=False).lower()
    else:
        body = f'<div class="full-record">{render_tree(record)}</div>'
        searchable = json.dumps(record, ensure_ascii=False).lower()
    return f"""
    <article class="scene" data-suite="{html.escape(suite, quote=True)}"
             data-agent-min="{agent_min}" data-wrist-min="{wrist_min}"
             data-wrist-na="{str(wrist_na).lower()}"
             data-v0-objects="{html.escape(v0_status, quote=True)}"
             data-search="{html.escape(searchable, quote=True)}">
      <div class="scene-identity">
        <span class="scene-index">Scene index: {index}</span>
        <code class="scene-name">{html.escape(uid)}</code>
      </div>
      {render_images(record, inventory_dir, output_dir)}
      <div class="content">{body}</div>
    </article>
    """


def generate_html(
    records: list[dict[str, Any]],
    mode: str,
    input_path: Path,
    output_path: Path,
    lexicon: dict[str, dict[str, str]],
) -> str:
    suites = sorted({str(record.get("suite") or "unknown") for record in records})
    cards = "".join(
        render_card(record, index, mode, input_path.parent, output_path.parent, lexicon)
        for index, record in enumerate(records, 1)
    )
    v0_counts = {"yes": 0, "no": 0, "unknown": 0}
    for record in records:
        status, _ = scene_v0_status(record.get("objects_raw") or [], lexicon)
        v0_counts[status] += 1
    suite_options = "".join(
        f'<option value="{html.escape(suite, quote=True)}">{html.escape(suite)}</option>'
        for suite in suites
    )
    lexicon_overview = render_lexicon(lexicon) if mode == "small" else ""
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
    .lexicon-overview {{ margin:0 0 22px; padding:20px; background:white; border:1px solid var(--border);
      border-radius:10px; box-shadow:0 2px 5px #1e293b12; }}
    .lexicon-heading {{ display:flex; gap:20px; align-items:center; justify-content:space-between; margin-bottom:14px; }}
    .lexicon-heading h2 {{ margin:0; }} .lexicon-heading p {{ color:var(--muted); }}
    .lexicon-counts {{ display:flex; gap:8px; flex-wrap:wrap; }}
    .lexicon-wrap {{ width:100%; overflow-x:auto; border:1px solid var(--border); border-radius:6px; }}
    .lexicon-table {{ min-width:1260px; border:0; }}
    .lexicon-table th:first-child {{ min-width:210px; }}
    .lexicon-table th:nth-child(2), .lexicon-table th:nth-child(3) {{ min-width:140px; }}
    .lexicon-table th:nth-child(6) {{ min-width:180px; }}
    .lexicon-table th:last-child {{ min-width:220px; }}
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
    .content {{ min-width:0; }}
    table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:6px 8px; border:1px solid var(--border); text-align:left; }}
    th {{ background:#f8fafc; }} .muted,.null,.empty {{ color:var(--muted); }} .true {{ color:#15803d; }} .false {{ color:#b91c1c; }}
    .objects-wrap {{ width:100%; max-width:100%; overflow-x:auto; border:1px solid var(--border); border-radius:6px; }}
    .objects {{ min-width:1180px; border:0; }}
    .objects th:first-child {{ min-width:210px; }}
    .objects th:nth-child(2), .objects th:nth-child(3) {{ min-width:85px; }}
    .objects th:nth-child(4), .objects th:nth-child(5) {{ min-width:135px; }}
    .objects th:last-child {{ min-width:180px; }}
    .objects tr.v0-review td {{ background:#fffbeb; }}
    .v0-badge, .scene-v0 {{ display:inline-block; padding:3px 8px; border-radius:999px; font-weight:700; }}
    .v0-badge.v0-yes, .scene-v0-yes {{ background:#dcfce7; color:#166534; }}
    .v0-badge.v0-no, .scene-v0-no {{ background:#ffe4e6; color:#9f1239; }}
    .v0-badge.v0-review, .scene-v0-unknown {{ background:#fef3c7; color:#92400e; }}
    .v0-summary {{ display:flex; gap:10px; align-items:center; margin:0 0 12px; }}
    .blocked-objects {{ color:#9f1239; font-family:ui-monospace,monospace; font-size:12px; }}
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
    <h1>SLAVA inventory · {len(records)} scenes · {html.escape(mode)} · all-v0 {v0_counts['yes']}</h1>
    <input id="search" type="search" placeholder="Search scenes…">
    <select id="suite"><option value="">All suites</option>{suite_options}</select>
    <select id="agent-threshold" title="Every object must meet this Agent view visibility">
      <option value="0">Agent: any</option>
      <option value="1">Agent: partial+</option>
      <option value="2">Agent: visible</option>
    </select>
    <select id="wrist-threshold" title="Every annotated object must meet this Wrist view visibility; scenes without a wrist camera pass as N/A">
      <option value="0">Wrist: any</option>
      <option value="1">Wrist: partial+</option>
      <option value="2">Wrist: visible</option>
    </select>
    <select id="v0-objects" title="Filter by object_lexicon usable_v0 for every scene object">
      <option value="">Objects v0: any</option>
      <option value="yes">Objects v0: all yes</option>
    </select>
    <span id="shown">{len(records)} shown</span>
  </header>
  <main>{lexicon_overview}{cards}</main>
  <script>
    const cards = [...document.querySelectorAll('.scene')];
    const search = document.querySelector('#search');
    const suite = document.querySelector('#suite');
    const agentThreshold = document.querySelector('#agent-threshold');
    const wristThreshold = document.querySelector('#wrist-threshold');
    const v0Objects = document.querySelector('#v0-objects');
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
          (card.dataset.wristNa === 'true' || Number(card.dataset.wristMin) >= wristMin) &&
          (!v0Objects.value || card.dataset.v0Objects === v0Objects.value);
        card.classList.toggle('hidden', !visible);
        if (visible) count++;
      }}
      shown.textContent = `${{count}} shown`;
    }}
    search.addEventListener('input', applyFilters);
    suite.addEventListener('change', applyFilters);
    agentThreshold.addEventListener('change', applyFilters);
    wristThreshold.addEventListener('change', applyFilters);
    v0Objects.addEventListener('change', applyFilters);
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input JSONL inventory")
    parser.add_argument("--mode", choices=("small", "full"), default="small")
    parser.add_argument(
        "--lexicon",
        type=Path,
        default=None,
        help="Object lexicon CSV (default: object_lexicon.csv beside the input)",
    )
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
    lexicon_path = (
        args.lexicon.resolve()
        if args.lexicon is not None
        else input_path.parent / "object_lexicon.csv"
    )
    lexicon = load_lexicon(lexicon_path)
    validate_lexicon_coverage(records, lexicon)
    document = generate_html(records, args.mode, input_path, output_path, lexicon)
    output_path.write_text(document, encoding="utf-8")
    print(f"Wrote {len(records)} scenes to {output_path} ({args.mode} mode)")


if __name__ == "__main__":
    main()
