"""Statistics for the behavioral pilot: paired variant comparison, Δlang, CIs.

Stdlib only (no scipy/numpy) so the report can be regenerated from a bare
`python3` on any machine the dataset is handed to.

The central point of this module is that SLAVA's design is PAIRED — task.md:
"парный дизайн (одна сцена/сид, разные инструкции)". Every scene is run with
every instruction variant, so a variant comparison must be made scene-by-scene
against the same scenes. Comparing marginal success rates instead silently
mixes the language effect with scene composition, and the composition really
does differ here: `ru_case_swap` is only authored for 8 of 20 scenes (the rest
are legitimately `axis_na`), and partial runs left some models with ragged
per-variant coverage. Marginal SR over "whatever rows exist" is not the same
quantity for two variants and must not be subtracted.
"""
from __future__ import annotations

import math
import random
from typing import Any, Iterable, Optional

# --------------------------------------------------------------------------
# Interval estimates
# --------------------------------------------------------------------------


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Correct at the 0% and 100% ends, where the normal approximation collapses
    to a zero-width interval. Most cells here are small-n and several are
    exactly 0/n, so this matters.
    """
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def bootstrap_ci(
    values: list[float], iters: int = 2000, seed: int = 0, alpha: float = 0.05
) -> tuple[float, float]:
    """Percentile bootstrap CI for a mean."""
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(n)) / n for _ in range(iters))
    lo = means[max(0, int(alpha / 2 * iters))]
    hi = means[min(iters - 1, int((1 - alpha / 2) * iters))]
    return (lo, hi)


# --------------------------------------------------------------------------
# Paired tests
# --------------------------------------------------------------------------


def mcnemar_exact(b: int, c: int) -> Optional[float]:
    """Two-sided exact McNemar p-value for paired binary outcomes.

    `b` and `c` are the DISCORDANT counts: scenes where A succeeded and B
    failed, and vice versa. Concordant pairs carry no information about a
    difference and are excluded by construction — that is the whole point of
    the test, and why it is the right one for this design (task.md names it
    explicitly).

    Exact binomial rather than the chi-square approximation because the
    discordant counts here are tiny (often < 10), where chi-square is not
    trustworthy. Returns None when there are no discordant pairs at all: with
    b == c == 0 the data contain no evidence either way, which is different
    from "no significant difference".
    """
    n = b + c
    if n == 0:
        return None
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) * (0.5 ** n)
    return min(1.0, 2 * tail)


def paired_outcomes(
    rows_a: dict[str, bool], rows_b: dict[str, bool]
) -> tuple[list[bool], list[bool], list[str]]:
    """Align two {scene: success} maps on the scenes they share.

    Returns (a_values, b_values, scenes) in a stable scene order. Scenes
    present for only one variant are dropped — they cannot contribute to a
    paired comparison, and including them is exactly the composition bug this
    module exists to prevent.
    """
    scenes = sorted(set(rows_a) & set(rows_b))
    return [rows_a[s] for s in scenes], [rows_b[s] for s in scenes], scenes


def discordant(a: list[bool], b: list[bool]) -> tuple[int, int]:
    """(b, c) discordant counts: A-only successes, B-only successes."""
    only_a = sum(1 for x, y in zip(a, b) if x and not y)
    only_b = sum(1 for x, y in zip(a, b) if y and not x)
    return only_a, only_b


# --------------------------------------------------------------------------
# Δlang
# --------------------------------------------------------------------------


def delta_lang(
    by_variant: dict[str, dict[str, bool]],
    variant: str,
    anchor: str = "en_canonical",
    control: str = "en_paraphrase",
) -> Optional[dict[str, Any]]:
    """Δlang for one variant, computed strictly on shared scenes.

    Δlang_v = gap_v − gap_control, where gap_x = SR_anchor − SR_x.

    task.md calls Δlang "главная метрика пилота" precisely because subtracting
    the English-paraphrase gap removes the "this instruction string is simply
    unfamiliar" effect and leaves the language effect. That subtraction is only
    meaningful if all three quantities come from the SAME scenes, so everything
    here is computed on the anchor ∩ control ∩ variant intersection rather than
    on each variant's own marginal coverage.

    Returns None when the three variants share no scenes.
    """
    anchor_map = by_variant.get(anchor, {})
    control_map = by_variant.get(control, {})
    variant_map = by_variant.get(variant, {})
    scenes = sorted(set(anchor_map) & set(control_map) & set(variant_map))
    if not scenes:
        return None

    a = [anchor_map[s] for s in scenes]
    c = [control_map[s] for s in scenes]
    v = [variant_map[s] for s in scenes]

    sr = lambda xs: sum(xs) / len(xs)  # noqa: E731
    gap_variant = sr(a) - sr(v)
    gap_control = sr(a) - sr(c)
    value = gap_variant - gap_control

    # Paired bootstrap: resample SCENES (the unit of pairing), not episodes,
    # so the anchor/control/variant outcomes of a scene move together exactly
    # as they are correlated in the real design.
    rng = random.Random(0)
    n = len(scenes)
    draws = []
    for _ in range(2000):
        idx = [rng.randrange(n) for _ in range(n)]
        aa = sum(a[i] for i in idx) / n
        cc = sum(c[i] for i in idx) / n
        vv = sum(v[i] for i in idx) / n
        draws.append((aa - vv) - (aa - cc))
    draws.sort()

    b_disc, c_disc = discordant(a, v)
    return {
        "value": value,
        "gap_variant": gap_variant,
        "gap_control": gap_control,
        "n_scenes": n,
        "ci": (draws[50], draws[1949]),
        "p_mcnemar_vs_anchor": mcnemar_exact(b_disc, c_disc),
        "discordant": (b_disc, c_disc),
    }


def outcomes_by_variant(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, bool]]:
    """{variant: {task_uid: success}} for one model's annotation rows.

    n=1 repeat per (scene, variant, model) is the project's fixed design
    (schema.DEFAULT_N_REPEATS), so one row per key is expected; if repeats are
    ever added, this needs to aggregate instead of overwrite.
    """
    out: dict[str, dict[str, bool]] = {}
    for row in rows:
        out.setdefault(row["variant"], {})[row["task_uid"]] = bool(row.get("success"))
    return out


# --------------------------------------------------------------------------
# Diagnostics beyond success rate
# --------------------------------------------------------------------------


def first_contact_profile(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Where an episode went wrong, one level below success/failure.

    SR alone cannot separate "understood the instruction but fumbled the grasp"
    from "reached for the wrong object" from "never moved". `first_contact_object`
    can: it is the first task object the gripper actually touched, recorded by
    the contact tracker at collection time. This is the slot-level attribution
    the project is built around (task.md's H-understanding / H-grounding /
    H-binding), so it belongs in the report next to SR rather than only in the
    raw JSONL.
    """
    rows = list(rows)
    n = len(rows)
    if not n:
        return {"n": 0, "correct_target": None, "wrong_target": None, "no_contact": None}
    correct = sum(
        1 for r in rows
        if r.get("first_contact_object") and r["first_contact_object"] == r.get("target_object")
    )
    none = sum(1 for r in rows if not r.get("first_contact_object"))
    return {
        "n": n,
        "correct_target": correct / n,
        "wrong_target": (n - correct - none) / n,
        "no_contact": none / n,
    }


def failure_mix(rows: Iterable[dict[str, Any]]) -> dict[str, float]:
    """Share of each failure_type_auto — does one variant fail *differently*?"""
    rows = list(rows)
    if not rows:
        return {}
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["failure_type_auto"]] = counts.get(r["failure_type_auto"], 0) + 1
    return {k: v / len(rows) for k, v in sorted(counts.items(), key=lambda kv: -kv[1])}


def cluster_summary(scenes: Iterable[str]) -> dict[str, Any]:
    """Scenes are not independent: several share one task, differing only by init state.

    A LIBERO `task_uid` is `<suite>__<task_name>__init<NNN>`, so stripping the
    suffix recovers the task. Our 16 LIBERO scenes are only 9 distinct tasks
    (one contributes 4 init states), which means a scene-level test overstates
    how much independent evidence there is. Reported explicitly rather than
    left for a reader to discover.
    """
    scenes = list(scenes)
    tasks: dict[str, int] = {}
    for s in scenes:
        task = s.rsplit("__init", 1)[0]
        tasks[task] = tasks.get(task, 0) + 1
    return {
        "n_scenes": len(scenes),
        "n_tasks": len(tasks),
        "max_scenes_per_task": max(tasks.values()) if tasks else 0,
    }


def paired_by_task(
    a_map: dict[str, bool], b_map: dict[str, bool]
) -> tuple[int, int]:
    """Discordant counts aggregated to TASK level, not scene level.

    A task counts as a loss only if it succeeded under the anchor on at least
    one init state and failed under the variant on all of them (and vice
    versa) — the conservative reading. Used to show how much of the
    scene-level significance survives once init states of the same task stop
    being treated as independent samples.
    """
    tasks: dict[str, list[str]] = {}
    for scene in set(a_map) & set(b_map):
        tasks.setdefault(scene.rsplit("__init", 1)[0], []).append(scene)
    only_a = only_b = 0
    for scenes in tasks.values():
        a_any = any(a_map[s] for s in scenes)
        b_any = any(b_map[s] for s in scenes)
        if a_any and not b_any:
            only_a += 1
        elif b_any and not a_any:
            only_b += 1
    return only_a, only_b
