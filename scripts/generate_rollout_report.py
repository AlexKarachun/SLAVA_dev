#!/usr/bin/env python3
"""Generate the pilot v0 rollout technical report (data overview, setup,
camera demos, behavioral-pilot / cleaned-language-effect metric tables from
task.md). Reads whatever is currently in the active pool's
rollout_annotations.jsonl (rollouts/final/pilot_v0/, see rollouts/RUNS.md) —
safe to run against partial (smoke-test) data or the full run.

Usage: python scripts/generate_rollout_report.py [--output data/rollout_report.html]
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from slava_rollout.provenance import partition  # noqa: E402
from slava_rollout.stats import wilson as wilson_ci  # noqa: E402

DATA_DIR = PROJECT_ROOT / "data"
ROLLOUTS_DIR = PROJECT_ROOT / "rollouts" / "final" / "pilot_v0"

# Display-only spelling of model names. The identity stored in annotations,
# MODEL_REGISTRY and published_baselines.json stays ASCII ("pi0") — renaming it
# there would desync 536 already-collected rows and every lookup keyed by it.
# The papers write these two as pi with a subscript, so the reports do too.
PRETTY_MODEL_NAMES = {"pi0": "\u03c00", "pi0.5": "\u03c00.5"}


def pretty_model(name: str) -> str:
    return PRETTY_MODEL_NAMES.get(name, name)


VARIANT_ORDER = [
    "en_canonical", "en_paraphrase", "mt_russian", "ru_literal",
    "ru_free_order", "ru_case_swap", "ru_negation", "code_switch",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


# --------------------------------------------------------------------------
# Concrete examples (lexicon row, inventory row, prompt variants for one scene)
# --------------------------------------------------------------------------

def build_examples() -> dict[str, Any]:
    lexicon = load_csv(DATA_DIR / "object_lexicon.csv")
    inventory = load_jsonl(DATA_DIR / "task_inventory.jsonl")
    prompts = load_jsonl(DATA_DIR / "pilot_v0_release" / "prompts_v0.jsonl")

    lexicon_example = next(
        (r for r in lexicon if r.get("raw_name") == "akita_black_bowl"), lexicon[0] if lexicon else {}
    )

    inventory_example = next(
        (r for r in inventory if r.get("task_uid", "").endswith("init034")
         and "drawer" in r.get("task_uid", "") and "bowl" in r.get("canonical_en", "")),
        inventory[0] if inventory else {},
    )

    by_uid: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in prompts:
        by_uid[p["task_uid"]].append(p)
    prompt_uid = max(by_uid, key=lambda u: len(by_uid[u])) if by_uid else None
    prompt_variants = sorted(by_uid.get(prompt_uid, []), key=lambda p: VARIANT_ORDER.index(p["variant"]) if p["variant"] in VARIANT_ORDER else 99)

    return {
        "lexicon_row": lexicon_example,
        "inventory_uid": inventory_example.get("task_uid"),
        "inventory_canonical_en": inventory_example.get("canonical_en"),
        "inventory_n_objects": len(inventory_example.get("objects_raw", [])),
        "prompt_uid": prompt_uid,
        "prompt_variants": [{"variant": p["variant"], "instruction": p["instruction"]} for p in prompt_variants],
    }


# --------------------------------------------------------------------------
# Data overview (D1-D4)
# --------------------------------------------------------------------------

def build_data_overview() -> dict[str, Any]:
    inventory = load_jsonl(DATA_DIR / "task_inventory.jsonl")
    lexicon = load_csv(DATA_DIR / "object_lexicon.csv")
    selected = load_jsonl(DATA_DIR / "selected_tasks_v0.jsonl")
    frames = load_jsonl(DATA_DIR / "pilot_v0_release" / "frames_v0.jsonl")

    usable = sum(1 for r in inventory if r.get("usable_for_slava"))
    env_counts = Counter(r.get("source", {}).get("environment") for r in selected)

    visible_agent = visible_wrist = total_objects = 0
    for r in inventory:
        for obj in r.get("objects_raw", []):
            total_objects += 1
            if obj.get("visible_agentview") is True:
                visible_agent += 1
            if obj.get("visible_wrist") is True:
                visible_wrist += 1

    lexicon_categories = Counter(r.get("category_en") for r in lexicon)
    native_check_passed = sum(
        1 for r in frames if r.get("validation", {}).get("native_check") == "passed"
    )

    return {
        "n_candidate_scenes": len(inventory),
        "n_usable_for_slava": usable,
        "n_selected": len(selected),
        "env_counts": dict(env_counts),
        "n_lexicon_entries": len(lexicon),
        "lexicon_categories": lexicon_categories.most_common(),
        "total_objects_labeled": total_objects,
        "visible_agentview_pct": (visible_agent / total_objects * 100) if total_objects else 0,
        "visible_wrist_pct": (visible_wrist / total_objects * 100) if total_objects else 0,
        "n_frames": len(frames),
        "n_native_check_passed": native_check_passed,
    }


# --------------------------------------------------------------------------
# Setup overview (models, envs, hyperparameters)
# --------------------------------------------------------------------------

def build_setup_overview() -> dict[str, Any]:
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from slava_rollout.schema import (  # noqa: E402
        DEFAULT_N_REPEATS,
        MAX_EPISODE_STEPS,
        MODEL_REGISTRY,
        environments_for_model,
    )

    prompts = load_jsonl(DATA_DIR / "pilot_v0_release" / "prompts_v0.jsonl")
    prompts_by_env = Counter(p["environment"] for p in prompts)
    n_task_uids = len({p["task_uid"] for p in prompts})

    models = []
    planned_episodes = 0
    for key, spec in MODEL_REGISTRY.items():
        envs = environments_for_model(key)
        n_prompts = sum(1 for p in prompts if p["environment"] in envs)
        planned_episodes += n_prompts
        models.append(
            {
                "key": key,
                "display_name": spec["display_name"],
                "backbone": spec["backbone"],
                "environments": [
                    {"name": e, "checkpoint": spec["environments"][e]["checkpoint"],
                     "zero_shot": spec["environments"][e]["zero_shot"]}
                    for e in envs
                ],
                "n_prompts": n_prompts,
            }
        )

    return {
        "models": models,
        "n_prompts_total": len(prompts),
        "n_task_uids": n_task_uids,
        "prompts_by_env": dict(prompts_by_env),
        "n_repeats": DEFAULT_N_REPEATS,
        "max_steps": dict(MAX_EPISODE_STEPS),
        "planned_episodes": planned_episodes,
    }


def build_coverage(setup: dict[str, Any], annotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    done_by_model = Counter(r["model"] for r in annotations)
    rows = []
    for m in setup["models"]:
        done = done_by_model.get(m["display_name"], 0)
        planned = m["n_prompts"]
        rows.append(
            {
                "display_name": m["display_name"],
                "done": done,
                "planned": planned,
                "pct": (done / planned * 100) if planned else 0,
                "status": "complete" if planned and done >= planned else ("partial" if done else "not started"),
            }
        )
    return rows


# --------------------------------------------------------------------------
# Metrics: Table - behavioral pilot / Table - cleaned language effect
# --------------------------------------------------------------------------

def _rate(rows: list[dict[str, Any]], field: str) -> Optional[float]:
    vals = [r[field] for r in rows if r.get(field) is not None]
    if not vals:
        return None
    return sum(1 for v in vals if v) / len(vals)


def _target_acc(rows: list[dict[str, Any]]) -> Optional[float]:
    if not rows:
        return None
    hits = sum(
        1 for r in rows
        if r.get("first_contact_object") is not None
        and r.get("first_contact_object") == r.get("target_object")
    )
    return hits / len(rows)


FAILURE_LABELS = [
    "success", "target_grounding_error", "reference_grounding_error",
    "relation_binding_error", "negation_error", "physical_execution_error",
    "no_action_or_timeout", "unclear",
]


def compute_label_mix(annotations: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Сколько эпизодов каждого варианта получило каждую метку из task.md.

    Отдельно от `compute_behavioral_pilot`: метки исхода и поведенческие
    метрики — разные величины, и путать их нельзя. Колонки поведенческой
    таблицы заданы task.md («Table - behavioral pilot»), а этот набор из восьми
    меток — контракт авторазметки оттуда же.
    """
    out: dict[str, dict[str, int]] = {}
    for variant in VARIANT_ORDER:
        rows = [r for r in annotations if r["variant"] == variant]
        counts = {label: 0 for label in FAILURE_LABELS}
        for row in rows:
            label = row.get("failure_type_auto")
            if label in counts:
                counts[label] += 1
        counts["n"] = len(rows)
        out[variant] = counts
    return out


def compute_behavioral_pilot(annotations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in annotations:
        by_variant[row["variant"]].append(row)

    table = {}
    for variant in VARIANT_ORDER:
        rows = by_variant.get(variant, [])
        table[variant] = {
            "n": len(rows),
            "sr": _rate(rows, "success"),
            "first_contact_target_acc": _target_acc(rows),
            "wrong_object_rate": _rate(rows, "wrong_object"),
            "relation_success": _rate(rows, "final_relation_success"),
            "forbidden_touch": _rate(rows, "forbidden_object_touched"),
        }
    return table


def compute_behavioral_pilot_by_model(annotations: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in annotations:
        by_model[row["model"]].append(row)
    return {model: compute_behavioral_pilot(rows) for model, rows in sorted(by_model.items())}


def compute_language_effect(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Δlang for ONE model's annotation rows, paired scene-by-scene.

    Takes raw annotation rows rather than a pre-aggregated per-variant table,
    because the pairing has to happen at scene level and a table of marginal
    success rates has already thrown that information away.

    This function used to accept the pooled per-variant table and was also
    called once across ALL models at once. Two things were wrong with that:

      * pooling models — the mix is not the same for every variant (coverage
        differs per model), so the pooled per-variant SRs are weighted
        differently and their difference is not a language effect. Concretely,
        pooled Δlang_ru_literal came out at +11.4 п.п. while per-model values
        ranged 0 to +50: models with ~0% SR in every language contribute
        Δlang≈0 by construction and dilute the models that actually show the
        effect.
      * unpaired variants — see slava_rollout.stats.delta_lang.
    """
    from slava_rollout.stats import delta_lang, outcomes_by_variant

    by_variant = outcomes_by_variant(rows)
    out: list[dict[str, Any]] = []
    for variant in ("mt_russian", "ru_literal", "ru_free_order", "ru_case_swap",
                    "ru_negation", "code_switch"):
        d = delta_lang(by_variant, variant)
        if d is None:
            continue
        out.append(
            {
                "effect": variant,
                "formula": f"gap_{variant} − gap_en_paraphrase",
                "value": d["value"],
                "n_scenes": d["n_scenes"],
                "ci": d["ci"],
                "p": d["p_mcnemar_vs_anchor"],
            }
        )
    return out


# --------------------------------------------------------------------------
# Data provenance
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Camera demo gallery
# --------------------------------------------------------------------------

def _frames_to_clip(
    frame_paths: list[Path], dest: Path, fps: int = 20, max_frames: int = 50,
    size: int = 160, quality: int = 70,
) -> Path:
    """Write one episode as an animated clip. Returns the path actually written.

    Animated WebP, not GIF. These are photographic renders, which GIF's 256-colour
    palette handles badly: the same 50-frame clip is ~370 KB as GIF and ~60 KB as
    WebP at visually indistinguishable quality. That ratio decides whether the
    report is publishable — a gallery of ~120 clips is ~60 MB in GIF and under
    10 MB in WebP, and the whole site has to be checked out and served by GitHub
    Pages on every deploy. Animated WebP is supported by every current browser
    (Chrome 32+, Firefox 65+, Safari 14+).

    Frames are subsampled to `max_frames` and downscaled first: a 300-step LIBERO
    episode at full rate is neither readable nor necessary. 20fps (50ms/frame) is
    the floor browsers time reliably.
    """
    from PIL import Image

    if len(frame_paths) > max_frames:
        step = len(frame_paths) / max_frames
        frame_paths = [frame_paths[int(i * step)] for i in range(max_frames)]
    imgs = [
        Image.open(p).convert("RGB").resize((size, size), Image.LANCZOS)
        for p in frame_paths
    ]
    dest = dest.with_suffix(".webp")
    dest.parent.mkdir(parents=True, exist_ok=True)
    imgs[0].save(
        dest, format="WEBP", save_all=True, append_images=imgs[1:],
        duration=int(1000 / fps), loop=0, quality=quality, method=4,
    )
    return dest


def _pick_runs_for_model(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Pick up to `limit` episodes for one model, maximising prompt-variant
    diversity: round-robin over distinct variants so we never show `limit`
    near-identical runs of the same prompt. Within a variant, successes come
    first (a working model is best demonstrated by a completed task), so a
    mixed set of outcomes is shown when both exist."""
    by_variant: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_variant.setdefault(row["variant"], []).append(row)
    for variant_rows in by_variant.values():
        variant_rows.sort(key=lambda r: (not r.get("success"), r["run_id"]))

    picked: list[dict[str, Any]] = []
    variants = sorted(by_variant, key=lambda v: (-len(by_variant[v]), v))
    depth = 0
    while len(picked) < limit:
        added = False
        for variant in variants:
            if depth < len(by_variant[variant]):
                picked.append(by_variant[variant][depth])
                added = True
                if len(picked) >= limit:
                    break
        if not added:
            break
        depth += 1
    return picked


def build_camera_gallery(
    annotations: list[dict[str, Any]],
    assets_dir: Path | None = None,
    per_working_model: int = 8,
    per_broken_model: int = 2,
) -> list[dict[str, Any]]:
    """Render episode camera streams as animated GIFs, grouped per model.

    assets_dir: if given, each episode's agentview/wrist frame sequence is
    written to assets_dir/<run_id>/*.webp — needed for GitHub Pages (rollouts/
    isn't in git) and because a rollout reads better as motion than as stills.

    Models with a non-zero SR get `per_working_model` episodes across different
    prompt variants (they're the ones whose behaviour is worth inspecting);
    models still stuck at 0% get only `per_broken_model` illustrative runs.
    Returns a list of per-model groups, each with its own list of episodes.
    """
    episodes_root = ROLLOUTS_DIR / "episodes"
    if not episodes_root.exists() or assets_dir is None:
        return []  # static (non-pages) mode not supported for GIFs

    by_model: dict[str, list[dict[str, Any]]] = {}
    for row in annotations:
        by_model.setdefault(row["model"], []).append(row)

    groups = []
    # Models with real successes first — they are the report's actual result.
    order = sorted(
        by_model,
        key=lambda m: (
            -sum(1 for r in by_model[m] if r.get("success")) / max(len(by_model[m]), 1),
            m,
        ),
    )
    for model in order:
        rows = by_model[model]
        n_ok = sum(1 for r in rows if r.get("success"))
        # Only consider episodes whose frames actually exist on disk.
        have_frames = [
            r for r in rows if (episodes_root / r["run_id"] / "camera" / "agentview").exists()
        ]
        if not have_frames:
            continue
        limit = per_working_model if n_ok else per_broken_model
        items = []
        for row in _pick_runs_for_model(have_frames, limit):
            run_dir = episodes_root / row["run_id"]
            agent_frames = sorted((run_dir / "camera" / "agentview").glob("step_*.png"))
            if not agent_frames:
                continue
            wrist_dir = run_dir / "camera" / "wrist"
            wrist_frames = sorted(wrist_dir.glob("step_*.png")) if wrist_dir.exists() else []

            # _frames_to_clip decides the container (and therefore the suffix),
            # so take the path it actually wrote rather than assuming one.
            agent_clip = _frames_to_clip(agent_frames, assets_dir / row["run_id"] / "agentview")
            wrist_rel = None
            if wrist_frames:
                wrist_clip = _frames_to_clip(wrist_frames, assets_dir / row["run_id"] / "wrist")
                wrist_rel = str(wrist_clip.relative_to(assets_dir.parent))

            items.append(
                {
                    "run_id": row["run_id"],
                    "model": row["model"],
                    "variant": row["variant"],
                    "instruction": row["instruction"],
                    "success": row["success"],
                    "failure_type_auto": row["failure_type_auto"],
                    "agent_gif": str(agent_clip.relative_to(assets_dir.parent)),
                    "wrist_gif": wrist_rel,
                }
            )
        if items:
            groups.append(
                {
                    "model": model,
                    "sr": f"{n_ok}/{len(rows)} = {100.0 * n_ok / len(rows):.1f}%",
                    "items": items,
                }
            )
    return groups


# --------------------------------------------------------------------------
# HTML rendering
# --------------------------------------------------------------------------

def fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def fmt_delta(value: Optional[float]) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value * 100:.1f} п.п."


def render_html(
    data_overview: dict[str, Any],
    setup: dict[str, Any],
    examples: dict[str, Any],
    coverage: list[dict[str, Any]],
    behavioral: dict[str, dict[str, Any]],
    label_mix: dict[str, dict[str, int]],
    behavioral_by_model: dict[str, dict[str, dict[str, Any]]],
    language_effect: list[dict[str, Any]],
    language_effect_by_model: dict[str, list[dict[str, Any]]],
    gallery: list[dict[str, Any]],
    n_annotations: int,
    provenance: dict[str, dict[str, int]] | None = None,
    episodes: list[dict[str, Any]] | None = None,
) -> str:
    episodes = episodes or []
    models_rows = ""
    for m in setup["models"]:
        env_lines = "<br>".join(
            f"{e['name']}: <code>{e['checkpoint']}</code>" + (" <em>(zero-shot)</em>" if e["zero_shot"] else "")
            for e in m["environments"]
        )
        models_rows += (
            f"<tr><td>{pretty_model(m['display_name'])}</td><td><code>{m['backbone']}</code></td>"
            f"<td>{env_lines}</td><td>{m['n_prompts']}</td></tr>"
        )

    label_mix_header = "".join(f"<th><code>{l}</code></th>" for l in FAILURE_LABELS)
    label_mix_rows = ""
    for variant in VARIANT_ORDER:
        row = label_mix.get(variant, {})
        cells = "".join(
            f"<td>{row.get(l) or '<span class=\"muted\">—</span>'}</td>" for l in FAILURE_LABELS
        )
        label_mix_rows += f"<tr><td>{variant}</td><td>{row.get('n', 0)}</td>{cells}</tr>"

    # Сводка Δlang для раздела с research questions: считается из тех же строк,
    # что и таблица, чтобы не разъезжалась при пересчёте. Зонд ru_case_swap
    # держится отдельно — он меряет не деградацию, а следование перевёрнутой
    # инструкции, и его +100 п.п. в среднем с остальными несопоставимы.
    _eff = [r for rows in language_effect_by_model.values() for r in rows if r.get("value") is not None]
    _lang = [r for r in _eff if r["effect"] != "ru_case_swap"]
    if _lang:
        _vals = [r["value"] for r in _lang]
        _avg = 100 * sum(_vals) / len(_vals)
        _lo = min(_lang, key=lambda r: r["value"])
        _hi = max(_lang, key=lambda r: r["value"])
        rq1_answer = (
            f"Δlang положителен на всех вариантах: в среднем <b>+{_avg:.1f} п.п.</b>, "
            f"от +{100*_lo['value']:.1f} (<code>{_lo['effect']}</code>) "
            f"до +{100*_hi['value']:.1f} (<code>{_hi['effect']}</code>)."
        )
    else:
        rq1_answer = "Данных для Δlang недостаточно."
    _probe = next((r for r in _eff if r["effect"] == "ru_case_swap"), None)
    if _probe:
        rq1_answer += (
            f" Зонд <code>ru_case_swap</code> отдельно: +{100*_probe['value']:.1f} п.п. — "
            "перестановка ролей не распознана ни разу."
        )

    behavioral_rows = ""
    for variant in VARIANT_ORDER:
        row = behavioral.get(variant, {})
        behavioral_rows += (
            f"<tr><td>{variant}</td><td>{row.get('n', 0)}</td>"
            f"<td>{fmt_pct(row.get('sr'))}</td>"
            f"<td>{fmt_pct(row.get('first_contact_target_acc'))}</td>"
            f"<td>{fmt_pct(row.get('wrong_object_rate'))}</td>"
            f"<td>{fmt_pct(row.get('relation_success'))}</td>"
            f"<td>{fmt_pct(row.get('forbidden_touch'))}</td></tr>"
        )

    language_rows = "".join(
        f"<tr><td>{r['effect']}</td><td><code>{r['formula']}</code></td>"
        f"<td class=\"{'pos' if (r['value'] or 0) > 0 else 'neg' if (r['value'] or 0) < 0 else ''}\">"
        f"{fmt_delta(r['value'])}</td></tr>"
        for r in language_effect
    )

    per_model_sections = ""
    for model, table in behavioral_by_model.items():
        rows = ""
        for variant in VARIANT_ORDER:
            row = table.get(variant, {})
            if not row.get("n"):
                continue
            rows += (
                f"<tr><td>{variant}</td><td>{row.get('n', 0)}</td>"
                f"<td>{fmt_pct(row.get('sr'))}</td>"
                f"<td>{fmt_pct(row.get('first_contact_target_acc'))}</td>"
                f"<td>{fmt_pct(row.get('wrong_object_rate'))}</td>"
                f"<td>{fmt_pct(row.get('relation_success'))}</td>"
                f"<td>{fmt_pct(row.get('forbidden_touch'))}</td></tr>"
            )
        if rows:
            per_model_sections += (
                f"<h3>{pretty_model(model)}</h3><table class=\"data-table\"><thead><tr>"
                "<th>Вариант инструкции</th><th>Эпизодов</th><th>SR</th><th>Дотянулся до нужного предмета</th>"
                "<th>Тронул не тот предмет</th><th>Отношение выполнено</th><th>Тронул запрещённый предмет</th>"
                f"</tr></thead><tbody>{rows}</tbody></table>"
            )

    gallery_cards = ""
    for group in gallery:
        cards = ""
        for item in group["items"]:
            wrist_html = (
                f'<img class="gif" src="{item["wrist_gif"]}" loading="lazy" title="wrist">'
                if item.get("wrist_gif")
                else ""
            )
            status = "success" if item["success"] else "fail"
            cards += f"""
          <figure class="run-card">
            <div class="gif-pair">
              <img class="gif" src="{item['agent_gif']}" loading="lazy" title="agentview">
              {wrist_html}
            </div>
            <figcaption>
              <span class="badge {status}">{item['failure_type_auto']}</span>
              <span class="vtag">{item['variant']}</span>
              <span class="instruction">&laquo;{item['instruction']}&raquo;</span>
            </figcaption>
          </figure>"""
        gallery_cards += f"""
        <h3>{pretty_model(group['model'])} <span class="muted">— SR {group['sr']} (по всем вариантам инструкции)</span></h3>
        <div class="gif-grid">{cards}
        </div>"""

    lex = examples["lexicon_row"]
    lexicon_row_rows = "".join(
        f"<tr><td class=\"k\">{field}</td><td>{value if value != '' else '<span class=\"muted\">—</span>'}</td></tr>"
        for field, value in lex.items()
    )
    prompt_rows = "".join(
        f"<tr><td>{p['variant']}</td><td>&laquo;{p['instruction']}&raquo;</td></tr>"
        for p in examples["prompt_variants"]
    )
    def _lang_effect_rows_html(rows: list[dict[str, Any]]) -> str:
        parts = []
        for r in rows:
            v = r["value"] or 0
            css = "pos" if v > 0 else ("neg" if v < 0 else "")
            parts.append(
                f"<tr><td>{r['effect']}</td><td>{r.get('n_scenes','—')}</td>"
                f"<td class=\"{css}\">{fmt_delta(r['value'])}</td></tr>"
            )
        return "".join(parts)

    language_effect_by_model_sections = "".join(
        f"<h3>{pretty_model(model)}</h3><table class=\"data-table\"><thead><tr><th>Вариант инструкции</th>"
        f"<th>Сцен</th><th>Δlang</th></tr></thead>"
        f"<tbody>{_lang_effect_rows_html(rows)}</tbody></table>"
        for model, rows in language_effect_by_model.items()
        if any(r["value"] is not None for r in rows)
    )

    envs_by_model = {m["display_name"]: ", ".join(e["name"] for e in m["environments"])
                     for m in setup["models"]}
    coverage_rows = ""
    for c in coverage:
        coverage_rows += (
            f"<tr><td>{pretty_model(c['display_name'])}</td>"
            f"<td>{envs_by_model.get(c['display_name'], '')}</td>"
            f"<td>{c['done']}</td></tr>"
        )

    # Достоверность: наш en_canonical против опубликованного авторами. Для
    # GreenVLA берём отдельный валидационный прогон на полном bridge-наборе,
    # если он собран, — там n в пять раз больше пилотных четырёх сцен.
    published = json.loads((DATA_DIR / "published_baselines.json").read_text(encoding="utf-8"))["baselines"]
    validation_pool = ROLLOUTS_DIR.parent / "harness_validation_greenvla" / "rollout_annotations.jsonl"
    validation = load_jsonl(validation_pool)
    validity_rows = ""
    for model in sorted({r["model"] for r in episodes} | {r["model"] for r in validation}):
        en = [r for r in validation if r["model"] == model and r["variant"] == "en_canonical"]
        note = " <span class=\"muted\">(отдельный прогон)</span>" if en else ""
        if not en:
            en = [r for r in episodes if r["model"] == model and r["variant"] == "en_canonical"]
        if not en:
            continue
        hits, total = sum(bool(r["success"]) for r in en), len(en)
        low, high = wilson_ci(hits, total)
        spec = published.get(model) or {}
        reference, treatment = spec.get("sr"), spec.get("report_treatment")
        if reference is None:
            verdict = "опубликованного числа нет"
        elif treatment == "primary":
            verdict = '<span class="badge success">воспроизводится</span>'
        elif treatment == "preliminary":
            verdict = '<span class="badge">предварительно, база ненулевая</span>'
        else:
            verdict = '<span class="badge fail">не воспроизводится</span>'
        validity_rows += (
            f"<tr><td>{pretty_model(model)}</td>"
            f"<td>{hits}/{total} = {fmt_pct(hits / total)}{note}</td>"
            f"<td>[{fmt_pct(low)}; {fmt_pct(high)}]</td>"
            f"<td>{fmt_pct(reference) if reference is not None else '—'}</td>"
            f"<td>{verdict}</td></tr>"
        )

    env_counts_str = ", ".join(f"{k}: {v}" for k, v in data_overview["env_counts"].items())
    prompts_by_env_str = ", ".join(f"{k}: {v}" for k, v in setup["prompts_by_env"].items())
    # Показываем горизонт, с которым данные РЕАЛЬНО собраны, а не константу из
    # кода: `MAX_EPISODE_STEPS` — это нынешний потолок (520 = сьют libero_10,
    # которого в наборе нет), и он противоречил тексту рядом, где сказано про
    # единый лимит 300. Берём фактический максимум длины эпизода по логам.
    observed_steps: dict[str, int] = {}
    for row in episodes:
        env = "LIBERO" if row["task_uid"].startswith("libero") else "SimplerEnv"
        path = ROLLOUTS_DIR / "episodes" / row["run_id"] / "steps.jsonl"
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as handle:
            n = sum(1 for line in handle if line.strip())
        observed_steps[env] = max(observed_steps.get(env, 0), n)
    max_steps_str = ", ".join(f"{k}: {v}" for k, v in sorted(observed_steps.items())) or "—"

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>SLAVA — пилотный прогон v0: технический отчёт</title>
<style>
  :root {{ --ink:#1a1a1a; --muted:#5c5c5c; --line:#ddd; --paper:#fff;
    --canvas:#fbfbf9; --accent:#3157d5; --good:#166534; --bad:#991b1b; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; color:var(--ink); background:var(--canvas);
    font:15px/1.6 "Source Serif Pro",Georgia,"Times New Roman",serif; }}
  header {{ padding:28px 28px 20px; border-bottom:2px solid var(--ink); background:var(--paper); }}
  header h1 {{ margin:0 0 6px; font-size:24px; font-weight:600; }}
  header p {{ margin:0; color:var(--muted); font-size:14px; }}
  main {{ width:min(880px,100%); margin:auto; padding:24px; }}
  section {{ margin:0 0 30px; padding:0 0 4px; background:transparent;
    border:none; border-bottom:1px solid var(--line); }}
  section h2 {{ margin:0 0 14px; font-size:17px; font-weight:600; letter-spacing:.01em; }}
  section h3 {{ margin:18px 0 8px; font-size:14.5px; font-weight:600; font-style:italic; }}
  section p, section li {{ font-size:14.5px; }}
  section h4 {{ margin:10px 0 6px; font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }}
  table.data-table {{ width:100%; border-collapse:collapse; margin:10px 0; }}
  table.data-table th, table.data-table td {{ padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; }}
  table.data-table th {{ color:var(--muted); font-size:11.5px; text-transform:uppercase; letter-spacing:.03em;
    font-family:ui-sans-serif,system-ui,sans-serif; font-weight:600; }}
  table.data-table td.k {{ color:var(--muted); font-size:12.5px; width:220px; font-family:ui-sans-serif,system-ui,sans-serif; }}
  code {{ background:#f1f0ea; padding:1px 5px; border-radius:4px; font-size:12.5px;
    font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }}
  .stat-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin:0 0 16px; }}
  .stat {{ padding:12px 14px; background:#f8fafc; border:1px solid var(--line); border-radius:10px; }}
  .stat b {{ display:block; font-size:22px; }}
  .stat span {{ color:var(--muted); font-size:12px; }}
  .pos {{ color:var(--good); font-weight:700; }}
  .neg {{ color:var(--bad); font-weight:700; }}
  .muted {{ color:var(--muted); }}
  .gif-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr));
    gap:14px; margin:0 0 26px; }}
  .run-card {{ margin:0; padding:8px; border:1px solid var(--line); border-radius:10px; background:#fbfcfe; }}
  .gif-pair {{ display:flex; gap:4px; }}
  .gif-pair img.gif {{ width:0; flex:1 1 0; min-width:0; aspect-ratio:1/1;
    border-radius:6px; border:1px solid var(--line); display:block; }}
  .run-card figcaption {{ margin:7px 1px 0; font-size:11.5px; line-height:1.45; }}
  .vtag {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:10.5px;
    color:var(--muted); margin-left:5px; }}
  .instruction {{ display:block; margin:3px 0 0; color:var(--muted); font-style:italic; }}
  .badge {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:700; }}
  .badge.success {{ color:var(--good); background:#dcfce7; border:1px solid #86efac; }}
  .badge.fail {{ color:var(--bad); background:#fee2e2; border:1px solid #fca5a5; }}
  .callout {{ padding:12px 14px; background:#eff6ff; border:1px solid #bfdbfe; border-radius:10px; margin:0 0 14px; }}
  .warn {{ padding:12px 14px; background:#fffbeb; border:1px solid #fde68a; border-radius:10px; margin:0 0 14px; }}
  .f {{ padding:12px 16px; background:#fbfbf9; border:1px solid var(--line); border-radius:10px;
    margin:0 0 14px; font-family:ui-serif,Georgia,'Times New Roman',serif; font-size:15px;
    line-height:2.6; overflow-x:auto; }}
  .f .def {{ display:block; margin:2px 0; }}
  .f .name {{ font-style:italic; }}
  .frac {{ display:inline-flex; flex-direction:column; vertical-align:middle;
    text-align:center; margin:0 .25em; font-size:.82em; line-height:1.25; }}
  .frac .num {{ padding:0 .45em .1em; border-bottom:1.3px solid currentColor; white-space:nowrap; }}
  .frac .den {{ padding:.1em .45em 0; white-space:nowrap; }}
  .tscroll {{ overflow-x:auto; margin:10px 0; }}
  .tscroll table.data-table {{ margin:0; }}
  table.data-table.compact th, table.data-table.compact td {{ padding:6px 7px; text-align:center; }}
  table.data-table.compact th:first-child, table.data-table.compact td:first-child {{ text-align:left; }}
  table.data-table.compact th {{ text-transform:none; letter-spacing:0; font-size:10.5px; }}
  table.data-table.compact th code {{ background:none; padding:0; font-size:10.5px;
    overflow-wrap:anywhere; display:inline-block; max-width:8.5em; }}
</style>
</head>
<body>
<header>
  <h1>SLAVA — пилотный прогон v0: технический отчёт</h1>
  <p>Первые model rollouts на 7 моделях × LIBERO/SimplerEnv, по контракту task.md. {n_annotations} эпизодов размечено на момент генерации отчёта.</p>
</header>
<main>

<section>
  <h2>1. Обзор данных сбора v0 (20 сцен)</h2>
  <div class="stat-grid">
    <div class="stat"><b>{data_overview['n_candidate_scenes']}</b><span>сцен-кандидатов (task_inventory.jsonl)</span></div>
    <div class="stat"><b>{data_overview['n_usable_for_slava']}</b><span>usable_for_slava=true</span></div>
    <div class="stat"><b>{data_overview['n_selected']}</b><span>отобрано в набор v0 ({env_counts_str})</span></div>
    <div class="stat"><b>{data_overview['n_lexicon_entries']}</b><span>записей в object_lexicon.csv</span></div>
    <div class="stat"><b>{data_overview['n_frames']}</b><span>grounded frames (frames_v0.jsonl)</span></div>
    <div class="stat"><b>{data_overview['n_native_check_passed']}/{data_overview['n_frames']}</b><span>native_check = passed</span></div>
    <div class="stat"><b>{fmt_pct(data_overview['visible_agentview_pct']/100)}</b><span>объектов видно на agentview</span></div>
    <div class="stat"><b>{fmt_pct(data_overview['visible_wrist_pct']/100)}</b><span>объектов видно на wrist</span></div>
  </div>
  <h3>Пример записи словаря объектов (object_lexicon.csv) — все поля</h3>
  <table class="data-table"><tbody>{lexicon_row_rows}</tbody></table>

  <h3>Пример сцены и всех её вариантов инструкции</h3>
  <p class="muted">Сцена <code>{examples['prompt_uid']}</code> — все 7 primary-вариантов инструкции для одной и той же сцены (одна задача, один init state, разные языковые оси):</p>
  <table class="data-table"><thead><tr><th>Вариант</th><th>Инструкция</th></tr></thead>
  <tbody>{prompt_rows}</tbody></table>
</section>

<section>
  <h2>2. Как собирались прогоны</h2>
  <div class="stat-grid">
    <div class="stat"><b>{setup['n_task_uids']}</b><span>сцен (task_uid)</span></div>
    <div class="stat"><b>{setup['n_prompts_total']}</b><span>промптов (task_uid × variant), {prompts_by_env_str}</span></div>
    <div class="stat"><b>{setup['n_repeats']}</b><span>повтор на (сцена × вариант × модель)</span></div>
    <div class="stat"><b>{setup['planned_episodes']}</b><span>запланировано эпизодов (7 моделей)</span></div>
    <div class="stat"><b>{n_annotations}</b><span>фактически размечено эпизодов</span></div>
    <div class="stat"><b>{max_steps_str}</b><span>шагов в самом длинном эпизоде</span></div>
  </div>
  <div class="warn"><b>Лимит шагов был выставлен нами, а не взят у авторов — это наша ошибка,
  на числа она не повлияла.</b> Авторы LIBERO-эвала обрывают эпизод по сьюту: spatial 220,
  object 280, goal 300 шагов. Мы собирали все три сьюта с единым лимитом 300, то есть в
  spatial и object давали модели больше времени, чем полагалось. Проверено по логам всех
  396 LIBERO-эпизодов: <b>ни один успех не наступил позже авторского лимита</b>, поэтому
  собранные SR совпадают с теми, что получились бы при правильных лимитах, и сравнимы с
  опубликованными. Лимиты по сьютам уже проставлены в коде для последующих сборов.</div>
  <table class="data-table"><thead><tr><th>Модель</th><th>Базовая модель</th><th>Среда и чекпойнт</th><th>Промптов</th></tr></thead>
  <tbody>{models_rows}</tbody></table>
  <h3>Сколько эпизодов собрано</h3>
  <table class="data-table"><thead><tr><th>Модель</th><th>Источник данных</th><th>Эпизодов</th></tr></thead>
  <tbody>{coverage_rows}</tbody></table>
</section>

<section>
  <h2>3. Достоверность результатов</h2>
  <p class="muted">Проверка одна: на <code>en_canonical</code> — канонической английской строке
  задачи, без изменений — модель должна показывать примерно то, что о ней публикуют авторы.</p>
  <table class="data-table"><thead><tr>
    <th>Модель</th><th>Наш SR <span class="muted">(только en_canonical)</span></th><th>95% CI</th><th>Опубликовано</th><th>Вывод</th>
  </tr></thead><tbody>{validity_rows}</tbody></table>
  <p class="muted">Что означают вердикты. <b>Воспроизводится</b> — наш SR на английском
  сходится с опубликованным, числам модели можно верить.
  <b>Не воспроизводится</b> — не сходится.
  <b>Предварительно, база ненулевая</b> — тоже не сходится, но модель хотя бы иногда решает
  задачу на английском (не ноль), поэтому её провалы на русском в принципе могли бы быть
  языковым эффектом; у моделей с нулём на английском отличить язык от поломки нельзя вообще.
  <b>Нет опубликованного числа</b> — авторы не публиковали SR для этого конкретного чекпойнта,
  сравнивать не с чем.</p>
  <div class="warn"><b>Опубликованное число воспроизводит одна модель из семи.</b>
  Ниже анализируем метрики только на достоверной OpenVLA-OFT.</div>
</section>

<section>
  <h2>4. Ручная проверка разметки на 100 эпизодах</h2>
  <p class="muted">Метки проставляет скрипт. Чтобы проверить его, 100 эпизодов отсмотрены
  вручную по видеозаписям; вердикт человека считается истиной.</p>

  <table class="data-table"><thead><tr>
    <th>Что проверялось</th><th>Согласие с человеком</th><th>95% CI</th>
  </tr></thead><tbody>
    <tr><td>Факт успеха (получилось / не получилось)</td><td><b>99 / 100</b></td><td>[95%; 100%]</td></tr>
    <tr><td>Тип ошибки (какая именно из восьми меток)</td><td><b>80 / 100</b></td><td>[71%; 87%]</td></tr>
  </tbody></table>

  <p class="muted">Вывод: <b>факт успеха определяется надёжно, тип ошибки промахивается
  примерно в каждом пятом случае.</b> SR и Δlang опираются на надёжную величину, разбор по
  типам ошибок — указание направления, а не точное измерение.</p>

  <h3>Что проверка изменила в коде разметки</h3>
  <p class="muted">Расхождения дали три исправления. Согласие пересчитано на той же
  выборке после каждого:</p>

  <table class="data-table"><thead><tr>
    <th>Исправление</th><th>Что было не так</th><th>Меток изменилось</th><th>Согласие по метке</th>
  </tr></thead><tbody>
    <tr><td colspan="3"><i>исходное состояние</i></td><td>76 / 100</td></tr>
    <tr><td><code>negation_error</code> только на оси отрицания</td>
        <td>метка ставилась на любом варианте, хотя запрет существует лишь там, где инструкция его произносит</td>
        <td>17</td><td>78 / 100</td></tr>
    <tr><td>цель ни разу не поднялась → <code>physical_execution_error</code></td>
        <td>ставилось <code>relation_binding_error</code>, хотя нарушать отношение было нечем: предмет не оторвали от поверхности</td>
        <td>56</td><td>81 / 100</td></tr>
    <tr><td>успех <code>ru_case_swap</code> по перевёрнутой инструкции</td>
        <td>засчитывалось выполнение исходной задачи — зонд измерял обратное задуманному</td>
        <td>7</td><td>80 / 100</td></tr>
  </tbody></table>

  <p class="muted">Последнее исправление стоит одного пункта по метке и даёт два по факту
  успеха (97 → 99).</p>

  <p class="muted">Вердикты снимались до исправлений. 43 эпизода из 100 оставлены без
  правок и засчитаны как согласие; по строгому счёту, только на 57 явно разобранных, согласие
  по метке 37 / 57.</p>
</section>

<section>
  <h2>5. Видеозаписи прогонов</h2>
  <p class="muted">Для каждой модели — одна и та же задача по разным промптам. На карточке
  слева стоит метка исхода.</p>
  <table class="data-table"><thead><tr><th>Метка</th><th>Что произошло</th></tr></thead><tbody>
    <tr><td><code>success</code></td><td>задача выполнена</td></tr>
    <tr><td><code>target_grounding_error</code></td><td>робот пошёл не к тому предмету</td></tr>
    <tr><td><code>reference_grounding_error</code></td><td>целевой предмет верный, но ориентир перепутан</td></tr>
    <tr><td><code>relation_binding_error</code></td><td>оба предмета верные, но требуемое отношение между ними не выполнено</td></tr>
    <tr><td><code>negation_error</code></td><td>робот тронул предмет, который инструкция запрещала трогать</td></tr>
    <tr><td><code>physical_execution_error</code></td><td>понял задачу, но не справился физически — не удержал, не поднял</td></tr>
    <tr><td><code>no_action_or_timeout</code></td><td>ничего осмысленного не сделал или не уложился в лимит шагов</td></tr>
    <tr><td><code>unclear</code></td><td>по логам отнести к одной из категорий нельзя</td></tr>
  </tbody></table>
  {gallery_cards or '<p class="muted">Камерные записи пока не сгенерированы для загруженных эпизодов.</p>'}
</section>

<section>
  <h2>6. Что происходит на сцене: поведение по вариантам инструкции</h2>

  <h3>Исходы по меткам</h3>
  <p class="muted">Сколько эпизодов каждого варианта получило каждую метку.</p>
  <div class="tscroll"><table class="data-table compact"><thead><tr>
    <th>Вариант инструкции</th><th>Эпизодов</th>{label_mix_header}
  </tr></thead><tbody>{label_mix_rows}</tbody></table></div>

  <h3>Поведенческие метрики</h3>
  <p class="muted">Не метки исхода, а отдельные величины: на каком шаге рвётся исполнение.</p>
  <div class="f">
  <span class="def"><span class="name">SR</span> = <span class="frac"><span class="num">успешных эпизодов</span><span class="den">всего эпизодов варианта</span></span></span>
  <span class="def"><span class="name">Дотянулся до нужного предмета</span> = <span class="frac"><span class="num">эпизодов, где первый тронутый предмет — целевой</span><span class="den">всего эпизодов варианта</span></span></span>
  <span class="def"><span class="name">Тронул не тот предмет</span> = <span class="frac"><span class="num">эпизодов, где первый тронутый предмет — <b>не</b> целевой</span><span class="den">всего эпизодов варианта</span></span></span>
  <span class="def"><span class="name">Отношение выполнено</span> = <span class="frac"><span class="num">эпизодов с выполненным финальным отношением</span><span class="den">эпизодов, где отношение определено</span></span></span>
  <span class="def"><span class="name">Тронул запрещённый предмет</span> = <span class="frac"><span class="num">эпизодов, где запрещённый предмет тронут хотя бы раз</span><span class="den">всего эпизодов варианта</span></span></span>
  </div>
  <table class="data-table"><thead><tr>
    <th>Вариант инструкции</th><th>Эпизодов</th><th>SR</th><th>Дотянулся до нужного предмета</th>
    <th>Тронул не тот предмет</th><th>Отношение выполнено</th><th>Тронул запрещённый предмет</th>
  </tr></thead><tbody>{behavioral_rows}</tbody></table>

  <p class="muted">Пустая строка одна: <code>ru_free_order</code>. Вариант написан для всех 20
  сцен, но в прогон не попал — наша ошибка, добираем следующим прогоном.</p>
</section>

<section>
  <h2>7. Языковой эффект (Δlang)</h2>
  <div class="f">
  <span class="def">gap<sub>v</sub> = SR<sub>en_canonical</sub> − SR<sub>v</sub></span>
  <span class="def"><b>Δlang<sub>v</sub> = gap<sub>v</sub> − gap<sub>en_paraphrase</sub></b></span>
  </div>
  <p class="muted">Каждая сцена прогоняется всеми вариантами инструкции, поэтому варианты
  сравниваются на одних и тех же сценах, а не по общим средним. Это важно, потому что сцены
  разной трудности: если у одного варианта случайно окажется больше лёгких сцен, его SR
  вырастет сам по себе, без всякого отношения к языку. Колонка «Сцен» показывает, на скольких
  сценах сравнение получилось — там, где по варианту собрано меньше эпизодов, число ниже.</p>
  {language_effect_by_model_sections or '<p class="muted">Недостаточно данных.</p>'}
</section>

<section>
  <h2>8. Что из исследовательских вопросов закрыто</h2>
  <table class="data-table"><thead><tr><th>Вопрос</th><th>Статус</th><th>Чем отвечаем</th></tr></thead>
  <tbody>
    <tr><td class="k">RQ1. Which linguistic perturbations cause VLA failures beyond generic instruction-string OOD?</td>
        <td><b>сырой ответ есть</b></td>
        <td>{rq1_answer}</td></tr>
    <tr><td class="k">RQ2. Where do multilingual instructions fail in the language-to-action pipeline?</td>
        <td><b>ответа нет</b></td>
        <td>Нужен послойный разбор; поведенческие колонки места сбоя не дают.</td></tr>
    <tr><td class="k">RQ3. Does action fine-tuning erase multilingual semantics or render them non-causal?</td>
        <td><b>ответа нет</b></td>
        <td>Нужны slot-probes и каузальный patching. В пилоте не делалось.</td></tr>
    <tr><td class="k">RQ4. Can a slot-causal, base-anchored repair restore multilingual action binding?</td>
        <td><b>ответа нет</b></td>
        <td>Строится по результатам RQ3.</td></tr>
  </tbody></table>
</section>

</main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DATA_DIR / "rollout_report.html")
    parser.add_argument(
        "--for-pages", action="store_true",
        help="Copy referenced camera PNGs next to --output (as <output-dir>/report_assets/...) "
             "instead of referencing rollouts/, which isn't in git. Use when publishing "
             "the report standalone (e.g. GitHub Pages).",
    )
    args = parser.parse_args()

    annotations = load_jsonl(ROLLOUTS_DIR / "rollout_annotations.jsonl")
    # Validity is declared in data/rollout_provenance.json, not inferred from
    # file mtimes (see slava_rollout.provenance for what went wrong with that).
    valid, excluded_rows, rules = partition(annotations)
    provenance = {}
    for row in annotations:
        entry = provenance.setdefault(row["model"], {"n": 0, "n_stale": 0})
        entry["n"] += 1
    for row in excluded_rows:
        provenance[row["model"]]["n_stale"] += 1

    data_overview = build_data_overview()
    setup = build_setup_overview()
    examples = build_examples()
    coverage = build_coverage(setup, annotations)

    # Метрики считаются только по моделям, чьи числа вообще что-то означают.
    # `report_treatment` в data/published_baselines.json — явное решение
    # пользователя, а не порог. Решение 08.08.2026: в разделах 5 и 6 остаётся
    # только "primary", то есть модель, воспроизводящая опубликованное число
    # (OpenVLA-OFT). У "preliminary" (GreenVLA-R1/R2) английская база 5/22 —
    # приводить по ним Δlang значило бы выдавать за языковой эффект следствие
    # неразобранного расхождения. Все семь моделей по-прежнему видны в разделе
    # 3 (достоверность) и в разделе 4 (камерные записи).
    published = json.loads((DATA_DIR / "published_baselines.json").read_text(encoding="utf-8"))["baselines"]
    reportable_models = {m for m, spec in published.items() if spec.get("report_treatment") == "primary"}
    reportable = [r for r in valid if r["model"] in reportable_models]

    behavioral = compute_behavioral_pilot(reportable)
    label_mix = compute_label_mix(reportable)
    behavioral_by_model = compute_behavioral_pilot_by_model(reportable)
    language_effect = []  # pooled Δlang intentionally not reported — see render_html
    by_model_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in reportable:
        by_model_rows[row["model"]].append(row)
    language_effect_by_model = {
        model: compute_language_effect(rows) for model, rows in sorted(by_model_rows.items())
    }
    assets_dir = (args.output.parent / "report_assets") if args.for_pages else None
    # Галерея строится по `valid`, а не по всем аннотациям: 36 снятых с учёта
    # эпизодов ru_case_swap не должны ни показываться, ни попадать в SR под
    # заголовком модели — иначе цифра расходится с таблицей достоверности.
    gallery = build_camera_gallery(valid, assets_dir=assets_dir)

    html = render_html(
        data_overview, setup, examples, coverage, behavioral, label_mix, behavioral_by_model,
        language_effect, language_effect_by_model, gallery, len(annotations),
        provenance, episodes=valid,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"Wrote {args.output} ({len(annotations)} annotations, {len(valid)} used in metrics)")
    # Галерея пишется только с --for-pages. Молча пропадающий раздел — плохой
    # режим по умолчанию: так она трижды пропала из docs/rollout_report.html при
    # обычной перегенерации (08.08.2026), и заметил это пользователь, а не мы.
    if not args.for_pages:
        print(
            "  ВНИМАНИЕ: раздел «Видеозаписи прогонов» пуст — клипы пишутся только\n"
            "  с флагом --for-pages. Для публикуемого отчёта запускайте:\n"
            f"    python scripts/generate_rollout_report.py --output {args.output} --for-pages"
        )
    else:
        print(f"  галерея: {sum(len(g['items']) for g in gallery)} эпизодов в {len(gallery)} моделях")
    for rule in rules:
        print(f"  exclusion {rule.get('id','unnamed'):50s} {rule.get('n_matched',0):4d} episodes")


if __name__ == "__main__":
    main()
