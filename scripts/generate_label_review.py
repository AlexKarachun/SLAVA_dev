#!/usr/bin/env python3
"""Editable dashboard for the manual validation of auto-labelling (task.md:1224).

task.md requires checking 100 rollouts by hand and estimating the auto-labeller's
accuracy. Until that is done, every `failure_type_auto` in the report is the
output of an unverified script, not data.

The sample is stratified, not the first 100 lines of the annotations file: those
would be almost entirely one model and one variant, so the measured accuracy
would describe that corner rather than the dataset. Selection order:

  1. up to 30% successful episodes (the most expensive kind to mislabel, but
     they are 89 of 536 and would swamp the sample if all were taken),
  2. at least one episode per (model, failure label) pair that exists,
  3. the rest proportional to each model's share of the dataset,

with a fixed seed so the same 100 come back on a re-run.

Each card plays the episode (both cameras), can be scrubbed frame by frame, and
shows the evidence the auto-labeller itself used: first contact, wrong/forbidden
object, final relation, the gripper trace and everything the arm touched. That
is deliberate — a verdict that only sees the label cannot disagree with it.

Verdicts are entered in the browser and exported as JSON; apply_label_review.py
folds them into the pool's manual_labels.jsonl and reports agreement.
"""
from __future__ import annotations

import argparse
import collections
import json
import random
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROLLOUTS = PROJECT_ROOT / "rollouts" / "final" / "pilot_v0"
LABEL_SHORT = {
    "success": "успех",
    "target_grounding_error": "не тот target",
    "reference_grounding_error": "не тот reference",
    "relation_binding_error": "не то отношение",
    "negation_error": "нарушил запрет",
    "physical_execution_error": "физика",
    "no_action_or_timeout": "не двигался",
    "unclear": "непонятно",
}
LABELS = [
    "success", "target_grounding_error", "reference_grounding_error",
    "relation_binding_error", "negation_error", "physical_execution_error",
    "no_action_or_timeout", "unclear",
]


def load_annotations() -> list[dict]:
    path = ROLLOUTS / "rollout_annotations.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def stratified_sample(rows: list[dict], size: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    by_id = {r["run_id"]: r for r in rows}
    chosen: list[str] = []

    def take(candidates: list[dict], count: int) -> None:
        pool = [r for r in candidates if r["run_id"] not in chosen]
        rng.shuffle(pool)
        for record in pool[: max(count, 0)]:
            chosen.append(record["run_id"])

    take([r for r in rows if r.get("success")], int(size * 0.3))

    cells = collections.defaultdict(list)
    for record in rows:
        cells[(record["model"], record["failure_type_auto"])].append(record)
    for cell in sorted(cells):
        if len(chosen) >= size:
            break
        take(cells[cell], 1)

    per_model = collections.Counter(r["model"] for r in rows)
    total = sum(per_model.values())
    remaining = size - len(chosen)
    for model, count in per_model.most_common():
        if len(chosen) >= size:
            break
        take([r for r in rows if r["model"] == model], round(remaining * count / max(total, 1)))
    take(rows, size - len(chosen))
    return [by_id[run_id] for run_id in chosen[:size]]


def frames(run_id: str, camera: str, count: int) -> list[str]:
    """Evenly spaced frames, referenced by relative path.

    Not inlined as base64 on purpose: 100 episodes x ~24 frames is tens of
    megabytes, and the pool sits next to data/ on the same disk (frames are never in
    git, so there is nothing to make portable here)."""
    directory = ROLLOUTS / "episodes" / run_id / "camera" / camera
    if not directory.is_dir():
        return []
    found = sorted(directory.glob("step_*.png"))
    if not found:
        return []
    step = max(len(found) // count, 1)
    picked = found[::step][:count]
    if found[-1] not in picked:
        picked.append(found[-1])
    return [str(Path("..") / f.relative_to(PROJECT_ROOT)) for f in picked]


def episode_trace(run_id: str) -> dict:
    """Gripper opening and contact history, straight from the step log.

    This is what makes a card decidable without opening a notebook: whether the
    gripper ever closed, and what the arm touched, is exactly the evidence the
    auto-labeller reduced to one word."""
    path = ROLLOUTS / "episodes" / run_id / "steps.jsonl"
    if not path.exists():
        return {"steps": 0, "gripper": [], "contacts": []}
    steps = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    gripper: list[float] = []
    contacts: list[str] = []
    for record in steps:
        value = record.get("gripper_state")
        if isinstance(value, (int, float)):
            gripper.append(round(float(value), 3))
        elif isinstance(value, list) and value:
            gripper.append(round(float(value[0]), 3))
        raw = record.get("contacts") or []
        names = raw.keys() if isinstance(raw, dict) else raw
        for name in names:
            if isinstance(name, str) and name not in contacts:
                contacts.append(name)
    return {"steps": len(steps), "gripper": gripper, "contacts": contacts}


def sparkline(values: list[float]) -> str:
    if not values:
        return ""
    step = max(len(values) // 120, 1)
    points = values[::step]
    low, high = min(points), max(points)
    span = (high - low) or 1.0
    coords = " ".join(
        f"{i * 240 / max(len(points) - 1, 1):.1f},{28 - (v - low) / span * 26:.1f}"
        for i, v in enumerate(points)
    )
    return f'<svg class="spark" viewBox="0 0 240 28"><polyline points="{coords}"/></svg>'


def render(sample: list[dict]) -> str:
    # One click, not two: a row of buttons rather than a <select>, because the
    # reviewer goes through 100 cards and every extra click is paid 100 times.
    options = "".join(
        f'<button type="button" data-value="{label}">{LABEL_SHORT.get(label, label)}</button>'
        for label in LABELS
    )
    cards = []
    for index, record in enumerate(sample, start=1):
        run_id = record["run_id"]
        agent = frames(run_id, "agentview", 24)
        wrist = frames(run_id, "wrist", 24)
        trace = episode_trace(run_id)
        gripper = trace["gripper"]
        contacts = ", ".join(trace["contacts"][:8]) or "—"
        wrist_figure = (
            f'<figure><img class="p-wrist" src="{wrist[0]}"><figcaption>wrist</figcaption></figure>'
            if wrist else ""
        )
        strip = "".join(
            f'<img src="{src}" loading="lazy" data-i="{i}">' for i, src in enumerate(agent)
        )
        cards.append(f"""
<article class="card" data-run-id="{run_id}" data-agent='{json.dumps(agent)}' data-wrist='{json.dumps(wrist)}'>
  <header>
    <span class="n">{index}/{len(sample)}</span>
    <span class="model">{record['model']}</span>
    <span class="variant">{record['variant']}</span>
    <span class="steps">{trace['steps']} шагов</span>
  </header>
  <p class="instruction">{record['instruction']}</p>
  <div class="players">
    <figure><img class="p-agent" src="{agent[0] if agent else ''}"><figcaption>agentview</figcaption></figure>
    {wrist_figure}
  </div>
  <input class="scrub" type="range" min="0" max="{max(len(agent) - 1, 0)}" value="0">
  <div class="strip">{strip}</div>
  <dl class="auto">
    <dt>авто</dt><dd><b>{'успех' if record['success'] else record['failure_type_auto']}</b></dd>
    <dt>цель → первый контакт</dt>
    <dd>{record.get('target_object') or '—'} → {record.get('first_contact_object') or 'ничего не тронул'}</dd>
    <dt>не тот / запрещённый</dt>
    <dd>{record.get('wrong_object')} / {record.get('forbidden_object_touched')}</dd>
    <dt>финальное отношение</dt><dd>{record.get('final_relation_success')}</dd>
    <dt>гриппер</dt>
    <dd>{sparkline(gripper)} мин {min(gripper) if gripper else '—'} · макс {max(gripper) if gripper else '—'}</dd>
    <dt>контакты за эпизод</dt><dd>{contacts}</dd>
  </dl>
  <div class="verdict">
    <div class="seg v-success">
      <button type="button" class="ok" data-value="true">успех</button>
      <button type="button" class="bad" data-value="false">провал</button>
    </div>
    <div class="seg v-label">{options}</div>
    <input class="v-note" placeholder="заметка">
  </div>
</article>""")

    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>Ручная валидация авторазметки ({len(sample)} эпизодов)</title>
<style>
 body {{ font: 15px/1.5 system-ui, sans-serif; margin: 0 auto; max-width: 1180px; padding: 24px; }}
 .card {{ border: 1px solid #ccc; border-radius: 10px; padding: 14px; margin-bottom: 20px; }}
 header {{ display: flex; gap: 14px; font-weight: 600; align-items: baseline; }}
 .variant, .steps {{ color: #777; font-weight: 400; }}
 .instruction {{ font-size: 17px; margin: 6px 0 10px; }}
 .players {{ display: flex; gap: 12px; }}
 .players img {{ height: 300px; border-radius: 6px; background: #0002; image-rendering: pixelated; }}
 figcaption {{ font-size: 12px; color: #888; text-align: center; }}
 .scrub {{ width: 100%; margin: 8px 0; }}
 .strip {{ display: flex; gap: 3px; overflow-x: auto; padding-bottom: 4px; }}
 .strip img {{ height: 76px; border-radius: 3px; cursor: pointer; opacity: .75; }}
 .strip img:hover {{ opacity: 1; outline: 2px solid #2a7; }}
 .auto {{ display: grid; grid-template-columns: max-content 1fr; gap: 3px 14px; font-size: 13px; margin-top: 10px; }}
 .auto dt {{ color: #888; }}
 .spark {{ width: 240px; height: 28px; vertical-align: middle; }}
 .spark polyline {{ fill: none; stroke: #2a7; stroke-width: 1.5; }}
 .verdict {{ display: flex; gap: 10px; align-items: center; margin-top: 10px; flex-wrap: wrap; }}
 .seg {{ display: flex; gap: 4px; flex-wrap: wrap; }}
 .seg button {{ font: inherit; font-size: 13px; padding: 5px 10px; border: 1px solid #bbb;
                border-radius: 6px; background: transparent; color: inherit; cursor: pointer; }}
 .seg button:hover {{ border-color: #2a7; }}
 .seg button.on {{ background: #2a7; border-color: #2a7; color: #fff; font-weight: 600; }}
 .v-success button.on.bad {{ background: #c33; border-color: #c33; }}
 .v-note {{ flex: 1; }}
 .done {{ border-color: #2a7; background: #f6fffa; }}
 #bar {{ position: sticky; top: 0; z-index: 5; background: #fff; padding: 10px 0;
        border-bottom: 1px solid #ddd; display: flex; gap: 16px; align-items: center; }}
 #hint {{ color: #888; font-size: 13px; }}
 @media (prefers-color-scheme: dark) {{
   body {{ background: #14161a; color: #e8e8e8; }}
   .card {{ border-color: #333; }} #bar {{ background: #14161a; border-color: #333; }}
   .done {{ background: #16241c; border-color: #2a7; }}
 }}
</style></head><body>
<div id="bar">
  <strong>Проверено: <span id="count">0</span>/{len(sample)}</strong>
  <label><input type="checkbox" id="autoplay" checked> проигрывать</label>
  <button id="export">Скачать вердикты</button>
  <span id="hint">1 — успех, 2 — провал (для карточки в центре экрана)</span>
</div>
{''.join(cards)}
<script>
const cards = [...document.querySelectorAll('.card')];

// Each card plays its own episode: frames are plain files, so a timer swapping
// src is enough — and it only runs while the card is near the viewport.
const observer = new IntersectionObserver(entries => {{
  entries.forEach(e => e.isIntersecting ? play(e.target) : stop(e.target));
}}, {{rootMargin: '300px'}});

function setFrame(card, i) {{
  const agent = JSON.parse(card.dataset.agent), wrist = JSON.parse(card.dataset.wrist);
  if (agent.length) card.querySelector('.p-agent').src = agent[Math.min(i, agent.length - 1)];
  const w = card.querySelector('.p-wrist');
  if (w && wrist.length) w.src = wrist[Math.min(i, wrist.length - 1)];
  card.querySelector('.scrub').value = i;
}}
function play(card) {{
  if (card._timer || !document.getElementById('autoplay').checked) return;
  const n = JSON.parse(card.dataset.agent).length;
  if (!n) return;
  let i = 0;
  card._timer = setInterval(() => setFrame(card, i++ % n), 220);
}}
function stop(card) {{ clearInterval(card._timer); card._timer = null; }}

cards.forEach(card => {{
  observer.observe(card);
  card.querySelector('.scrub').addEventListener('input', e => {{ stop(card); setFrame(card, +e.target.value); }});
  card.querySelectorAll('.strip img').forEach(img =>
    img.addEventListener('click', () => {{ stop(card); setFrame(card, +img.dataset.i); }}));
}});
document.getElementById('autoplay').addEventListener('change', e =>
  cards.forEach(c => e.target.checked ? play(c) : stop(c)));

function selected(card, group) {{
  const on = card.querySelector('.' + group + ' button.on');
  return on ? on.dataset.value : '';
}}
function select(card, group, value) {{
  card.querySelectorAll('.' + group + ' button').forEach(b =>
    b.classList.toggle('on', value !== '' && b.dataset.value === value));
}}
cards.forEach(card => card.querySelectorAll('.seg button').forEach(button =>
  button.addEventListener('click', () => {{
    const group = button.parentElement.classList.contains('v-success') ? 'v-success' : 'v-label';
    // Clicking the active choice clears it — otherwise a misclick is unfixable.
    select(card, group, selected(card, group) === button.dataset.value ? '' : button.dataset.value);
    refresh();
  }})));

document.addEventListener('keydown', e => {{
  if (['INPUT', 'SELECT'].includes(e.target.tagName)) return;
  if (e.key !== '1' && e.key !== '2') return;
  const card = cards.find(c => {{
    const r = c.getBoundingClientRect();
    return r.top < window.innerHeight / 2 && r.bottom > window.innerHeight / 2;
  }});
  if (!card) return;
  select(card, 'v-success', e.key === '1' ? 'true' : 'false');
  refresh();
}});

function collect() {{
  return cards.filter(c => selected(c, 'v-success')).map(c => ({{
    run_id: c.dataset.runId,
    success: selected(c, 'v-success') === 'true',
    failure_type_manual: selected(c, 'v-label') || null,
    note: c.querySelector('.v-note').value || null,
  }}));
}}
function refresh() {{
  cards.forEach(c => c.classList.toggle('done', !!selected(c, 'v-success')));
  document.getElementById('count').textContent = collect().length;
  localStorage.setItem('slava_label_review', JSON.stringify(collect()));
}}
document.addEventListener('change', refresh);
document.addEventListener('input', refresh);
JSON.parse(localStorage.getItem('slava_label_review') || '[]').forEach(v => {{
  const c = cards.find(c => c.dataset.runId === v.run_id);
  if (!c) return;
  select(c, 'v-success', String(v.success));
  select(c, 'v-label', v.failure_type_manual || '');
  c.querySelector('.v-note').value = v.note || '';
}});
refresh();
document.getElementById('export').onclick = () => {{
  const blob = new Blob([JSON.stringify(collect(), null, 2)], {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'label_review_verdicts.json'; a.click();
}};
</script></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "label_review.html")
    args = parser.parse_args()

    rows = load_annotations()
    sample = stratified_sample(rows, args.size, args.seed)
    args.output.write_text(render(sample), encoding="utf-8")
    print(f"{len(sample)} episodes -> {args.output}")
    for model, count in collections.Counter(r["model"] for r in sample).most_common():
        successes = sum(1 for r in sample if r["model"] == model and r["success"])
        print(f"  {model:34s} {count:3d}  (успехов {successes})")


if __name__ == "__main__":
    main()
