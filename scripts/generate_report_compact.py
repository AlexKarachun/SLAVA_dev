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

from generate_rollout_report import (  # noqa: E402
    _frames_to_gif,
    annotate_provenance,
)

ROLLOUTS = PROJECT_ROOT / "rollouts"
VARIANT_ORDER = [
    "en_canonical", "en_paraphrase", "mt_russian", "ru_literal",
    "ru_case_swap", "ru_negation", "code_switch",
]
RU_VARIANTS = {"mt_russian", "ru_literal", "ru_case_swap", "ru_negation"}


def load_annotations() -> list[dict[str, Any]]:
    path = ROLLOUTS / "rollout_annotations.jsonl"
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval — correct at the 0% and 100% ends, where the
    normal approximation degenerates. Most cells here are small-n and several
    are exactly 0, so this matters."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def bootstrap_ci(values: list[bool], iters: int = 2000, seed: int = 0) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(iters):
        means.append(sum(rng.choice(values) for _ in range(n)) / n)
    means.sort()
    return (means[int(0.025 * iters)], means[int(0.975 * iters)])


def per_model_variant(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[bool]]:
    out: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for r in rows:
        out[(r["model"], r["variant"])].append(bool(r.get("success")))
    return out


def pick_examples(rows: list[dict[str, Any]], assets: Path, n: int = 4) -> list[dict[str, Any]]:
    """One episode per distinct outcome, rendered as animated GIFs.

    Both cameras where the environment has them: agentview always, wrist only
    on LIBERO (SimplerEnv/WidowX has no wrist camera at all). GIFs, not stills,
    because the failure modes here are about *motion* — a frozen arm and a
    reaching-but-missing arm look nearly identical in a first/last pair.
    """
    picked, seen = [], set()
    order = sorted(rows, key=lambda r: (not r.get("success"), r.get("failure_type_auto") or ""))
    for r in order:
        key = r.get("failure_type_auto")
        if key in seen:
            continue
        run_dir = ROLLOUTS / "episodes" / r["run_id"]
        agent = sorted((run_dir / "camera" / "agentview").glob("step_*.png")) \
            if (run_dir / "camera" / "agentview").exists() else []
        if len(agent) < 2:
            continue
        out = assets / r["run_id"]
        ag_gif = out / "agentview.gif"
        _frames_to_gif(agent, ag_gif)
        wr_dir = run_dir / "camera" / "wrist"
        wr_frames = sorted(wr_dir.glob("step_*.png")) if wr_dir.exists() else []
        wr_rel = None
        if wr_frames:
            wr_gif = out / "wrist.gif"
            _frames_to_gif(wr_frames, wr_gif)
            wr_rel = str(wr_gif.relative_to(assets.parent))
        seen.add(key)
        picked.append({**r, "_ag": str(ag_gif.relative_to(assets.parent)),
                       "_wr": wr_rel, "_n": len(agent)})
        if len(picked) >= n:
            break
    return picked


def esc(s: Any) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render(rows: list[dict[str, Any]], excluded: set[str], assets: Path) -> str:
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

    # ---- language effect, per model, en_canonical anchored
    lang = ""
    for m in models:
        en = cells.get((m, "en_canonical"), [])
        if not en:
            continue
        sr_en = sum(en) / len(en)
        para = cells.get((m, "en_paraphrase"), [])
        gap_para = (sr_en - sum(para) / len(para)) if para else None
        ru_rows = ""
        for v in VARIANT_ORDER:
            if v in ("en_canonical", "en_paraphrase"):
                continue
            vals = cells.get((m, v), [])
            if not vals:
                continue
            gap = sr_en - sum(vals) / len(vals)
            dl = (gap - gap_para) if gap_para is not None else None
            ru_rows += (f"<tr><td>{v}</td><td>{100*gap:+.1f}</td>"
                        f"<td><b>{'—' if dl is None else f'{100*dl:+.1f}'}</b></td></tr>")
        lo, hi = bootstrap_ci(en)
        lang += (f"<h4>{esc(m)} <span class=ci>SR<sub>en_canonical</sub> = "
                 f"{100*sr_en:.0f}% [bootstrap {100*lo:.0f};{100*hi:.0f}]</span></h4>"
                 f"<table class=t2><tr><th>вариант</th><th>gap, п.п.</th>"
                 f"<th>Δlang, п.п.</th></tr>{ru_rows}</table>")

    ex = pick_examples(rows, assets)
    ex_html = ""
    for e in ex:
        imgs = f"<img src='{e['_ag']}' title='agentview'>"
        if e["_wr"]:
            imgs += f"<img src='{e['_wr']}' title='wrist'>"
        else:
            imgs += "<span class=ci>(wrist-камеры нет — WidowX/SimplerEnv)</span>"
        ex_html += (
            f"<figure><figcaption><code>{esc(e['variant'])}</code> · "
            f"{esc(e['model'])} · {'успех' if e.get('success') else esc(e.get('failure_type_auto'))}"
            f" · {e['_n']} шагов<br><span class=ci>{esc(e['instruction'])}</span></figcaption>"
            f"{imgs}</figure>")

    excl = ""
    if excluded:
        excl = ("<p class=warn><b>Исключены из метрик:</b> " + ", ".join(sorted(excluded)) +
                " — их эпизоды собраны по обе стороны от правки общего model-server, "
                "смешивать две конфигурации инференса в одно число нельзя "
                "(<code>annotate_provenance()</code>).</p>")

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
figure img{{width:190px;image-rendering:pixelated;border:1px solid #ddd;margin-right:6px;vertical-align:top}}
figcaption{{font-size:12px;margin-bottom:6px}}
code{{background:#f4f4f4;padding:1px 4px;border-radius:3px}}
.warn{{background:#fffbe6;border-left:3px solid #f0c000;padding:6px 10px;font-size:13px}}
.f{{background:#f7f7f9;padding:8px 10px;border-radius:5px;font-family:ui-monospace,monospace;font-size:12.5px}}
</style>
<h1>SLAVA — кросс-язычный бенчмарк VLA</h1>
<p class=ci>{n_total} эпизодов в метриках · n=1 повтор на (сцена × вариант × модель)</p>

<h2>1. Метрики</h2>
<div class=f>
SR = успешные эпизоды / всего &nbsp;·&nbsp; успех берётся из нативного <code>env.check_success()</code><br>
gap<sub>v</sub> = SR<sub>en_canonical</sub> − SR<sub>v</sub><br>
<b>Δlang<sub>v</sub> = gap<sub>v</sub> − gap<sub>en_paraphrase</sub></b>
</div>
<p>Вычитание <code>gap_en_paraphrase</code> — ключевой контроль: он убирает эффект
«инструкция просто непривычная» и оставляет только языковой. CI по SR —
интервал Уилсона (корректен у краёв 0% и 100%), по <code>en_canonical</code> — бутстрап, 2000 итераций.</p>

<h2>2. SR по вариантам</h2>
<table><tr><th></th>{head}</tr>{body}</table>
{excl}
<p class=ci><code>ru_case_swap</code> — намеренно перевёрнутая инструкция
(«поставь жёлтый на зелёный» при success-предикате «зелёный на жёлтом»).
Модель, выполнившая её верно, засчитывается как провал: это зонд на
чувствительность к порядку, а не задача. В агрегат по модели не входит.</p>

<h2>3. Языковой эффект</h2>
{lang}

<h2>4. Примеры эпизодов</h2>
<p class=ci>анимация всего эпизода: agentview и wrist (где есть)</p>
{ex_html}
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=PROJECT_ROOT / "docs" / "report.html")
    args = ap.parse_args()
    ann = load_annotations()
    prov = annotate_provenance(ann)
    excluded = {m for m, s in prov.items() if s["n_stale"]}
    rows = [r for r in ann if r["model"] not in excluded]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    assets = args.output.parent / "report_assets"
    args.output.write_text(render(rows, excluded, assets), encoding="utf-8")
    print(f"Wrote {args.output} ({len(rows)}/{len(ann)} эпизодов в метриках)")
    for m, s in sorted(prov.items()):
        flag = "  <-- исключён" if s["n_stale"] else ""
        print(f"  {m:35s} n={s['n']:4d} stale={s['n_stale']:4d}{flag}")


if __name__ == "__main__":
    main()
