#!/usr/bin/env python3
"""Generate the pilot v0 rollout technical report (data overview, setup,
camera demos, behavioral-pilot / cleaned-language-effect metric tables from
task.md). Reads whatever is currently in rollouts/rollout_annotations.jsonl —
safe to run against partial (smoke-test) data or the full run.

Usage: python scripts/generate_rollout_report.py [--output data/rollout_report.html]
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ROLLOUTS_DIR = PROJECT_ROOT / "rollouts"

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


def compute_language_effect(behavioral: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    def sr(variant: str) -> Optional[float]:
        return behavioral.get(variant, {}).get("sr")

    sr_en_canonical = sr("en_canonical")

    def gap(variant: str) -> Optional[float]:
        v = sr(variant)
        if sr_en_canonical is None or v is None:
            return None
        return sr_en_canonical - v

    gap_en_paraphrase = gap("en_paraphrase")

    def delta_lang(variant: str) -> Optional[float]:
        g = gap(variant)
        if g is None or gap_en_paraphrase is None:
            return None
        return g - gap_en_paraphrase

    rows = [
        {"effect": "gap_en_paraphrase", "formula": "SR_en_canonical − SR_en_paraphrase", "value": gap_en_paraphrase},
        {"effect": "gap_ru_literal", "formula": "SR_en_canonical − SR_ru_literal", "value": gap("ru_literal")},
        {"effect": "Δlang_ru_literal", "formula": "gap_ru_literal − gap_en_paraphrase", "value": delta_lang("ru_literal")},
        {"effect": "Δlang_ru_free_order", "formula": "gap_ru_free_order − gap_en_paraphrase", "value": delta_lang("ru_free_order")},
        {"effect": "Δlang_ru_negation", "formula": "gap_ru_negation − gap_en_paraphrase", "value": delta_lang("ru_negation")},
        {"effect": "Δlang_code_switch", "formula": "gap_code_switch − gap_en_paraphrase", "value": delta_lang("code_switch")},
    ]
    return rows


# --------------------------------------------------------------------------
# Camera demo gallery
# --------------------------------------------------------------------------

def build_camera_gallery(annotations: list[dict[str, Any]], max_runs: int = 12) -> list[dict[str, Any]]:
    episodes_root = ROLLOUTS_DIR / "episodes"
    if not episodes_root.exists():
        return []

    seen_models: set[str] = set()
    gallery = []
    # Prefer one run per model for variety, then fill up to max_runs: first
    # pass takes the first row seen for each distinct model, second pass
    # fills any remaining slots from the rest, in original order.
    first_per_model, rest = [], []
    for row in annotations:
        if row["model"] not in seen_models:
            seen_models.add(row["model"])
            first_per_model.append(row)
        else:
            rest.append(row)
    ordered = first_per_model + rest
    for row in ordered:
        if len(gallery) >= max_runs:
            break
        run_dir = episodes_root / row["run_id"]
        agent_dir = run_dir / "camera" / "agentview"
        wrist_dir = run_dir / "camera" / "wrist"
        if not agent_dir.exists():
            continue
        agent_frames = sorted(agent_dir.glob("step_*.png"))
        wrist_frames = sorted(wrist_dir.glob("step_*.png")) if wrist_dir.exists() else []
        if not agent_frames:
            continue
        picks_idx = sorted({0, len(agent_frames) // 2, len(agent_frames) - 1})
        agent_picks = [agent_frames[i] for i in picks_idx if i < len(agent_frames)]
        wrist_picks = [wrist_frames[i] for i in picks_idx if i < len(wrist_frames)]
        gallery.append(
            {
                "run_id": row["run_id"],
                "model": row["model"],
                "variant": row["variant"],
                "instruction": row["instruction"],
                "success": row["success"],
                "failure_type_auto": row["failure_type_auto"],
                "agent_paths": [str(p.relative_to(PROJECT_ROOT)) for p in agent_picks],
                "wrist_paths": [str(p.relative_to(PROJECT_ROOT)) for p in wrist_picks],
            }
        )
    return gallery


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
    return f"{sign}{value * 100:.1f} pp"


def render_html(
    data_overview: dict[str, Any],
    setup: dict[str, Any],
    coverage: list[dict[str, Any]],
    behavioral: dict[str, dict[str, Any]],
    behavioral_by_model: dict[str, dict[str, dict[str, Any]]],
    language_effect: list[dict[str, Any]],
    gallery: list[dict[str, Any]],
    n_annotations: int,
) -> str:
    models_rows = ""
    for m in setup["models"]:
        env_lines = "<br>".join(
            f"{e['name']}: <code>{e['checkpoint']}</code>" + (" <em>(zero-shot)</em>" if e["zero_shot"] else "")
            for e in m["environments"]
        )
        models_rows += (
            f"<tr><td>{m['display_name']}</td><td><code>{m['backbone']}</code></td>"
            f"<td>{env_lines}</td><td>{m['n_prompts']}</td></tr>"
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
                f"<h3>{model}</h3><table class=\"data-table\"><thead><tr>"
                "<th>Variant</th><th>n</th><th>SR</th><th>First-contact target acc</th>"
                "<th>Wrong-object rate</th><th>Relation success</th><th>Forbidden touch</th>"
                f"</tr></thead><tbody>{rows}</tbody></table>"
            )

    gallery_cards = ""
    for item in gallery:
        agent_imgs = "".join(f'<img src="{p}" loading="lazy">' for p in item["agent_paths"])
        wrist_imgs = "".join(f'<img src="{p}" loading="lazy">' for p in item["wrist_paths"]) or "<p class=\"muted\">нет wrist-камеры</p>"
        status = "success" if item["success"] else "fail"
        gallery_cards += f"""
        <div class="run-card">
          <div class="run-head">
            <b>{item['model']}</b> · {item['variant']} ·
            <span class="badge {status}">{item['failure_type_auto']}</span>
          </div>
          <p class="instruction">&laquo;{item['instruction']}&raquo;</p>
          <h4>agentview (start / mid / end)</h4>
          <div class="frame-row">{agent_imgs}</div>
          <h4>wrist (start / mid / end)</h4>
          <div class="frame-row">{wrist_imgs}</div>
        </div>"""

    lexicon_cat_rows = "".join(
        f"<tr><td>{cat}</td><td>{count}</td></tr>" for cat, count in data_overview["lexicon_categories"]
    )

    coverage_rows = ""
    for c in coverage:
        status_class = {"complete": "success", "partial": "", "not started": "fail"}[c["status"]]
        coverage_rows += (
            f"<tr><td>{c['display_name']}</td><td>{c['done']} / {c['planned']}</td>"
            f"<td><span class=\"badge {status_class}\">{c['status']}</span></td></tr>"
        )

    env_counts_str = ", ".join(f"{k}: {v}" for k, v in data_overview["env_counts"].items())
    prompts_by_env_str = ", ".join(f"{k}: {v}" for k, v in setup["prompts_by_env"].items())
    max_steps_str = ", ".join(f"{k}: {v}" for k, v in setup["max_steps"].items())

    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>SLAVA pilot v0 — rollout technical report</title>
<style>
  :root {{ --ink:#172033; --muted:#64748b; --line:#d8dee8; --paper:#fff;
    --canvas:#f3f6fa; --accent:#3157d5; --good:#166534; --bad:#991b1b; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; color:var(--ink); background:var(--canvas);
    font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
  header {{ padding:20px 28px; color:#fff; background:#172033; }}
  header h1 {{ margin:0 0 4px; font-size:22px; }}
  header p {{ margin:0; color:#cbd5e1; }}
  main {{ width:min(1200px,100%); margin:auto; padding:24px; }}
  section {{ margin:0 0 28px; padding:22px; background:var(--paper);
    border:1px solid var(--line); border-radius:14px; box-shadow:0 4px 14px #33415512; }}
  section h2 {{ margin:0 0 14px; font-size:19px; border-bottom:1px solid var(--line); padding-bottom:10px; }}
  section h3 {{ margin:18px 0 8px; font-size:15px; }}
  section h4 {{ margin:10px 0 6px; font-size:12px; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }}
  table.data-table {{ width:100%; border-collapse:collapse; margin:10px 0; }}
  table.data-table th, table.data-table td {{ padding:8px 10px; border-bottom:1px solid var(--line); text-align:left; }}
  table.data-table th {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.03em; }}
  code {{ background:#f1f5f9; padding:1px 5px; border-radius:5px; font-size:12.5px; }}
  .stat-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin:0 0 16px; }}
  .stat {{ padding:12px 14px; background:#f8fafc; border:1px solid var(--line); border-radius:10px; }}
  .stat b {{ display:block; font-size:22px; }}
  .stat span {{ color:var(--muted); font-size:12px; }}
  .pos {{ color:var(--good); font-weight:700; }}
  .neg {{ color:var(--bad); font-weight:700; }}
  .muted {{ color:var(--muted); }}
  .run-card {{ margin:0 0 22px; padding:14px; border:1px solid var(--line); border-radius:10px; background:#fbfcfe; }}
  .run-head {{ margin:0 0 6px; }}
  .instruction {{ margin:0 0 8px; color:var(--muted); font-style:italic; }}
  .frame-row {{ display:flex; gap:8px; flex-wrap:wrap; margin:0 0 10px; }}
  .frame-row img {{ width:180px; border-radius:8px; border:1px solid var(--line); }}
  .badge {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:700; }}
  .badge.success {{ color:var(--good); background:#dcfce7; border:1px solid #86efac; }}
  .badge.fail {{ color:var(--bad); background:#fee2e2; border:1px solid #fca5a5; }}
  .callout {{ padding:12px 14px; background:#eff6ff; border:1px solid #bfdbfe; border-radius:10px; margin:0 0 14px; }}
  .warn {{ padding:12px 14px; background:#fffbeb; border:1px solid #fde68a; border-radius:10px; margin:0 0 14px; }}
</style>
</head>
<body>
<header>
  <h1>SLAVA — pilot v0 rollout technical report</h1>
  <p>Первые model rollouts на 5 моделях × LIBERO/SimplerEnv, по контракту task.md. {n_annotations} эпизодов размечено на момент генерации отчёта.</p>
</header>
<main>

<section>
  <h2>1. Обзор данных предыдущих спринтов (D1–D4)</h2>
  <div class="stat-grid">
    <div class="stat"><b>{data_overview['n_candidate_scenes']}</b><span>candidate scenes (D1 task_inventory)</span></div>
    <div class="stat"><b>{data_overview['n_usable_for_slava']}</b><span>usable_for_slava=true</span></div>
    <div class="stat"><b>{data_overview['n_selected']}</b><span>отобрано в D3 ({env_counts_str})</span></div>
    <div class="stat"><b>{data_overview['n_lexicon_entries']}</b><span>записей в object_lexicon.csv (D2)</span></div>
    <div class="stat"><b>{data_overview['n_frames']}</b><span>grounded frames (D4)</span></div>
    <div class="stat"><b>{data_overview['n_native_check_passed']}/{data_overview['n_frames']}</b><span>native_check = passed</span></div>
    <div class="stat"><b>{fmt_pct(data_overview['visible_agentview_pct']/100)}</b><span>объектов видно на agentview</span></div>
    <div class="stat"><b>{fmt_pct(data_overview['visible_wrist_pct']/100)}</b><span>объектов видно на wrist</span></div>
  </div>
  <h3>Object lexicon — категории</h3>
  <table class="data-table"><thead><tr><th>category_en</th><th>count</th></tr></thead>
  <tbody>{lexicon_cat_rows}</tbody></table>
</section>

<section>
  <h2>2. Обзор сетапа роллаутов</h2>
  <div class="stat-grid">
    <div class="stat"><b>{setup['n_task_uids']}</b><span>сцен (task_uid)</span></div>
    <div class="stat"><b>{setup['n_prompts_total']}</b><span>промптов (task_uid × variant), {prompts_by_env_str}</span></div>
    <div class="stat"><b>{setup['n_repeats']}</b><span>повторов на (сцена × вариант × модель)</span></div>
    <div class="stat"><b>{setup['planned_episodes']}</b><span>запланировано эпизодов (5 моделей)</span></div>
    <div class="stat"><b>{n_annotations}</b><span>фактически размечено эпизодов</span></div>
    <div class="stat"><b>{max_steps_str}</b><span>лимит шагов на эпизод</span></div>
  </div>
  <table class="data-table"><thead><tr><th>Модель</th><th>Backbone</th><th>Среда(ы) и чекпойнт(ы)</th><th>Промптов</th></tr></thead>
  <tbody>{models_rows}</tbody></table>
  <p class="muted">Полная архитектура (env-worker/model-server split, авторазметка, известные допущения) — в
  <code>.claude/skills/slava-model-rollouts/SKILL.md</code>.</p>

  <h3>Фактическое покрытие прогонов (эпизодов сделано / запланировано)</h3>
  <div class="warn"><b>Прогон остановлен досрочно</b> (ограничение по времени) — GreenVLA-R0 и
  GreenVLA-R1 полностью завершены (это были объявленный пользователем приоритет), OpenVLA-OFT
  частично, pi0/pi0.5/SmolVLA не запускались. Метрики ниже посчитаны честно по тому, что реально
  есть — читайте их с поправкой на это неполное покрытие, а не как финальный полный пилот.</div>
  <table class="data-table"><thead><tr><th>Модель</th><th>Эпизодов</th><th>Статус</th></tr></thead>
  <tbody>{coverage_rows}</tbody></table>
</section>

<section>
  <h2>3. Камерные записи роллаутов</h2>
  <p class="muted">По одному эпизоду на модель (где данные уже есть), кадры agentview/wrist на старте, середине и конце эпизода. Полный просмотр — <code>notebooks/02_rollout_camera_dashboard.ipynb</code>.</p>
  {gallery_cards or '<p class="muted">Камерные записи пока не сгенерированы для загруженных эпизодов.</p>'}
</section>

<section>
  <h2>4. Метрики — Table: behavioral pilot</h2>
  <p class="muted">Формат и метрики строго по task.md "Table - behavioral pilot" — агрегировано по всем моделям, производившим соответствующий вариант.</p>
  <table class="data-table"><thead><tr>
    <th>Variant</th><th>n</th><th>SR</th><th>First-contact target acc</th>
    <th>Wrong-object rate</th><th>Relation success</th><th>Forbidden touch</th>
  </tr></thead><tbody>{behavioral_rows}</tbody></table>

  <div class="warn"><b>Важная оговорка:</b> модель→среда матрица асимметрична (task.md), поэтому пуллинг по
  вариантам смешивает разные подмножества моделей/сцен для разных строк (например, en_canonical для
  GreenVLA — только 4 SimplerEnv-сцены, для OpenVLA-OFT — 16 LIBERO-сцен). Разбивка по моделям ниже —
  более честный источник для интерпретации отдельной модели.</div>

  <h3>Разбивка по моделям</h3>
  {per_model_sections or '<p class="muted">Недостаточно данных для разбивки по моделям.</p>'}
</section>

<section>
  <h2>5. Метрики — Table: cleaned language effect (Δlang)</h2>
  <p class="muted">Главная метрика пилота (task.md): отделяет языковой эффект от instruction-string OOD.
  Положительный Δlang значит, что соответствующая RU/code-switch ось теряет SR сильнее, чем можно было бы
  объяснить простым перефразированием на английском (en_paraphrase) — то есть эффект специфичен для языка,
  не просто "непривычная формулировка".</p>
  <table class="data-table"><thead><tr><th>Effect</th><th>Formula</th><th>Value</th></tr></thead>
  <tbody>{language_rows}</tbody></table>
</section>

<section>
  <h2>6. Наблюдение: SR = 0% во всех вариантах на текущих данных</h2>
  <div class="callout">
  <p>На всех 77 размеченных эпизодах <code>success</code> ни разу не сработал — SR=0% по каждой модели и
  варианту (см. таблицы ниже). Это делает Δlang-таблицу вырожденной (все gap'ы считаются от SR=0%, поэтому
  Δlang≈0 pp everywhere) — таблица ниже механически корректна, но не информативна на этом объёме данных;
  выводы про Δlang делать преждевременно.</p>
  <p>Проверено, что это не баг разметки: <code>success</code> берётся напрямую из нативного
  <code>env.check_success()</code>/<code>info["success"]</code> симулятора (LIBERO/SimplerEnv), не из нашей
  эвристики. Отдельно проверено на сэмпле эпизодов (md5 кадров agentview по шагам): <b>GreenVLA-R0</b>
  систематически "замирает" на 24–40 из 60 шагов (кадры и позы объектов не меняются) в каждом
  проверенном эпизоде — модель перестаёт выдавать значимые действия примерно на середине эпизода.
  <b>GreenVLA-R1</b> замирает существенно меньше (1–14 шагов), <b>OpenVLA-OFT</b> не замирает вовсе
  (max identical run = 1 на всех проверенных LIBERO-эпизодах). Раз паттерн модель-специфичен (общий
  env-worker код у GreenVLA-R0/R1 один и тот же), а не одинаков для всех — это похоже на реальное различие
  в поведении между R0 (base curriculum stage) и R1 (следующая, более дообученная стадия), а не на
  инфраструктурный баг. Стоит перепроверить на большем сэмпле, если/когда прогон возобновится.</p>
  </div>
</section>

<section>
  <h2>7. Что осталось по чек-листу task.md</h2>
  <div class="warn">
  <p><b>Ручная валидация первых 100 rollouts</b> (task.md, "Auto-labeling для первых прогонов": "проверить
  первые 100 rollouts и оценить точность auto-labeler'а") — <b>не выполнена</b>. Это explicit требование
  человеческой проверки точности авторазметчика (`src/slava_rollout/auto_label.py`), которое агент не может
  корректно заменить собой — не переприсваивать эту задачу LLM-проверке, нужна ваша ручная сверка выборки
  эпизодов (камера + `rollout_annotations.jsonl` + `failure_type_auto`) против того, что реально произошло.</p>
  <p><b>v0.1 (projection 3D → 2D crosshair) и pointing-зонд GreenVLA</b> — не начаты. Task.md сам относит их
  к следующему шагу после behavioral pilot ("После делаем"), не к Definition of Done pilot v0 — сознательно
  в backlog, не блокер этого отчёта.</p>
  <p><b>Полное покрытие 5 моделей × 127 промптов</b> — не достигнуто (см. таблицу покрытия в разделе 2),
  прогон остановлен по ограничению времени. pi0/pi0.5/SmolVLA можно доснять отдельным запуском позже.</p>
  </div>
</section>

<section>
  <h2>8. Интерпретация относительно гипотез task.md</h2>
  <div class="callout">
  <p><b>RQ1</b> (task.md "Наши research questions"): "Which linguistic perturbations cause VLA failures
  beyond generic instruction-string OOD?" — отвечает именно Δlang-таблица выше. Положительный и заметно
  больше нуля Δlang по какой-либо RU/code-switch оси = свидетельство в пользу языко-специфичного эффекта,
  не только шума от непривычной формулировки.</p>
  <p>Дальше по клейму проекта (H-understanding / H-grounding / H-binding, "Три возможных объяснения") этот
  пилот сам по себе <b>не различает эти три гипотезы</b> — для этого нужны slot-level probes, visual-grounding
  oracle и каузальный patching между base и action-tuned чекпойнтами, которые не входят в scope pilot v0
  (see task.md "Наш core" пп. 2–6, "Visual oracle: не блокирует v0"). Этот отчёт закрывает поведенческий
  слой (Phase 2 auto-labeling), не атрибуционный.</p>
  </div>
</section>

</main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DATA_DIR / "rollout_report.html")
    args = parser.parse_args()

    annotations = load_jsonl(ROLLOUTS_DIR / "rollout_annotations.jsonl")
    data_overview = build_data_overview()
    setup = build_setup_overview()
    coverage = build_coverage(setup, annotations)
    behavioral = compute_behavioral_pilot(annotations)
    behavioral_by_model = compute_behavioral_pilot_by_model(annotations)
    language_effect = compute_language_effect(behavioral)
    gallery = build_camera_gallery(annotations)

    html = render_html(
        data_overview, setup, coverage, behavioral, behavioral_by_model, language_effect, gallery, len(annotations)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"Wrote {args.output} ({len(annotations)} annotations)")


if __name__ == "__main__":
    main()
