"""Tests for src/slava_rollout/auto_label.py — the failure-label ladder that
every behavioral metric in the report is derived from.

Stdlib `unittest` on purpose: this repository is handed to other researchers,
and these must run on a bare `python3` with no pip install:

    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_rollout.auto_label import label_episode  # noqa: E402


def label(**overrides):
    """A non-success episode with sane defaults; override one thing per test."""
    kwargs = dict(
        env_success=False,
        first_contact_object=None,
        touched_objects=[],
        target_object="target_1",
        reference_object=None,
        forbidden_objects=[],
        relation=None,
        action="pick_place",
        final_object_poses={},
        success_predicates=[{"type": "spatial_relation", "relation": "on",
                             "arg1": "target_1", "arg2": "ref_1"}],
        step_count=60,
        max_steps=120,
        ran_to_completion=True,
    )
    kwargs.update(overrides)
    return label_episode(**kwargs)


class TestTimeoutIsEnvironmentIndependent(unittest.TestCase):
    """The bug this suite was written for.

    An episode that ran to the end of its horizon and never touched anything is
    the same physical event whether the horizon was LIBERO's 300 or
    SimplerEnv's native 60. It must get the same label.

    Before the fix it did not: the ladder asked `step_count >= max_steps`, but
    `max_steps` is our OUTER cap (schema.MAX_EPISODE_STEPS), not the env's real
    horizon. SimplerEnv's gymnasium TimeLimit fires at 60 while our cap is 120,
    so the condition was unreachable there and every such episode fell through
    to `unclear`. Real dataset evidence: SimplerEnv had 0 `no_action_or_timeout`
    and 115 `unclear`; LIBERO had 199 and 0. A perfect split by environment is a
    code artifact, not a property of the models.
    """

    def test_libero_full_horizon_no_contact(self):
        got = label(step_count=300, max_steps=300)
        self.assertEqual(got["failure_type_auto"], "no_action_or_timeout")

    def test_simplerenv_native_horizon_below_our_cap(self):
        # 60 native steps, 120 outer cap — the case that used to become `unclear`.
        got = label(step_count=60, max_steps=120)
        self.assertEqual(got["failure_type_auto"], "no_action_or_timeout")

    def test_both_environments_agree(self):
        libero = label(step_count=300, max_steps=300)
        simpler = label(step_count=60, max_steps=120)
        self.assertEqual(libero["failure_type_auto"], simpler["failure_type_auto"])


class TestDegenerateEpisodesStayUnclear(unittest.TestCase):
    """`unclear` must keep meaning "we genuinely cannot tell", not "SimplerEnv"."""

    def test_episode_that_barely_started(self):
        got = label(step_count=1, max_steps=300)
        self.assertEqual(got["failure_type_auto"], "unclear")

    def test_episode_cut_short_by_an_error(self):
        # Stopped before its horizon for a reason other than success/termination
        # (crash, orchestrator kill): we cannot claim the model failed to act.
        got = label(step_count=42, ran_to_completion=False)
        self.assertEqual(got["failure_type_auto"], "unclear")


class TestLabelLadder(unittest.TestCase):
    def test_success_wins_over_everything(self):
        got = label(env_success=True, first_contact_object="distractor_1",
                    touched_objects=["forbidden_1"], forbidden_objects=["forbidden_1"])
        self.assertEqual(got["failure_type_auto"], "success")
        self.assertTrue(got["success"])

    def test_touching_forbidden_is_negation_error(self):
        got = label(first_contact_object="target_1", touched_objects=["target_1", "forbidden_1"],
                    forbidden_objects=["forbidden_1"])
        self.assertEqual(got["failure_type_auto"], "negation_error")
        self.assertTrue(got["forbidden_object_touched"])

    def test_wrong_first_contact_is_target_grounding_error(self):
        got = label(first_contact_object="distractor_1", touched_objects=["distractor_1"])
        self.assertEqual(got["failure_type_auto"], "target_grounding_error")
        self.assertTrue(got["wrong_object"])

    def test_right_target_with_relation_is_relation_binding_error(self):
        got = label(first_contact_object="target_1", touched_objects=["target_1"],
                    reference_object="ref_1", relation="on")
        self.assertEqual(got["failure_type_auto"], "relation_binding_error")

    def test_right_target_without_relation_is_physical_execution_error(self):
        got = label(first_contact_object="target_1", touched_objects=["target_1"],
                    reference_object=None, relation=None)
        self.assertEqual(got["failure_type_auto"], "physical_execution_error")

    def test_every_label_is_in_the_fixed_task_md_set(self):
        from slava_rollout.schema import FAILURE_LABELS
        cases = [
            label(),
            label(env_success=True),
            label(first_contact_object="distractor_1"),
            label(first_contact_object="target_1", touched_objects=["target_1"]),
            label(step_count=1),
        ]
        for got in cases:
            self.assertIn(got["failure_type_auto"], FAILURE_LABELS)


class TestDerivedFields(unittest.TestCase):
    def test_wrong_object_needs_a_known_target(self):
        got = label(first_contact_object="something", target_object=None)
        self.assertFalse(got["wrong_object"])

    def test_conditional_execution_is_null_without_contact(self):
        self.assertIsNone(label()["conditional_execution_success"])

    def test_conditional_execution_is_null_when_target_was_wrong(self):
        got = label(first_contact_object="distractor_1")
        self.assertIsNone(got["conditional_execution_success"])

    def test_conditional_execution_set_when_grounding_was_right(self):
        got = label(first_contact_object="target_1", touched_objects=["target_1"])
        self.assertIs(got["conditional_execution_success"], False)

    def test_relation_success_is_null_without_predicates(self):
        self.assertIsNone(label(success_predicates=[])["final_relation_success"])


if __name__ == "__main__":
    unittest.main()


class NegationAxisTest(unittest.TestCase):
    """negation_error принадлежит оси отрицания, а не любой сцене.

    `forbidden_objects` заполнены у всех вариантов сцены — это удобный сырой
    сигнал. Но запрет существует только там, где инструкция его произносит:
    до 07.08.2026 метка ставилась на en_canonical/mt_russian/ru_literal/
    code_switch, где никакого «не X, а Y» в тексте не было (17 эпизодов из 21).
    """

    def _label(self, variant):
        return label_episode(
            env_success=False,
            first_contact_object="bowl",
            touched_objects=["bowl", "forbidden_thing"],
            target_object="plate",
            reference_object=None,
            forbidden_objects=["forbidden_thing"],
            variant=variant,
            relation=None,
            action="pick",
            final_object_poses={},
            success_predicates=[{"type": "state"}],
            step_count=50,
        )

    def test_negation_error_only_on_the_negation_variant(self) -> None:
        self.assertEqual(self._label("ru_negation")["failure_type_auto"], "negation_error")

    def test_other_variants_fall_through_to_the_normal_rules(self) -> None:
        for variant in ("en_canonical", "mt_russian", "ru_literal", "code_switch"):
            with self.subTest(variant=variant):
                self.assertEqual(
                    self._label(variant)["failure_type_auto"], "target_grounding_error"
                )

    def test_raw_signal_is_still_recorded_for_every_variant(self) -> None:
        # Поле остаётся: по нему можно пересчитать более строгое правило, не
        # перезапуская прогоны.
        self.assertTrue(self._label("en_canonical")["forbidden_object_touched"])


class CaseSwapSuccessTest(unittest.TestCase):
    """У `ru_case_swap` успех — про перевёрнутую инструкцию, а не про предикат среды.

    Предикат намеренно не переворачивается вместе с текстом, поэтому env_success
    отвечает «сделал ли робот ИСХОДНОЕ задание»: высокий SR означал бы «модель не
    заметила перестановку». Решение пользователя 07.08.2026 — считать успехом то,
    о чём просила перевёрнутая инструкция.
    """

    def _label(self, variant, poses, env_success=True):
        return label_episode(
            env_success=env_success,
            first_contact_object="bowl_1",
            touched_objects=["bowl_1"],
            target_object="bowl_1",
            reference_object="plate_1",
            forbidden_objects=[],
            variant=variant,
            relation="on",
            action="pick_place",
            final_object_poses=poses,
            success_predicates=[{"type": "spatial_relation"}],
            step_count=50,
        )

    def test_following_the_swap_counts_as_success(self) -> None:
        # Тарелка оказалась на миске — робот сделал то, о чём просили.
        out = self._label("ru_case_swap", {"bowl_1": [0.0, 0.0, 0.87], "plate_1": [0.0, 0.0, 0.90]})
        self.assertTrue(out["success"])
        self.assertEqual(out["success_source"], "swapped_predicate")

    def test_ignoring_the_swap_is_a_failure_even_if_the_env_says_success(self) -> None:
        out = self._label("ru_case_swap", {"bowl_1": [0.0, 0.0, 0.90], "plate_1": [0.4, 0.3, 0.87]})
        self.assertFalse(out["success"])

    def test_other_variants_keep_the_environment_predicate(self) -> None:
        out = self._label("ru_literal", {})
        self.assertTrue(out["success"])
        self.assertEqual(out["success_source"], "env")

    def test_missing_poses_fall_back_to_the_environment(self) -> None:
        # «Не знаю» не должно превращаться в «не выполнил».
        out = self._label("ru_case_swap", {})
        self.assertEqual(out["success_source"], "env")


class LiftRuleTest(unittest.TestCase):
    """Нельзя нарушить отношение объектом, который ни разу не подняли.

    До 07.08.2026 такие эпизоды получали `relation_binding_error` по остаточному
    принципу (цель тронута, отношение не достигнуто) — и это было самое частое
    расхождение с человеком после починки negation: он видел «коснулся, но не
    смог взять», то есть `physical_execution_error`.
    """

    def _label(self, target_lifted):
        return label_episode(
            env_success=False, first_contact_object="bowl", touched_objects=["bowl"],
            target_object="bowl", reference_object="plate", forbidden_objects=[],
            variant="en_canonical", relation="on", action="pick_place",
            final_object_poses={}, success_predicates=[{"type": "spatial_relation"}],
            step_count=100, target_lifted=target_lifted,
        )

    def test_never_lifted_is_a_physical_failure(self) -> None:
        self.assertEqual(self._label(False)["failure_type_auto"], "physical_execution_error")

    def test_lifted_but_relation_unmet_stays_a_relation_error(self) -> None:
        self.assertEqual(self._label(True)["failure_type_auto"], "relation_binding_error")

    def test_unknown_lift_keeps_the_previous_behaviour(self) -> None:
        # None означает «поз не было» — не повод менять вывод.
        self.assertEqual(self._label(None)["failure_type_auto"], "relation_binding_error")
