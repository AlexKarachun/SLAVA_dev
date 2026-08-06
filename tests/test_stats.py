"""Tests for src/slava_rollout/stats.py.

    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_rollout.stats import (  # noqa: E402
    bootstrap_ci,
    delta_lang,
    discordant,
    mcnemar_exact,
    outcomes_by_variant,
    paired_outcomes,
    wilson,
)


class TestWilson(unittest.TestCase):
    """Checked against published Wilson score interval values."""

    def test_zero_successes_has_nonzero_upper_bound(self):
        lo, hi = wilson(0, 4)
        self.assertAlmostEqual(lo, 0.0, places=6)
        self.assertAlmostEqual(hi, 0.4899, places=3)

    def test_symmetric_case(self):
        lo, hi = wilson(2, 4)
        self.assertAlmostEqual(lo, 0.1500, places=3)
        self.assertAlmostEqual(hi, 0.8500, places=3)

    def test_large_sample(self):
        lo, hi = wilson(74, 99)
        self.assertAlmostEqual(lo, 0.6538, places=3)
        self.assertAlmostEqual(hi, 0.8227, places=3)

    def test_empty(self):
        self.assertEqual(wilson(0, 0), (0.0, 0.0))


class TestMcNemar(unittest.TestCase):
    def test_no_discordant_pairs_is_undefined_not_significant(self):
        # Every scene agreed. There is no evidence of a difference — which is
        # not the same claim as "the difference is not significant".
        self.assertIsNone(mcnemar_exact(0, 0))

    def test_perfectly_one_sided_small_sample(self):
        # b=5, c=0 -> 2 * 0.5^5 = 0.0625; not significant at 0.05 despite a
        # clean 5-0 split, which is exactly the small-n caution we want.
        self.assertAlmostEqual(mcnemar_exact(5, 0), 0.0625, places=6)

    def test_perfectly_one_sided_reaches_significance_at_six(self):
        self.assertAlmostEqual(mcnemar_exact(6, 0), 0.03125, places=6)

    def test_symmetric_is_not_significant(self):
        self.assertAlmostEqual(mcnemar_exact(4, 4), 1.0, places=6)

    def test_is_symmetric_in_its_arguments(self):
        self.assertEqual(mcnemar_exact(7, 2), mcnemar_exact(2, 7))

    def test_never_exceeds_one(self):
        for b in range(6):
            for c in range(6):
                p = mcnemar_exact(b, c)
                if p is not None:
                    self.assertLessEqual(p, 1.0)
                    self.assertGreater(p, 0.0)


class TestPairing(unittest.TestCase):
    def test_only_shared_scenes_are_compared(self):
        a = {"s1": True, "s2": False, "s3": True}
        b = {"s2": True, "s3": False}
        av, bv, scenes = paired_outcomes(a, b)
        self.assertEqual(scenes, ["s2", "s3"])
        self.assertEqual(av, [False, True])
        self.assertEqual(bv, [True, False])

    def test_discordant_counts(self):
        a = [True, True, False, False]
        b = [False, True, True, False]
        self.assertEqual(discordant(a, b), (1, 1))


class TestDeltaLang(unittest.TestCase):
    def _by_variant(self, en, para, ru):
        return {
            "en_canonical": en,
            "en_paraphrase": para,
            "ru_literal": ru,
        }

    def test_no_language_effect_when_ru_matches_paraphrase(self):
        # Anchor 4/4; paraphrase and ru both 2/4 -> gaps equal -> Δlang == 0.
        en = {f"s{i}": True for i in range(4)}
        para = {"s0": True, "s1": True, "s2": False, "s3": False}
        ru = {"s0": True, "s1": True, "s2": False, "s3": False}
        got = delta_lang(self._by_variant(en, para, ru), "ru_literal")
        self.assertAlmostEqual(got["value"], 0.0, places=9)

    def test_language_effect_when_ru_is_worse_than_paraphrase(self):
        en = {f"s{i}": True for i in range(4)}
        para = {f"s{i}": True for i in range(4)}   # paraphrase costs nothing
        ru = {f"s{i}": False for i in range(4)}    # russian loses everything
        got = delta_lang(self._by_variant(en, para, ru), "ru_literal")
        self.assertAlmostEqual(got["value"], 1.0, places=9)
        self.assertEqual(got["n_scenes"], 4)

    def test_uses_only_the_triple_intersection(self):
        # ru_literal covers one scene the others do not; it must be ignored
        # rather than inflating/deflating the marginal rate.
        en = {"s0": True, "s1": True}
        para = {"s0": True, "s1": True}
        ru = {"s0": False, "s1": False, "s_extra": True}
        got = delta_lang(self._by_variant(en, para, ru), "ru_literal")
        self.assertEqual(got["n_scenes"], 2)
        self.assertAlmostEqual(got["value"], 1.0, places=9)

    def test_composition_confound_is_actually_prevented(self):
        # The bug this guards: ru_case_swap exists only on the hard scenes.
        # Marginal SR would read as a huge language effect; paired on shared
        # scenes there is none.
        en = {"easy1": True, "easy2": True, "hard1": False}
        para = {"easy1": True, "easy2": True, "hard1": False}
        swap = {"hard1": False}          # only the hard scene was authored
        got = delta_lang({"en_canonical": en, "en_paraphrase": para,
                          "ru_case_swap": swap}, "ru_case_swap")
        self.assertEqual(got["n_scenes"], 1)
        self.assertAlmostEqual(got["value"], 0.0, places=9)

    def test_returns_none_without_shared_scenes(self):
        got = delta_lang({"en_canonical": {"a": True}, "en_paraphrase": {"a": True},
                          "ru_literal": {"b": False}}, "ru_literal")
        self.assertIsNone(got)

    def test_ci_brackets_the_point_estimate(self):
        en = {f"s{i}": True for i in range(8)}
        para = {f"s{i}": i % 2 == 0 for i in range(8)}
        ru = {f"s{i}": False for i in range(8)}
        got = delta_lang(self._by_variant(en, para, ru), "ru_literal")
        lo, hi = got["ci"]
        self.assertLessEqual(lo, got["value"] + 1e-9)
        self.assertGreaterEqual(hi, got["value"] - 1e-9)


class TestOutcomesByVariant(unittest.TestCase):
    def test_groups_by_variant_and_scene(self):
        rows = [
            {"variant": "en_canonical", "task_uid": "s1", "success": True},
            {"variant": "en_canonical", "task_uid": "s2", "success": False},
            {"variant": "ru_literal", "task_uid": "s1", "success": False},
        ]
        got = outcomes_by_variant(rows)
        self.assertEqual(got["en_canonical"], {"s1": True, "s2": False})
        self.assertEqual(got["ru_literal"], {"s1": False})


class TestBootstrap(unittest.TestCase):
    def test_constant_sample_has_degenerate_interval(self):
        lo, hi = bootstrap_ci([1.0] * 20)
        self.assertAlmostEqual(lo, 1.0, places=9)
        self.assertAlmostEqual(hi, 1.0, places=9)

    def test_is_deterministic_for_a_fixed_seed(self):
        vals = [1.0, 0.0, 1.0, 1.0, 0.0, 1.0, 0.0]
        self.assertEqual(bootstrap_ci(vals), bootstrap_ci(vals))



class TestDiagnostics(unittest.TestCase):
    def test_first_contact_profile_splits_three_ways(self):
        from slava_rollout.stats import first_contact_profile
        rows = [
            {"first_contact_object": "t", "target_object": "t"},   # correct
            {"first_contact_object": "d", "target_object": "t"},   # wrong object
            {"first_contact_object": None, "target_object": "t"},  # never touched
            {"first_contact_object": None, "target_object": "t"},
        ]
        got = first_contact_profile(rows)
        self.assertEqual(got["n"], 4)
        self.assertAlmostEqual(got["correct_target"], 0.25)
        self.assertAlmostEqual(got["wrong_target"], 0.25)
        self.assertAlmostEqual(got["no_contact"], 0.50)
        # the three shares must partition the episodes
        self.assertAlmostEqual(
            got["correct_target"] + got["wrong_target"] + got["no_contact"], 1.0
        )

    def test_first_contact_profile_handles_empty(self):
        from slava_rollout.stats import first_contact_profile
        self.assertEqual(first_contact_profile([])["n"], 0)

    def test_cluster_summary_counts_tasks_not_scenes(self):
        from slava_rollout.stats import cluster_summary
        got = cluster_summary([
            "libero_goal__put_the_wine_bottle_on_the_rack__init000",
            "libero_goal__put_the_wine_bottle_on_the_rack__init017",
            "libero_goal__put_the_wine_bottle_on_the_rack__init034",
            "libero_goal__turn_on_the_stove__init000",
        ])
        self.assertEqual(got["n_scenes"], 4)
        self.assertEqual(got["n_tasks"], 2)
        self.assertEqual(got["max_scenes_per_task"], 3)

    def test_paired_by_task_collapses_init_states(self):
        from slava_rollout.stats import paired_by_task
        # One task, three init states: anchor wins on one, variant never wins.
        # Scene level would say 1 discordant; task level also says 1 — but a
        # second task whose init states disagree must not double-count.
        a = {"t1__init000": True, "t1__init017": False, "t2__init000": True}
        b = {"t1__init000": False, "t1__init017": False, "t2__init000": True}
        only_a, only_b = paired_by_task(a, b)
        self.assertEqual((only_a, only_b), (1, 0))

    def test_failure_mix_sums_to_one(self):
        from slava_rollout.stats import failure_mix
        rows = [{"failure_type_auto": x} for x in
                ["success", "success", "target_grounding_error", "no_action_or_timeout"]]
        got = failure_mix(rows)
        self.assertAlmostEqual(sum(got.values()), 1.0)
        self.assertAlmostEqual(got["success"], 0.5)

if __name__ == "__main__":
    unittest.main()
