from __future__ import annotations

from typing import Any

# Failure labels: fixed set from task.md "Failure labels". Do not invent free-form labels.
FAILURE_LABELS = (
    "success",
    "target_grounding_error",
    "reference_grounding_error",
    "relation_binding_error",
    "negation_error",
    "physical_execution_error",
    "no_action_or_timeout",
    "unclear",
)

# rollout_annotations.jsonl fields, exact set from task.md "Auto-labeling для первых прогонов".
ROLLOUT_ANNOTATION_FIELDS = (
    "run_id",
    "model",
    "task_uid",
    "variant",
    "instruction",
    "seed",
    "success",
    "first_contact_object",
    "target_object",
    "reference_object",
    "wrong_object",
    "forbidden_object_touched",
    "final_relation_success",
    "conditional_execution_success",
    "failure_type_auto",
    "notes",
)

# task.md "Модели и среды" + AGENTS.md "Модели — 5, не 4" / "Модель → среда":
# GreenVLA counted as two separate models (R0-base, R1-bridge); pi0/pi0.5 and SmolVLA
# run on BOTH environments (user's explicit decision, not task.md's narrower table).
# Checkpoints researched via WebSearch/WebFetch in the 2026-08-04 implementation session,
# confirmed with the user for the SimplerEnv/bridge zero-shot risk — see AGENTS.md
# "Текущее состояние проекта" decision log for sourcing/rationale. Re-verify if this
# session is picked up much later; HF repos can move.
MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "greenvla_r0": {
        "display_name": "GreenVLA-R0",
        "backbone": "Qwen3-VL-4B-Instruct",
        "environments": {
            "SimplerEnv": {
                "checkpoint": "SberRoboticsCenter/GreenVLA-5b-base-stride-1",
                "data_config_name": "bridge",
                "zero_shot": False,
            },
        },
    },
    "greenvla_r1_bridge": {
        "display_name": "GreenVLA-R1 (bridge)",
        "backbone": "Qwen3-VL-4B-Instruct",
        "environments": {
            "SimplerEnv": {
                "checkpoint": "SberRoboticsCenter/GreenVLA-5b-stride-1-R1-bridge",
                "data_config_name": "bridge",
                "zero_shot": False,
            },
        },
    },
    "openvla_oft": {
        "display_name": "OpenVLA-OFT",
        "backbone": "Prismatic (openvla-7b)",
        "environments": {
            "LIBERO": {
                "checkpoint": "moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10",
                "zero_shot": False,
            },
        },
    },
    "pi0": {
        "display_name": "pi0",
        "backbone": "PaliGemma",
        "environments": {
            "LIBERO": {"checkpoint": "lerobot/pi0_libero_finetuned", "zero_shot": False},
            "SimplerEnv": {"checkpoint": "lerobot/pi0_base", "zero_shot": True},
        },
    },
    "pi05": {
        "display_name": "pi0.5",
        "backbone": "PaliGemma",
        "environments": {
            "LIBERO": {"checkpoint": "lerobot/pi05_libero_finetuned", "zero_shot": False},
            "SimplerEnv": {"checkpoint": "lerobot/pi05_base", "zero_shot": True},
        },
    },
    "smolvla": {
        "display_name": "SmolVLA",
        "backbone": "HuggingFaceTB/SmolVLM2-500M-Video-Instruct",
        "environments": {
            "LIBERO": {"checkpoint": "HuggingFaceVLA/smolvla_libero", "zero_shot": False},
            "SimplerEnv": {"checkpoint": "lerobot/smolvla_base", "zero_shot": True},
        },
    },
}

# Repeats per (scene, variant, model): user's explicit decision — n=1 for every model,
# for simplicity of table comparison (not split by deterministic/stochastic action head).
DEFAULT_N_REPEATS = 1

# Camera logging: user's explicit decision — one PNG frame per step, both agentview and
# wrist (where the environment has a wrist camera; SimplerEnv/WidowX does not).
CAMERA_FORMAT = "png_per_step"

# Outer safety caps, not the actual per-task horizon for SimplerEnv: each gym
# env is registered with its own max_episode_steps (e.g.
# StackGreenCubeOnYellowCube*=60, OpenDrawer*=113 — see
# ManiSkill2_real2sim/envs/custom_scenes/*.py @register_env(...,
# max_episode_steps=N)), enforced by gymnasium's TimeLimit wrapper inside
# simpler_env.make(). An episode ending well under 120 steps with done=True
# is that native horizon firing, not a bug — confirmed against the real
# registration values, not assumed.
MAX_EPISODE_STEPS = {
    "LIBERO": 300,
    "SimplerEnv": 120,
}


def models_for_environment(environment: str) -> list[str]:
    return [key for key, spec in MODEL_REGISTRY.items() if environment in spec["environments"]]


def environments_for_model(model_key: str) -> list[str]:
    return list(MODEL_REGISTRY[model_key]["environments"].keys())


def checkpoint_for(model_key: str, environment: str) -> str:
    return MODEL_REGISTRY[model_key]["environments"][environment]["checkpoint"]


def build_run_id(model_key: str, prompt_id: str, seed: int) -> str:
    """run_id convention: <prompt_id>__<model_key>__seed<seed:03d>.

    prompt_id already uniquely identifies (task_uid, variant) per
    data/pilot_v0_release/prompts_v0.jsonl — this keeps run_id traceable back to that file
    without inventing a parallel id scheme. task.md's run_id example
    ("openvla_libero_spatial_003_ru_literal_seed000") is illustrative free text, not a
    strict grammar; this is the concrete scheme actually used.
    """
    return f"{prompt_id}__{model_key}__seed{seed:03d}"


def validate_rollout_annotation(record: dict[str, Any]) -> None:
    missing = [f for f in ROLLOUT_ANNOTATION_FIELDS if f not in record]
    if missing:
        raise ValueError(f"rollout_annotations record missing fields: {missing}")
    extra = [f for f in record if f not in ROLLOUT_ANNOTATION_FIELDS]
    if extra:
        raise ValueError(f"rollout_annotations record has unexpected fields: {extra}")
    if record["failure_type_auto"] not in FAILURE_LABELS:
        raise ValueError(
            f"failure_type_auto must be one of {FAILURE_LABELS}, got {record['failure_type_auto']!r}"
        )
    if not isinstance(record["success"], bool):
        raise ValueError("success must be a bool")
    for bool_field in ("wrong_object", "forbidden_object_touched"):
        if not isinstance(record[bool_field], bool):
            raise ValueError(f"{bool_field} must be a bool")
    for tri_bool_field in ("final_relation_success", "conditional_execution_success"):
        value = record[tri_bool_field]
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"{tri_bool_field} must be a bool or null")
