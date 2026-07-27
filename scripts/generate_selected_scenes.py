#!/usr/bin/env python3
"""Generate a GitHub Pages gallery for scenes selected in task_inventory.jsonl."""

from __future__ import annotations

import argparse
import csv
import html
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "task_inventory.jsonl"
DEFAULT_LEXICON = PROJECT_ROOT / "data" / "object_lexicon.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "docs" / "index.html"
QUOTA_LABELS = {
    "spatial_relation": "Spatial relation",
    "pick_with_distractors": "Pick / object selection",
    "container": "Container",
    "surface": "Surface",
    "has_distractor": "Has distractor",
    "same_category_distractor": "Same-category distractor",
    "same_color_distractor": "Same-color distractor",
    "ru_case_swap": "ru_case_swap / role-stress",
    "ru_negation": "ru_negation",
}

sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_inventory.io_utils import (  # noqa: E402
    LEXICON_COLUMNS,
    load_jsonl,
    validate_lexicon_row,
)
from slava_inventory.schema import validate_inventory  # noqa: E402


def load_lexicon(path: Path) -> dict[str, dict[str, str]]:
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
        validate_lexicon_row(row, location=f"{path}:{line_number}")
        lexicon[raw_name] = {
            column: str(row.get(column) or "").strip() for column in LEXICON_COLUMNS
        }
    return lexicon


def copy_selected_images(
    selected: list[dict[str, Any]],
    *,
    inventory_dir: Path,
    output_dir: Path,
) -> dict[tuple[str, str], str | None]:
    assets_dir = output_dir / "assets" / "selected_scenes"
    if assets_dir.exists():
        shutil.rmtree(assets_dir)
    assets_dir.mkdir(parents=True, exist_ok=True)

    sources: dict[tuple[str, str], str | None] = {}
    for scene_number, record in enumerate(selected, 1):
        uid = str(record["task_uid"])
        for image_key in ("agentview_rgb", "wrist_rgb"):
            relative_path = record["images"].get(image_key)
            if relative_path is None:
                sources[(uid, image_key)] = None
                continue
            source_path = inventory_dir / relative_path
            if not source_path.is_file():
                raise FileNotFoundError(f"{uid}: missing {image_key}: {source_path}")
            suffix = source_path.suffix.lower() or ".png"
            target_name = f"{scene_number:02d}_{image_key}{suffix}"
            target_path = assets_dir / target_name
            shutil.copy2(source_path, target_path)
            sources[(uid, image_key)] = target_path.relative_to(output_dir).as_posix()
    return sources


def render_lexicon_table(
    objects: list[dict[str, Any]],
    lexicon: dict[str, dict[str, str]],
) -> str:
    headers = (
        "raw_name",
        "sim_handle",
        *[
            field
            for field in LEXICON_COLUMNS
            if field not in {"raw_name", "notes"}
        ],
    )
    rows = []
    for obj in objects:
        raw_name = str(obj["raw_name"])
        if raw_name not in lexicon:
            raise ValueError(f"object_lexicon.csv is missing raw_name={raw_name!r}")
        lexical = lexicon[raw_name]
        values = {
            "raw_name": raw_name,
            "sim_handle": str(obj.get("sim_handle") or ""),
            **lexical,
        }
        rows.append(
            "<tr>"
            + "".join(
                f"<td>{html.escape(str(values[field]))}</td>" for field in headers
            )
            + "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        + "".join(f"<th>{html.escape(field)}</th>" for field in headers)
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def render_image(path: str | None, label: str) -> str:
    if path is None:
        content = '<div class="image-na">N/A</div>'
    else:
        escaped = html.escape(path, quote=True)
        content = (
            f'<a href="{escaped}" target="_blank">'
            f'<img src="{escaped}" alt="{html.escape(label, quote=True)}" loading="lazy">'
            "</a>"
        )
    return (
        "<figure>"
        f"<figcaption>{html.escape(label)}</figcaption>"
        f"{content}</figure>"
    )


def render_quota_eligibility(values: dict[str, bool | None]) -> str:
    eligible = [
        f'<span class="quota">{html.escape(label)}</span>'
        for field, label in QUOTA_LABELS.items()
        if values.get(field) is True
    ]
    pending = sum(values.get(field) is None for field in QUOTA_LABELS)
    if eligible:
        content = "".join(eligible)
    else:
        content = '<span class="quota-empty">No eligible quotas marked</span>'
    if pending:
        content += f'<span class="quota-pending">{pending} pending</span>'
    return f'<div class="quotas"><b>quota_eligibility</b>{content}</div>'


def render_scene(
    record: dict[str, Any],
    scene_number: int,
    lexicon: dict[str, dict[str, str]],
    image_sources: dict[tuple[str, str], str | None],
) -> str:
    uid = str(record["task_uid"])
    source = record["source"]
    if source["environment"] == "LIBERO":
        state = f"init_state_id={source['init_state_id']}"
    else:
        state = (
            f"episode_id={source['episode_id']} · "
            f"reset_seed={source['reset_seed']}"
        )
    search = json.dumps(
        {
            "scene_number": scene_number,
            "task_uid": uid,
            "suite": record["suite"],
            "canonical_en": record["canonical_en"],
            "objects": record["objects_raw"],
            "quota_eligibility": record["quota_eligibility"],
        },
        ensure_ascii=False,
    ).lower()
    return f"""
    <article class="scene" id="scene-{scene_number}" data-search="{html.escape(search, quote=True)}">
      <div class="scene-head">
        <span class="scene-number">{scene_number}</span>
        <div>
          <h2>{html.escape(str(record["canonical_en"]))}</h2>
          <code>{html.escape(uid)}</code>
        </div>
      </div>
      <dl class="metadata">
        <div><dt>suite</dt><dd>{html.escape(str(record["suite"]))}</dd></div>
        <div><dt>state</dt><dd>{html.escape(state)}</dd></div>
      </dl>
      {render_quota_eligibility(record["quota_eligibility"])}
      <div class="images">
        {render_image(image_sources[(uid, "agentview_rgb")], "agentview_rgb")}
        {render_image(image_sources[(uid, "wrist_rgb")], "wrist_rgb")}
      </div>
      <h3>objects_raw × object_lexicon.csv</h3>
      {render_lexicon_table(list(record["objects_raw"]), lexicon)}
    </article>
"""


def generate_document(
    selected: list[dict[str, Any]],
    lexicon: dict[str, dict[str, str]],
    image_sources: dict[tuple[str, str], str | None],
) -> str:
    suite_counts = Counter(str(record["suite"]) for record in selected)
    suite_summary = " · ".join(
        f"{html.escape(suite)}: {count}" for suite, count in sorted(suite_counts.items())
    )
    cards = "".join(
        render_scene(record, number, lexicon, image_sources)
        for number, record in enumerate(selected, 1)
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SLAVA · selected scenes</title>
  <style>
    :root {{ --ink:#172033; --muted:#64748b; --line:#d8dee8; --paper:#fff;
      --canvas:#f3f6fa; --accent:#3157d5; }}
    * {{ box-sizing:border-box; }}
    html {{ scroll-behavior:smooth; }}
    body {{ margin:0; color:var(--ink); background:var(--canvas);
      font:14px/1.45 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    header {{ position:sticky; top:0; z-index:10; display:flex; align-items:center;
      gap:18px; padding:14px 24px; color:#fff; background:#172033; box-shadow:0 3px 12px #0f172a35; }}
    header h1 {{ margin:0; font-size:20px; }}
    header p {{ margin:0 auto 0 0; color:#cbd5e1; }}
    #search {{ width:min(360px,35vw); padding:9px 12px; border:0; border-radius:8px; }}
    main {{ width:min(1500px,100%); margin:auto; padding:24px; }}
    .scene {{ margin:0 0 24px; padding:20px; overflow:hidden; background:var(--paper);
      border:1px solid var(--line); border-radius:14px; box-shadow:0 4px 14px #33415512; }}
    .scene-head {{ display:flex; gap:14px; align-items:flex-start; margin-bottom:14px; }}
    .scene-number {{ display:grid; place-items:center; flex:0 0 34px; height:34px;
      color:#64748b; background:#f1f5f9; border:1px solid #cbd5e1; border-radius:999px;
      font-size:14px; font-weight:750; }}
    h2 {{ margin:0 0 4px; font-size:21px; }} h3 {{ margin:18px 0 8px; font-size:14px; }}
    code {{ color:#475569; overflow-wrap:anywhere; }}
    .metadata {{ display:flex; flex-wrap:wrap; gap:8px; margin:0 0 16px; }}
    .metadata div {{ padding:7px 10px; background:#f8fafc; border:1px solid var(--line); border-radius:8px; }}
    dt {{ display:inline; color:var(--muted); font-size:12px; font-weight:700; }}
    dd {{ display:inline; margin:0 0 0 7px; font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }}
    .quotas {{ display:flex; flex-wrap:wrap; gap:7px; align-items:center; margin:0 0 16px; }}
    .quotas b {{ margin-right:3px; font-size:12px; }}
    .quota,.quota-pending,.quota-empty {{ padding:4px 8px; border-radius:999px; font-size:12px; }}
    .quota {{ color:#166534; background:#dcfce7; border:1px solid #86efac; }}
    .quota-pending {{ color:#92400e; background:#fef3c7; border:1px solid #fcd34d; }}
    .quota-empty {{ color:var(--muted); background:#f1f5f9; border:1px solid #cbd5e1; }}
    .images {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }}
    figure {{ margin:0; }} figcaption {{ margin-bottom:6px; font-weight:750; }}
    img {{ display:block; width:100%; height:auto; border-radius:10px; background:#e2e8f0; }}
    .image-na {{ display:grid; place-items:center; min-height:240px; color:var(--muted);
      border:1px dashed #94a3b8; border-radius:10px; background:#f8fafc; font-weight:700; }}
    .table-wrap {{ width:100%; overflow-x:auto; border:1px solid var(--line); border-radius:9px; }}
    table {{ width:100%; min-width:1040px; border-collapse:collapse; }}
    th,td {{ padding:7px 9px; border-right:1px solid var(--line); border-bottom:1px solid var(--line);
      text-align:left; vertical-align:top; }}
    th {{ background:#f8fafc; font-size:12px; white-space:nowrap; }}
    tr:last-child td {{ border-bottom:0; }} th:last-child,td:last-child {{ border-right:0; }}
    .hidden {{ display:none; }}
    @media (max-width:760px) {{
      header {{ position:static; flex-wrap:wrap; }} header p {{ width:100%; }}
      #search {{ width:100%; }} main {{ padding:12px; }} .scene {{ padding:14px; }}
      .images {{ grid-template-columns:1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>SLAVA selected scenes</h1>
    <p>{len(selected)} scenes · {suite_summary}</p>
    <input id="search" type="search" placeholder="Search number, task, object…">
    <span id="shown">{len(selected)} shown</span>
  </header>
  <main>{cards}</main>
  <script>
    const scenes = [...document.querySelectorAll('.scene')];
    const search = document.querySelector('#search');
    const shown = document.querySelector('#shown');
    search.addEventListener('input', () => {{
      const query = search.value.trim().toLowerCase();
      let count = 0;
      for (const scene of scenes) {{
        const visible = !query || scene.dataset.search.includes(query);
        scene.classList.toggle('hidden', !visible);
        if (visible) count++;
      }}
      shown.textContent = `${{count}} shown`;
    }});
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--lexicon", type=Path, default=DEFAULT_LEXICON)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input.resolve()
    lexicon_path = args.lexicon.resolve()
    output_path = args.output.resolve()

    records = load_jsonl(input_path)
    validate_inventory(records)
    selected = [record for record in records if record["usable_for_slava"] is True]
    if not selected:
        raise ValueError(f"{input_path}: no records have usable_for_slava=true")
    selected.sort(key=lambda record: str(record["task_uid"]))

    lexicon = load_lexicon(lexicon_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image_sources = copy_selected_images(
        selected,
        inventory_dir=input_path.parent,
        output_dir=output_path.parent,
    )
    document = generate_document(selected, lexicon, image_sources)
    output_path.write_text(document, encoding="utf-8")
    (output_path.parent / ".nojekyll").touch()
    print(f"Wrote {len(selected)} selected scenes to {output_path}")


if __name__ == "__main__":
    main()
