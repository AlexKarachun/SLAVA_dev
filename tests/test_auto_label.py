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
