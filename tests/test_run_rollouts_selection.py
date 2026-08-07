"""Prompt selection in scripts/run_rollouts.py.

Covers the two flags added for harness validation (--variants, --prompts):
restricting to one instruction variant must not disturb the environment
filtering that decides which model may run where, and an alternative prompts
file must be read instead of the frozen pilot manifest, not in addition to it.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# run_rollouts imports the HTTP clients at module level; `requests` belongs to
# the slava-notebook env, not to whatever interpreter runs the tests. Prompt
# selection is pure data handling and never touches it, so a stub keeps this
# test runnable anywhere.
for heavy in ("requests", "numpy", "PIL", "PIL.Image"):
    sys.modules.setdefault(heavy, type(sys)(heavy))

spec = importlib.util.spec_from_file_location(
    "run_rollouts", PROJECT_ROOT / "scripts" / "run_rollouts.py"
)
run_rollouts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_rollouts)


def prompt(task: str, variant: str, environment: str) -> dict:
    return {
        "prompt_id": f"{task}__{variant}",
        "task_uid": task,
        "variant": variant,
        "environment": environment,
        "instruction": "x",
    }


class SelectPromptsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.prompts = [
            prompt("libero_a", "en_canonical", "LIBERO"),
            prompt("libero_a", "ru_literal", "LIBERO"),
            prompt("simpler_a", "en_canonical", "SimplerEnv"),
            prompt("simpler_a", "ru_literal", "SimplerEnv"),
        ]

    def test_variant_filter_keeps_only_that_variant(self) -> None:
        selected = run_rollouts.select_prompts(
            self.prompts, "pi0", smoke_test=False, variants=["en_canonical"]
        )
        self.assertTrue(selected)
        self.assertEqual({p["variant"] for p in selected}, {"en_canonical"})

    def test_variant_filter_does_not_widen_environments(self) -> None:
        # greenvla_r0 exists only for SimplerEnv; asking for en_canonical must
        # not let a LIBERO row through the environment gate.
        selected = run_rollouts.select_prompts(
            self.prompts, "greenvla_r0", smoke_test=False, variants=["en_canonical"]
        )
        self.assertEqual({p["environment"] for p in selected}, {"SimplerEnv"})

    def test_no_variant_filter_keeps_everything_for_the_environment(self) -> None:
        selected = run_rollouts.select_prompts(self.prompts, "pi0", smoke_test=False)
        self.assertEqual(len(selected), 4)

    def test_alternative_prompts_file_replaces_the_default(self) -> None:
        rows = [prompt("simpler_z", "en_canonical", "SimplerEnv")]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as handle:
            handle.write(json.dumps(rows[0]) + "\n")
            path = Path(handle.name)
        try:
            loaded = run_rollouts.load_prompts(path)
        finally:
            path.unlink()
        self.assertEqual(loaded, rows)



class StoragePoolTest(unittest.TestCase):
    """Every run must land in exactly one pool, chosen in one place.

    The pool layout exists because run_ids collide across pools by design (the
    same scene collected twice on different hardware), so a run writing into
    the wrong directory would silently corrupt a finished dataset.
    """

    def test_paths_follow_the_active_pool(self) -> None:
        import importlib

        import slava_rollout.storage as storage

        os_environ_backup = dict(os.environ)
        try:
            os.environ["SLAVA_RUN_POOL"] = "some_new_pool"
            storage = importlib.reload(storage)
            self.assertTrue(str(storage.annotations_path()).endswith(
                "rollouts/final/some_new_pool/rollout_annotations.jsonl"))
            self.assertTrue(str(storage.episode_dir("r")).endswith(
                "rollouts/final/some_new_pool/episodes/r"))
            self.assertTrue(str(storage.run_log_path("r")).endswith(
                "rollouts/final/some_new_pool/logs/r.log"))
        finally:
            os.environ.clear()
            os.environ.update(os_environ_backup)
            importlib.reload(storage)

    def test_default_pool_is_the_pilot(self) -> None:
        import slava_rollout.storage as storage

        self.assertEqual(storage.DEFAULT_POOL, "pilot_v0")
        self.assertTrue(str(storage.pool_root("pilot_v0")).endswith("rollouts/final/pilot_v0"))


class EpisodeDirHygieneTest(unittest.TestCase):
    """A re-run must not inherit the previous attempt's frames.

    Overwriting frames 1..N leaves N+1..M from a longer earlier run in place,
    and the result is a directory holding two different episodes — invisible in
    the metrics, very visible to anyone reviewing the footage.
    """

    def test_ensure_episode_dirs_clears_previous_attempt(self) -> None:
        import importlib
        import tempfile

        import slava_rollout.storage as storage

        with tempfile.TemporaryDirectory() as tmp:
            storage = importlib.reload(storage)
            storage.ROLLOUTS_ROOT = Path(tmp)
            run_id = "some__episode"
            frames = storage.camera_dir(run_id, "agentview")
            frames.mkdir(parents=True)
            for i in (1, 2, 60):
                (frames / f"step_{i:04d}.png").write_bytes(b"old")
            storage.steps_path(run_id).write_text('{"step": 1}\n')

            storage.ensure_episode_dirs(run_id, has_wrist=False)

            self.assertEqual(list(frames.glob("step_*.png")), [])
            self.assertFalse(storage.steps_path(run_id).exists())
        importlib.reload(storage)


class AuthorHorizonTest(unittest.TestCase):
    """Горизонт эпизода должен совпадать с авторским, иначе сравнение нечестно.

    Числа из `TASK_MAX_STEPS` в moojink/openvla-oft (сверено 08.08.2026).
    До 08.08.2026 у нас стоял единый лимит 300 на все сьюты LIBERO: по
    `libero_spatial` это на 80 шагов щедрее авторского, по `libero_object` на 20.
    На собранных данных это ничего не завысило (ни один успех не случился после
    авторского лимита), но на будущих прогонах разошлось бы.
    """

    def test_per_suite_limits_match_the_authors(self) -> None:
        from slava_rollout.schema import max_steps_for

        for suite, expected in (
            ("libero_spatial", 220), ("libero_object", 280),
            ("libero_goal", 300), ("libero_10", 520), ("libero_90", 400),
        ):
            with self.subTest(suite=suite):
                self.assertEqual(max_steps_for("LIBERO", f"{suite}__task__init000"), expected)

    def test_unknown_suite_falls_back_to_the_outer_cap(self) -> None:
        from slava_rollout.schema import MAX_EPISODE_STEPS, max_steps_for

        self.assertEqual(max_steps_for("LIBERO", "unknown__x"), MAX_EPISODE_STEPS["LIBERO"])

    def test_simplerenv_keeps_the_outer_cap_because_the_env_terminates_first(self) -> None:
        from slava_rollout.schema import max_steps_for

        self.assertEqual(max_steps_for("SimplerEnv", "simpler__widowx"), 120)

if __name__ == "__main__":
    unittest.main()
