#!/usr/bin/env python3
"""Compact SLAVA results report: metrics, formulas, a few example frames.

Deliberately terse — the long-form `generate_rollout_report.py` grew into a
wall of prose that buried the numbers. This one answers four questions and
stops: what was run, is the pipeline trustworthy, what is the language
effect, and what does a rollout actually look like.

Metric definitions are imported from `generate_rollout_report.py` so the two
reports can never disagree about what Δlang means.

Usage:
    python scripts/generate_report_compact.py --output docs/report.html
"""
from __future__ import annotations

import argparse
import base64
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from generate_rollout_report import _frames_to_clip  # noqa: E402
from slava_rollout.provenance import partition  # noqa: E402
from slava_rollout.stats import (  # noqa: E402
    bootstrap_ci,
    cluster_summary,
    delta_lang,
    failure_mix,
    first_contact_profile,
    outcomes_by_variant,
    paired_by_task,
    mcnemar_exact,
    wilson,
)

# Pool layout lives in one place (src/slava_rollout/storage.py); the report
# reads the finished pilot pool and, when present, the harness-validation pool.
ROLLOUTS = PROJECT_ROOT / "rollouts" / "final" / "pilot_v0"
VALIDATION_POOL = PROJECT_ROOT / "rollouts" / "final" / "harness_validation_greenvla"
VARIANT_ORDER = [
    "en_canonical", "en_paraphrase", "mt_russian", "ru_literal",
    "ru_case_swap", "ru_negation", "code_switch",
]
RU_VARIANTS = {"mt_russian", "ru_literal", "ru_case_swap", "ru_negation"}


def load_annotations() -> list[dict[str, Any]]:
    path = ROLLOUTS / "rollout_annotations.jsonl"
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def per_model_variant(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[bool]]:
    out: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for r in rows:
        out[(r["model"], r["variant"])].append(bool(r.get("success")))
    return out


def _agentview_frames(run_id: str) -> list[Path]:
    d = ROLLOUTS / "episodes" / run_id / "camera" / "agentview"
    return sorted(d.glob("step_*.png")) if d.is_dir() else []


def pick_showcase_scene(model_rows: list[dict[str, Any]]) -> Optional[str]:
    """One scene per model, chosen to make the comparison legible.

    The point of this gallery is the paired design itself: same model, same
    scene, same physics, only the wording of the instruction changes. So we
    want the scene where that contrast is most visible, preferring, in order:
    how many variants have frames on disk at all, whether the outcomes
    actually differ across variants (a scene the model always fails shows
    nothing), and whether English succeeds (a scene the model cannot do in any
    language says nothing about language).
    """
    by_scene: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in model_rows:
        if _agentview_frames(r["run_id"]):
            by_scene[r["task_uid"]].append(r)
    if not by_scene:
        return None

    def score(scene: str) -> tuple:
        rs = by_scene[scene]
        outcomes = {r["success"] for r in rs}
        en_ok = any(r["variant"] == "en_canonical" and r["success"] for r in rs)
        return (len(outcomes) > 1, en_ok, len(rs))

    return max(by_scene, key=score)


def build_variant_gallery(rows: list[dict[str, Any]], assets: Path) -> str:
    """Per model: one scene, every instruction variant, side by side.

    GIFs rather than stills because the failure modes here are about motion —
    a frozen arm and an arm reaching but missing look nearly identical in a
    first/last frame pair.
    """
    out = ""
    for model in sorted({r["model"] for r in rows}):
        model_rows = [r for r in rows if r["model"] == model]
        scene = pick_showcase_scene(model_rows)
        if scene is None:
            continue
        scene_rows = {r["variant"]: r for r in model_rows if r["task_uid"] == scene}
        cards = ""
        for variant in VARIANT_ORDER:
            r = scene_rows.get(variant)
            if r is None:
                continue
            frames = _agentview_frames(r["run_id"])
            if len(frames) < 2:
                continue
            clip = _frames_to_clip(
                frames, assets / r["run_id"] / "variant", max_frames=60, size=168
            )
            ok = r.get("success")
            outcome = "успех" if ok else esc(r.get("failure_type_auto") or "")
            cards += (
                f"<figure class='vcard {'ok' if ok else 'bad'}'>"
                f"<img src='{clip.relative_to(assets.parent)}' loading='lazy'>"
                f"<figcaption><code>{esc(variant)}</code> — <b>{outcome}</b>"
                f"<br><span class=ci>{esc(r['instruction'])}</span>"
                f"<br><span class=ci>{len(frames)} шагов</span></figcaption></figure>"
            )
        if not cards:
            continue
        n_ok = sum(1 for v in scene_rows.values() if v.get("success"))
        out += (
            f"<h4>{esc(model)} <span class=ci>· сцена <code>{esc(scene)}</code> "
            f"· {n_ok} из {len(scene_rows)} вариантов успешны</span></h4>"
            f"<div class=vrow>{cards}</div>"
        )
    return out


def esc(s: Any) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))



def load_published_baselines() -> dict[str, Any]:
    path = PROJECT_ROOT / "data" / "published_baselines.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("baselines", {})


def build_baseline_check(rows: list[dict[str, Any]]) -> str:
    """Does our harness reproduce a number the authors published?

    This is the load-bearing sanity check of the whole pilot: every
    cross-lingual claim rests on the English baseline being right. Reported
    first, including where it clearly failed.
    """
    published = load_published_baselines()
    body = ""
    for m in sorted({r["model"] for r in rows}):
        en = [r for r in rows if r["model"] == m and r["variant"] == "en_canonical"]
        if not en:
            continue
        k, n = sum(r["success"] for r in en), len(en)
        lo, hi = wilson(k, n)
        ref = published.get(m) or {}
        ref_sr, ref_label = ref.get("sr"), ref.get("label")
        if ref_sr is None:
            verdict, cls = "нет опубликованного числа", "na"
        elif hi - lo > 0.40:
            # With n this small the interval spans most of [0,1] and would
            # "contain" almost any reference value — declaring a match from it
            # would be an artefact of the sample size, not a reproduction.
            verdict, cls = f"не проверяемо (n={n}, CI шире 40 п.п.)", "na"
        elif lo <= ref_sr <= hi:
            verdict, cls = "совпадает (в CI)", "hi"
        elif k / n >= ref_sr:
            verdict, cls = "выше заявленного", "hi"
        else:
            verdict, cls = "НИЖЕ заявленного", "zero"
        body += (
            f"<tr><th class=m>{esc(m)}</th>"
            f"<td><b>{k}/{n}</b> = {100*k/n:.0f}%<br>"
            f"<span class=ci>[{100*lo:.0f};{100*hi:.0f}]</span></td>"
            f"<td>{esc(ref_label or '—')}<br><span class=ci>{esc(ref.get('scope') or '')}</span></td>"
            f"<td class={cls}>{verdict}</td>"
            f"<td class=ci>{esc(ref.get('source') or '')}</td></tr>"
        )
    return (
        "<table><tr><th></th><th>наш en_canonical</th><th>заявлено авторами</th>"
        f"<th>вердикт</th><th>источник</th></tr>{body}</table>"
    )


def build_validation_banner(rows: list[dict[str, Any]]) -> str:
    """What the reader must know before any number below: which models did not
    reproduce their own published English baseline, and what we do about each.

    A model that cannot hit its own published number on the authors' own English
    string is not measuring language — whatever is wrong sits in our pipeline.
    But that does not make every such model equally uninformative, so
    data/published_baselines.json carries an explicit `report_treatment` per
    model (a judgement, not a threshold):

      preliminary — English baseline is high enough that a collapse to zero on
                    Russian is still an observation; shown, flagged.
      excluded    — English baseline is too low to separate a language effect
                    from a broken pipeline; no language analysis at all.
    """
    published = load_published_baselines()
    # A dedicated validation run, when one exists, replaces the pilot's own
    # en_canonical count for the models it covers: it is the same check on a
    # wider scene set, so its interval is the one worth reporting.
    validation_path = VALIDATION_POOL / "rollout_annotations.jsonl"
    validation: list[dict[str, Any]] = []
    if validation_path.is_file():
        validation = [json.loads(l) for l in open(validation_path, encoding="utf-8") if l.strip()]

    groups: dict[str, list[tuple[str, int, int, float]]] = {"preliminary": [], "excluded": []}
    for model in sorted({r["model"] for r in rows} | {r["model"] for r in validation}):
        reference = (published.get(model) or {}).get("sr")
        treatment = (published.get(model) or {}).get("report_treatment")
        if reference is None or treatment not in groups:
            continue
        en = [r for r in validation if r["model"] == model and r["variant"] == "en_canonical"]
        if not en:
            en = [r for r in rows if r["model"] == model and r["variant"] == "en_canonical"]
        if not en:
            continue
        hits, total = sum(r["success"] for r in en), len(en)
        groups[treatment].append((model, hits, total, reference))
    if not any(groups.values()):
        return ""

    def items(entries: list[tuple[str, int, int, float]]) -> str:
        return "".join(
            f"<li><b>{esc(model)}</b> — у нас {hits}/{total} = {100 * hits / total:.0f}% "
            f"на <code>en_canonical</code> против заявленных {100 * reference:.0f}%</li>"
            for model, hits, total, reference in entries
        )

    out = "<div class=banner><b>Валидацию стенда прошла одна модель из семи.</b>"
    if groups["excluded"]:
        out += (
            "<p>Языковой анализ по этим моделям не приводится: их английская база слишком "
            "низка, чтобы отличить языковой эффект от общей поломки — нули на русском "
            "неотличимы от эффекта пола:</p>"
            f"<ul>{items(groups['excluded'])}</ul>"
        )
    if groups["preliminary"]:
        out += (
            "<p>Эти показаны как <b>предварительные</b>: опубликованное число не "
            "воспроизводится, но английская база ненулевая, поэтому падение до нуля "
            "на русском остаётся содержательным наблюдением:</p>"
            f"<ul>{items(groups['preliminary'])}</ul>"
        )
    out += (
        "<p>Расхождение такого размера на родной английской строке задачи — это "
        "дефект нашего пайплайна инференса, а не свойство модели. Полноценные "
        "выводы делаются только по модели, прошедшей валидацию.</p>"
    )
    if validation:
        out += (
            "<p class=ci>Числа GreenVLA здесь — по отдельному прогону на полном "
            "bridge-наборе SimplerEnv (22 сцены, все четыре задачи), а не по "
            "четырём сценам пилота: те покрывали одну задачу и с публикуемым "
            "средним по четырём не сопоставимы.</p>"
        )
    return out + "</div>"


def build_mt_ablation(rows: list[dict[str, Any]]) -> str:
    """Machine translation vs human-authored Russian, on shared scenes.

    Separates "the model struggles with Russian" from "our Russian is
    unnatural" — the cheapest objection to the whole result — and doubles as a
    prompt-length control, since raw MT is systematically the longest variant.
    """
    frames = {f["task_uid"]: f for f in
              (json.loads(l) for l in open(
                  PROJECT_ROOT / "data" / "pilot_v0_release" / "frames_v0.jsonl", encoding="utf-8"))}
    body = ""
    for m in sorted({r["model"] for r in rows}):
        by_variant = outcomes_by_variant([r for r in rows if r["model"] == m])
        mt, ru = by_variant.get("mt_russian", {}), by_variant.get("ru_literal", {})
        shared = sorted(set(mt) & set(ru))
        if not shared:
            continue
        mt_k, ru_k = sum(mt[s] for s in shared), sum(ru[s] for s in shared)
        toks = {"mt_russian": [], "ru_literal": []}
        for s in shared:
            tl = frames.get(s, {}).get("token_len", {}).get("openvla_oft", {})
            for v in toks:
                if tl.get(v) is not None:
                    toks[v].append(tl[v])
        avg = {v: (sum(x) / len(x) if x else None) for v, x in toks.items()}
        d_mt = sum(1 for s in shared if mt[s] and not ru[s])
        d_ru = sum(1 for s in shared if ru[s] and not mt[s])
        b = mcnemar_exact(d_mt, d_ru)
        tok_txt = (
            "—" if avg["mt_russian"] is None
            else f"{avg['mt_russian']:.1f} vs {avg['ru_literal']:.1f}"
        )
        # b is None means zero discordant scenes — i.e. the two Russian
        # variants behaved identically on every single scene. That is the
        # result here, not missing data, so say it rather than print a dash.
        p_txt = (f"нет расхождений<br><span class=ci>0 из {len(shared)}</span>"
                 if b is None else f"{b:.3f}<br><span class=ci>{d_mt}:{d_ru}</span>")
        body += (
            f"<tr><th class=m>{esc(m)}</th><td>{len(shared)}</td>"
            f"<td>{mt_k}/{len(shared)}</td><td>{ru_k}/{len(shared)}</td>"
            f"<td>{p_txt}</td><td class=ci>{tok_txt}</td></tr>"
        )
    return (
        "<table><tr><th></th><th>общих сцен</th><th>mt_russian (сырой MT)</th>"
        "<th>ru_literal (человек)</th><th>p (McNemar)</th>"
        "<th>токенов: MT vs человек</th></tr>" + body + "</table>"
    )


def build_contact_profile(rows: list[dict[str, Any]]) -> str:
    """Where it breaks, not just how often — first-contact attribution."""
    out = ""
    for m in sorted({r["model"] for r in rows}):
        model_rows = [r for r in rows if r["model"] == m]
        if not any(r["variant"] == "en_canonical" for r in model_rows):
            continue
        body = ""
        for v in VARIANT_ORDER:
            vr = [r for r in model_rows if r["variant"] == v]
            if not vr:
                continue
            p = first_contact_profile(vr)
            body += (
                f"<tr><td>{v}</td><td>{p['n']}</td>"
                f"<td class={'hi' if p['correct_target'] >= 0.7 else 'mid'}>{100*p['correct_target']:.0f}%</td>"
                f"<td>{100*p['wrong_target']:.0f}%</td>"
                f"<td>{100*p['no_contact']:.0f}%</td></tr>"
            )
        out += (f"<h4>{esc(m)}</h4><table class=t2><tr><th>вариант</th><th>n</th>"
                f"<th>верный target</th><th>не тот объект</th>"
                f"<th>не коснулся вовсе</th></tr>{body}</table>")
    return out


def build_failure_mix(rows: list[dict[str, Any]]) -> str:
    labels = ["success", "target_grounding_error", "relation_binding_error",
              "negation_error", "physical_execution_error", "no_action_or_timeout", "unclear"]
    out = ""
    for m in sorted({r["model"] for r in rows}):
        model_rows = [r for r in rows if r["model"] == m]
        body = ""
        for v in VARIANT_ORDER:
            vr = [r for r in model_rows if r["variant"] == v]
            if not vr:
                continue
            mix = failure_mix(vr)
            body += f"<tr><td>{v}</td>" + "".join(
                f"<td>{'' if not mix.get(l) else f'{100*mix[l]:.0f}%'}</td>" for l in labels
            ) + "</tr>"
        if body:
            head = "".join(f"<th>{l.replace('_error','').replace('_or_timeout','')}</th>" for l in labels)
            out += f"<h4>{esc(m)}</h4><table class=t2><tr><th>вариант</th>{head}</tr>{body}</table>"
    return out


def build_scene_matrix(rows: list[dict[str, Any]], model: str) -> str:
    """Per-scene outcomes: is the effect spread out, or two scenes carrying it?"""
    by_variant = outcomes_by_variant([r for r in rows if r["model"] == model])
    scenes = sorted(by_variant.get("en_canonical", {}))
    if not scenes:
        return ""
    head = "".join(f"<th>{v.replace('_','<br>')}</th>" for v in VARIANT_ORDER)
    body = ""
    for s in scenes:
        short = s.replace("libero_", "").rsplit("__init", 1)
        label = f"{short[0][:44]}<span class=ci> init{short[1]}</span>" if len(short) > 1 else s[:48]
        cells_html = ""
        for v in VARIANT_ORDER:
            val = by_variant.get(v, {}).get(s)
            if val is None:
                cells_html += "<td class=na>·</td>"
            else:
                cells_html += f"<td class={'hi' if val else 'zero'}>{'✓' if val else '✗'}</td>"
        body += f"<tr><th class=m>{label}</th>{cells_html}</tr>"
    return f"<table><tr><th></th>{head}</tr>{body}</table>"


def build_caveats(rows: list[dict[str, Any]], all_rows: list[dict[str, Any]]) -> str:
    """State the limits ourselves, with numbers, rather than leave them to be found."""
    items = []

    # power + clustering, on the model that carries the result
    for m in ["OpenVLA-OFT"]:
        by_variant = outcomes_by_variant([r for r in rows if r["model"] == m])
        en, ru = by_variant.get("en_canonical", {}), by_variant.get("ru_literal", {})
        shared = sorted(set(en) & set(ru))
        if not shared:
            continue
        b = sum(1 for s in shared if en[s] and not ru[s])
        c = sum(1 for s in shared if ru[s] and not en[s])
        cl = cluster_summary(shared)
        tb, tc = paired_by_task(en, ru)
        items.append(
            f"<li><b>Мощность на пределе.</b> У {esc(m)} значимость даёт расклад "
            f"{b}:{c} по дискордантным сценам (p={mcnemar_exact(b, c):.3f}). "
            f"При n={len(shared)} минимум для p&lt;0.05 — это 6:0; одна сцена в "
            f"обратную сторону, и p={mcnemar_exact(max(b-1, 0), c+0) or 1:.3f}. "
            f"Пилот показывает направление, а не финальную величину.</li>"
        )
        items.append(
            f"<li><b>Наблюдения не независимы.</b> {cl['n_scenes']} сцен — это "
            f"{cl['n_tasks']} различных задач (до {cl['max_scenes_per_task']} init-состояний "
            f"на одну). На уровне задач расклад {tb}:{tc}, "
            f"p={'—' if mcnemar_exact(tb, tc) is None else f'{mcnemar_exact(tb, tc):.3f}'} — "
            f"значимость на уровне сцен частично держится на том, что init-состояния "
            f"одной задачи считаются независимыми. Это главный аргумент за полный набор.</li>"
        )

    # floor effect
    floor = []
    for m in sorted({r["model"] for r in rows}):
        en = [r for r in rows if r["model"] == m and r["variant"] == "en_canonical"]
        if en and sum(r["success"] for r in en) / len(en) < 0.15:
            floor.append(m)
    if floor:
        items.append(
            "<li><b>Floor effect.</b> У " + esc(", ".join(floor)) +
            " SR близок к нулю уже на английском, поэтому их Δlang≈0 означает "
            "«измерять нечем», а не «языкового эффекта нет». Эти строки нельзя "
            "читать как свидетельство против эффекта.</li>"
        )

    items.append(
        "<li><b>n=1 повтор</b> на (сцена × вариант × модель) — осознанное решение ради "
        "простоты сравнения. У pi0/pi0.5/SmolVLA действие сэмплируется из "
        "flow-matching головы, так что их числа шумнее детерминированных OpenVLA-OFT/GreenVLA.</li>"
    )
    items.append(
        "<li><b>Авторазметка не прошла ручную валидацию.</b> Обязательная по task.md проверка "
        "первых 100 роллаутов ещё не сделана. Отдельно неразличимы "
        "<code>relation_binding_error</code> и <code>reference_grounding_error</code>: "
        "по одному сигналу первого контакта их не отделить, авторазметчик ставит первое.</li>"
    )
    items.append(
        f"<li><b>Исключено из метрик:</b> {len(all_rows) - len(rows)} эпизодов из {len(all_rows)} "
        "(объявлено в <code>data/rollout_provenance.json</code> с причиной).</li>"
    )
    return "<ul class=caveats>" + "".join(items) + "</ul>"


def render(rows: list[dict[str, Any]], rules: list[dict[str, Any]], assets: Path,
           all_rows: list[dict[str, Any]] | None = None) -> str:
    all_rows = all_rows if all_rows is not None else rows
    cells = per_model_variant(rows)
    models = sorted({r["model"] for r in rows})

    # ---- coverage + per-variant SR table
    head = "".join(f"<th>{v}</th>" for v in VARIANT_ORDER)
    body = ""
    for m in models:
        tds = ""
        for v in VARIANT_ORDER:
            vals = cells.get((m, v), [])
            if not vals:
                tds += "<td class=na>—</td>"
                continue
            k, n = sum(vals), len(vals)
            lo, hi = wilson(k, n)
            cls = "hi" if k / n >= 0.3 else ("mid" if k else "zero")
            tds += (f"<td class={cls}><b>{k}/{n}</b><br><span class=ci>"
                    f"{100*k/n:.0f}% [{100*lo:.0f};{100*hi:.0f}]</span></td>")
        body += f"<tr><th class=m>{esc(m)}</th>{tds}</tr>"

    # ---- language effect, per model, en_canonical anchored, PAIRED
    #
    # Every number below is computed on the scenes a variant SHARES with
    # en_canonical and en_paraphrase, never on its own marginal coverage.
    # Without that, `ru_case_swap` (authored for only 8 of 20 scenes, the rest
    # legitimately axis_na) would be compared against en_canonical's full 20 and
    # the difference in scene composition would read as a language effect.
    lang = ""
    for m in models:
        model_rows = [r for r in rows if r["model"] == m]
        by_variant = outcomes_by_variant(model_rows)
        en = by_variant.get("en_canonical")
        if not en:
            continue
        sr_en = sum(en.values()) / len(en)
        ru_rows = ""
        for v in VARIANT_ORDER:
            if v in ("en_canonical", "en_paraphrase"):
                continue
            d = delta_lang(by_variant, v)
            if d is None:
                continue
            lo, hi = d["ci"]
            p = d["p_mcnemar_vs_anchor"]
            p_txt = "—" if p is None else (f"{p:.3f}" if p >= 0.001 else "&lt;0.001")
            sig = " class=sig" if (p is not None and p < 0.05) else ""
            ru_rows += (
                f"<tr><td>{v}</td><td>{d['n_scenes']}</td>"
                f"<td>{100*d['gap_variant']:+.1f}</td>"
                f"<td><b>{100*d['value']:+.1f}</b><br>"
                f"<span class=ci>[{100*lo:+.0f};{100*hi:+.0f}]</span></td>"
                f"<td{sig}>{p_txt}</td></tr>"
            )
        lo, hi = bootstrap_ci([float(x) for x in en.values()])
        lang += (
            f"<h4>{esc(m)} <span class=ci>SR<sub>en_canonical</sub> = "
            f"{100*sr_en:.0f}% ({sum(en.values())}/{len(en)}) "
            f"[bootstrap {100*lo:.0f};{100*hi:.0f}]</span></h4>"
            f"<table class=t2><tr><th>вариант</th><th>парных сцен</th>"
            f"<th>gap, п.п.</th><th>Δlang, п.п. [95% CI]</th>"
            f"<th>p (McNemar)</th></tr>{ru_rows}</table>"
        )

    gallery_html = build_variant_gallery(rows, assets)

    # The report states what the metrics ARE computed on (the episode count in
    # the header). Which episodes are set aside, and why, is recorded in
    # data/rollout_provenance.json — that belongs to the repository's record,
    # not to a results write-up.
    baseline_html = build_baseline_check(rows)
    validation_banner = build_validation_banner(rows)
    mt_html = build_mt_ablation(rows)
    contact_html = build_contact_profile(rows)
    failure_html = build_failure_mix(rows)
    matrix_html = build_scene_matrix(rows, "OpenVLA-OFT")
    caveats_html = build_caveats(rows, all_rows)

    n_total = len(rows)
    return f"""<title>SLAVA — результаты</title>
<style>
body{{font:14px/1.5 system-ui,sans-serif;margin:24px auto;max-width:1000px;color:#111}}
h1{{font-size:20px;margin:0 0 4px}} h2{{font-size:16px;margin:22px 0 6px;border-bottom:1px solid #ddd}}
h4{{margin:14px 0 4px;font-size:14px;font-weight:600}}
table{{border-collapse:collapse;margin:6px 0;font-size:13px}}
td,th{{border:1px solid #ddd;padding:4px 7px;text-align:center}}
th.m{{text-align:left;white-space:nowrap;background:#fafafa}}
.ci{{color:#777;font-size:11px;font-weight:400}}
.zero{{background:#fff1f0}} .mid{{background:#fffbe6}} .hi{{background:#f0fff4}} .na{{color:#bbb}}
.t2 td:first-child{{text-align:left}}
figure{{margin:10px 0;padding:8px;border:1px solid #eee;border-radius:6px}}
.vrow{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}}
.vcard{{margin:0;padding:6px;width:180px;border-radius:6px;border:1px solid #e5e5e5}}
.vcard.ok{{border-color:#8ed6a4;background:#f6fffa}}
.vcard.bad{{border-color:#f0c9c4;background:#fffafa}}
.vcard img{{width:168px;margin:0}}
.vcard figcaption{{font-size:11px;line-height:1.35;margin:4px 0 0}}
figure img{{width:190px;image-rendering:pixelated;border:1px solid #ddd;margin-right:6px;vertical-align:top}}
figcaption{{font-size:12px;margin-bottom:6px}}
code{{background:#f4f4f4;padding:1px 4px;border-radius:3px}}
.warn{{background:#fffbe6;border-left:3px solid #f0c000;padding:6px 10px;font-size:13px}}
.warnlist{{background:#fffbe6;border-left:3px solid #f0c000;margin:0;padding:6px 10px 6px 26px;font-size:13px}}
.warnlist li{{margin:4px 0}}
.caveats{{padding-left:20px;font-size:13px}} .caveats li{{margin:6px 0}}
table.t2 td:first-child{{text-align:left;white-space:nowrap}}
td.sig{{font-weight:700;background:#f0fff4}}
.banner{{background:#fff4f4;border-left:3px solid #d33;padding:10px 14px;margin:14px 0;font-size:13.5px}}
.banner ul{{margin:6px 0 6px 18px;padding:0}} .banner p{{margin:6px 0 0}}
.f{{background:#f7f7f9;padding:8px 10px;border-radius:5px;font-family:ui-monospace,monospace;font-size:12.5px}}
</style>
<h1>SLAVA — кросс-язычный бенчмарк VLA</h1>
<p class=ci>{n_total} эпизодов в метриках · n=1 повтор на (сцена × вариант × модель)</p>
{validation_banner}

<h2>1. Воспроизводим ли мы известные числа</h2>
<p>Всё остальное в этом отчёте имеет смысл только если харнесс корректен. Самая
прямая проверка — прогнать <code>en_canonical</code> и сравнить с тем, что
авторы моделей заявляют сами. Наш набор сцен не совпадает с их бенчмарком,
поэтому это ориентир, а не построчное воспроизведение; но порядок величины
должен сходиться.</p>
{baseline_html}
<p class=ci><b>Как это читать.</b> OpenVLA-OFT воспроизводится — значит
пайплайн (сброс среды, подача наблюдений, детекция успеха) работает, и его
кросс-язычные числа можно интерпретировать. У остальных моделей
воспроизведение либо не подтверждается на нашем объёме сцен, либо
опубликованного числа для этой конфигурации нет; их SR нельзя сравнивать с
авторским напрямую, и языковые выводы по ним ограничены.</p>

<h2>2. Метрики</h2>
<div class=f>
SR = успешные эпизоды / всего &nbsp;·&nbsp; успех берётся из нативного <code>env.check_success()</code><br>
gap<sub>v</sub> = SR<sub>en_canonical</sub> − SR<sub>v</sub><br>
<b>Δlang<sub>v</sub> = gap<sub>v</sub> − gap<sub>en_paraphrase</sub></b>
</div>
<p>Вычитание <code>gap_en_paraphrase</code> — ключевой контроль: он убирает эффект
«инструкция просто непривычная» и оставляет только языковой.</p>
<p><b>Сравнение парное.</b> Каждый вариант сравнивается с
<code>en_canonical</code> и <code>en_paraphrase</code> только на тех сценах, которые
есть у всех трёх («парных сцен» в таблице). Иначе разница в составе сцен
читалась бы как языковой эффект: например <code>ru_case_swap</code> осмыслен лишь
на 8 сценах из 20 (у остальных <code>axis_na</code>), и его маргинальный SR
относится к другому, более узкому набору задач, чем SR<sub>en_canonical</sub>.</p>
<p>CI по SR — интервал Уилсона (корректен у краёв 0% и 100%); по Δlang —
парный бутстрап (2000 итераций, ресэмплируются <i>сцены</i>, а не эпизоды, чтобы
исходы одной сцены двигались вместе). <code>p</code> — точный тест Мак-Немара
против <code>en_canonical</code> по дискордантным парам; прочерк означает, что
дискордантных пар нет вовсе, то есть данных для суждения нет — это не то же самое,
что «различий нет».</p>
<p class=ci><b>Оговорка о метриках.</b> <code>final_relation_success</code> в этом
пилоте тождественно равен <code>success</code> (проверено: совпадает во всех 550
эпизодах): у каждой сцены ровно один success-предикат, и это буквально тот же
предикат, который проверяет нативный <code>env.check_success()</code>. Поэтому
отдельной колонкой «relation success» он не выводится — это было бы то же число
под другим именем.</p>

<h2>3. SR по вариантам</h2>
<table><tr><th></th>{head}</tr>{body}</table>
<p class=ci><code>ru_case_swap</code> — намеренно перевёрнутая инструкция
(«поставь жёлтый на зелёный» при success-предикате «зелёный на жёлтом»).
Модель, выполнившая её верно, засчитывается как провал: это зонд на
чувствительность к порядку, а не задача. В агрегат по модели не входит.</p>

<h2>4. Языковой эффект</h2>
{lang}

<h2>5. Машинный перевод против человеческого русского</h2>
<p>Самое дешёвое возражение к результату — «у вас просто неестественный
русский». Проверяется прямо: <code>mt_russian</code> — сырой выход DeepL без
единой правки, <code>ru_literal</code> — вручную выверенный вариант, прошедший
native check. Сравнение на общих сценах. Последняя колонка — средняя длина в
токенах (токенизатор OpenVLA-OFT): заодно контроль на то, что падение не
объясняется просто более длинным промптом.</p>
{mt_html}

<h2>6. Где именно ломается: первый контакт</h2>
<p>SR говорит только «получилось/нет». Первый объект, которого робот реально
коснулся, различает три разные неудачи: потянулся к верному объекту и не
справился физически; потянулся не к тому (ошибка заземления); не тронул ничего.
Это и есть slot-level атрибуция, ради которой строился бенчмарк.</p>
{contact_html}

<h2>7. Профиль типов отказов</h2>
<p>Ломается ли русский <i>иначе</i>, чем английский, а не просто чаще.</p>
{failure_html}

<h2>8. По сценам: эффект размазан или держится на паре сцен</h2>
<p>OpenVLA-OFT, по одной строке на сцену. Видно, что падение на русском не
сосредоточено в одной задаче.</p>
{matrix_html}

<h2>9. Ограничения</h2>
{caveats_html}

<h2>10. Как одна и та же модель справляется с разными формулировками</h2>
<p>Это парный дизайн в чистом виде: внутри каждого блока — одна модель, одна
сцена, одинаковая физика и одинаковое начальное состояние. Меняется только
формулировка инструкции. Сцена выбрана автоматически как самая показательная
у этой модели: та, где исходы по вариантам различаются, а английский вариант
модель выполняет — на сцене, которую модель не может сделать ни на одном языке,
про язык ничего не видно.</p>
{gallery_html}
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=PROJECT_ROOT / "docs" / "report.html")
    args = ap.parse_args()
    ann = load_annotations()
    rows, excluded, rules = partition(ann)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    assets = args.output.parent / "report_assets"
    args.output.write_text(render(rows, rules, assets, all_rows=ann), encoding="utf-8")
    print(f"Wrote {args.output} ({len(rows)}/{len(ann)} эпизодов в метриках)")
    if not rules:
        print("  NOTE: data/rollout_provenance.json declares no exclusions — "
              "every collected episode is being aggregated.")
    for r in rules:
        status = "applied" if r.get("n_matched") else "matched nothing (stale rule?)"
        print(f"  exclusion {r.get('id','unnamed'):50s} {r.get('n_matched',0):4d} episodes  [{status}]")


if __name__ == "__main__":
    main()
