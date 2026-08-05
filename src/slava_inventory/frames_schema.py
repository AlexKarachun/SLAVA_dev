"""Validation for the SLAVA v0.2 grounded semantic frame schema (data/pilot_v0_release/frames_v0.jsonl).

One record = one selected task + init state (matches the row it was built
from in selected_tasks_v0.jsonl), enriched with grounded target/reference/
relation/forbidden slots and Tier-1 instruction variants. Mirrors the literal
top-level field list from "Схема фрейма v0.2" in task.md (task_uid, suite,
task_id, init_state_id, frame_version, canonical_en, bddl_file, images,
scene, slots, variants, axis_na, validation, token_len) flatly rather than
nesting environment metadata under a "source" object, per an explicit call
to follow the template literally. LIBERO/SimplerEnv both need a few fields
beyond that minimal list to stay reproducible (task.md's own list is a
"обязательные поля" floor, not an exclusive one) -- see LIBERO_ONLY_FIELDS /
SIMPLER_ONLY_FIELDS below, always present but null for the other environment.
"""

from __future__ import annotations

from typing import Any, Iterable

from .schema import (
    VISIBILITY_VALUES,
    _exact_fields,
    _portable_path,
    _required_string,
)

FRAME_VERSION = "0.2"

# Fields listed verbatim in task.md's "Схема фрейма v0.2" template.
TEMPLATE_FRAME_FIELDS = {
    "task_uid",
    "suite",
    "task_id",
    "init_state_id",
    "frame_version",
    "canonical_en",
    "bddl_file",
    "images",
    "scene",
    "slots",
    "variants",
    "axis_na",
    "validation",
    "token_len",
}
# Reproducibility metadata task.md's minimal template doesn't spell out but
# AGENTS.md requires ("Portable manifest хранит repository-relative paths и
# pinned commits"). LIBERO's share (bddl_file/init_state_id) is already in
# the template; SimplerEnv needs these extra fields, null for LIBERO rows.
SIMPLER_ONLY_FIELDS = {"episode_id", "reset_seed", "gym_env_name"}
COMMON_PROVENANCE_FIELDS = {"environment", "commit", "task_name"}
# Sits next to `variants` (task.md: "Храним также систему перевода:
# mt_metadata: {system, date}"), null until mt_russian is actually filled by
# a real MT pass.
MT_METADATA_FIELD = {"mt_metadata"}
# task.md's QA item 14 ("Есть token_len для нужных токенизаторов") doesn't
# spell out a shape or a tokenizer list -- decided with the user: the four
# tokenizers below (one per backbone family in task.md's "Модели и среды"
# table; entries sharing a tokenizer -- GreenVLA/Qwen3-VL, Prismatic/
# OpenVLA-OFT, PaliGemma/pi0/pi0.5 -- collapse to one key each), real-text
# token counts (tokenizer(text)['input_ids'], default special tokens), keyed
# tokenizer -> variant -> int. token_len_metadata (mirrors mt_metadata's
# pattern) records which checkpoint each key was measured with, for
# reproducibility -- see scripts/compute_token_len.py.
TOKEN_LEN_TOKENIZERS = {"qwen3_vl", "openvla_oft", "paligemma", "smolvla"}
TOKEN_LEN_CHECKPOINTS = {
    "qwen3_vl": "Qwen/Qwen3-VL-4B-Instruct",
    "openvla_oft": "moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10",
    "paligemma": "google/paligemma-3b-pt-224",
    "smolvla": "HuggingFaceTB/SmolVLM2-500M-Video-Instruct",
}
TOKEN_LEN_METADATA_FIELD = {"token_len_metadata"}
FRAME_FIELDS = (
    TEMPLATE_FRAME_FIELDS
    | SIMPLER_ONLY_FIELDS
    | COMMON_PROVENANCE_FIELDS
    | MT_METADATA_FIELD
    | TOKEN_LEN_METADATA_FIELD
)
IMAGE_FIELDS = {
    "agentview_rgb",
    "wrist_rgb",
    "agentview_segmentation",
    "wrist_segmentation",
    "depth",
}
SCENE_OBJECT_FIELDS = {
    "id",
    "sim_handle",
    "raw_name",
    "category_en",
    "category_ru",
    "color_en",
    "color_ru",
    "pose_xyz_initial",
    "visible_agentview",
    "visible_wrist",
    "bbox2d_agentview",
    "mask_id_agentview",
    "role",
}
ROLE_VALUES = {"target", "reference", "distractor", "background"}
SLOT_FIELDS = {"action", "target", "reference", "relation", "forbidden", "success_predicates"}
ACTION_VALUES = {"pick_place", "open", "turn_on", "push", "stack"}
RELATION_VALUES = {"on", "in", "in_front_of", "left_of", "right_of", "next_to", None}
# success_predicates entries, per task.md's "type: spatial_relation, relation,
# arg1, arg2" example -- extended with a "state" type for single-object
# state-change tasks (open/turn_on) the example doesn't cover.
PREDICATE_FIELDS_BY_TYPE = {
    "spatial_relation": {"type", "relation", "arg1", "arg2"},
    "state": {"type", "predicate", "arg1"},
}
PREDICATE_TYPES = set(PREDICATE_FIELDS_BY_TYPE)
STATE_PREDICATE_VALUES = {"open", "turned_on"}
VARIANT_FIELDS = {
    "en_canonical",
    "en_paraphrase",
    "mt_russian",
    "ru_literal",
    "ru_free_order",
    "ru_case_swap",
    "ru_negation",
    "code_switch",
    "ru_translit",
    "ru_colloquial",
    "ru_anaphora",
}
AXIS_NA_KEYS = VARIANT_FIELDS - {"en_canonical"}
MT_METADATA_FIELDS = {"system", "date"}
VALIDATION_FIELDS = {"author", "native_check", "naturalness", "equivalence", "ambiguity", "notes"}
NATIVE_CHECK_VALUES = {"pending", "passed", "failed"}


def _string_or_null(value: Any, path: str) -> None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{path}: expected string or null")


def validate_frame_record(record: dict[str, Any]) -> None:
    if not isinstance(record, dict):
        raise ValueError("record: expected an object")
    _exact_fields(record, FRAME_FIELDS, "record")
    _required_string(record["task_uid"], "task_uid")
    _required_string(record["suite"], "suite")
    if not isinstance(record["task_id"], int) or isinstance(record["task_id"], bool):
        raise ValueError("task_id: expected an integer")
    if record["frame_version"] != FRAME_VERSION:
        raise ValueError(f"frame_version: expected {FRAME_VERSION!r}")
    _required_string(record["canonical_en"], "canonical_en")

    environment = record["environment"]
    if environment not in ("LIBERO", "SimplerEnv"):
        raise ValueError("environment: expected 'LIBERO' or 'SimplerEnv'")
    _required_string(record["commit"], "commit")
    _required_string(record["task_name"], "task_name")
    if environment == "LIBERO":
        if not isinstance(record["init_state_id"], int) or isinstance(record["init_state_id"], bool):
            raise ValueError("init_state_id: expected an integer for LIBERO")
        _portable_path(record["bddl_file"], "bddl_file")
        for field in SIMPLER_ONLY_FIELDS:
            if record[field] is not None:
                raise ValueError(f"{field}: must be null for LIBERO")
    else:
        if record["init_state_id"] is not None:
            raise ValueError("init_state_id: must be null for SimplerEnv")
        if record["bddl_file"] is not None:
            raise ValueError("bddl_file: must be null for SimplerEnv")
        if not isinstance(record["episode_id"], int) or isinstance(record["episode_id"], bool):
            raise ValueError("episode_id: expected an integer for SimplerEnv")
        if not isinstance(record["reset_seed"], int) or isinstance(record["reset_seed"], bool):
            raise ValueError("reset_seed: expected an integer for SimplerEnv")
        _required_string(record["gym_env_name"], "gym_env_name")

    images = record["images"]
    if not isinstance(images, dict):
        raise ValueError("images: expected an object")
    _exact_fields(images, IMAGE_FIELDS, "images")
    _portable_path(images["agentview_rgb"], "images.agentview_rgb")
    _portable_path(images["wrist_rgb"], "images.wrist_rgb", nullable=True)
    for field in ("agentview_segmentation", "wrist_segmentation", "depth"):
        _portable_path(images[field], f"images.{field}", nullable=True)

    scene = record["scene"]
    if not isinstance(scene, dict) or set(scene) != {"objects"}:
        raise ValueError("scene: expected an object with only 'objects'")
    objects = scene["objects"]
    if not isinstance(objects, list) or not objects:
        raise ValueError("scene.objects: expected a non-empty array")
    ids: set[str] = set()
    for index, obj in enumerate(objects):
        path = f"scene.objects[{index}]"
        if not isinstance(obj, dict):
            raise ValueError(f"{path}: expected an object")
        _exact_fields(obj, SCENE_OBJECT_FIELDS, path)
        _required_string(obj["id"], f"{path}.id")
        if obj["id"] in ids:
            raise ValueError(f"{path}.id: duplicate {obj['id']!r}")
        ids.add(obj["id"])
        _required_string(obj["sim_handle"], f"{path}.sim_handle")
        _required_string(obj["raw_name"], f"{path}.raw_name")
        for field in (
            "category_en",
            "category_ru",
            "color_en",
            "color_ru",
        ):
            _required_string(obj[field], f"{path}.{field}")
        pose = obj["pose_xyz_initial"]
        if not isinstance(pose, list) or len(pose) != 3 or not all(
            isinstance(n, (int, float)) and not isinstance(n, bool) for n in pose
        ):
            raise ValueError(f"{path}.pose_xyz_initial: expected three numbers")
        for camera in ("visible_agentview", "visible_wrist"):
            if obj[camera] not in VISIBILITY_VALUES:
                raise ValueError(f"{path}.{camera}: invalid visibility value {obj[camera]!r}")
        for field in ("bbox2d_agentview", "mask_id_agentview"):
            if obj[field] is not None:
                raise ValueError(f"{path}.{field}: must be null in v0")
        if obj["role"] not in ROLE_VALUES:
            raise ValueError(f"{path}.role: invalid role {obj['role']!r}")

    slots = record["slots"]
    if not isinstance(slots, dict):
        raise ValueError("slots: expected an object")
    _exact_fields(slots, SLOT_FIELDS, "slots")
    if slots["action"] not in ACTION_VALUES:
        raise ValueError(f"slots.action: expected one of {sorted(ACTION_VALUES)}")
    if slots["target"] not in ids:
        raise ValueError("slots.target: must reference an id in scene.objects")
    relation = slots["relation"]
    if relation not in RELATION_VALUES:
        raise ValueError(f"slots.relation: expected one of {sorted(v for v in RELATION_VALUES if v)} or null")
    reference = slots["reference"]
    if relation is not None:
        if reference not in ids:
            raise ValueError("slots.reference: must reference an id in scene.objects when relation is set")
    elif reference is not None and reference not in ids:
        raise ValueError("slots.reference: must reference an id in scene.objects or be null")
    forbidden = slots["forbidden"]
    if not isinstance(forbidden, list) or not all(isinstance(v, str) for v in forbidden):
        raise ValueError("slots.forbidden: expected an array of strings")
    for value in forbidden:
        if value not in ids:
            raise ValueError(f"slots.forbidden: {value!r} not in scene.objects")
    if slots["target"] in forbidden:
        raise ValueError("slots.forbidden: target must not be in forbidden")
    if reference is not None and reference in forbidden:
        # Found 2026-08-05: widowx_stack_cube (D4) had forbidden==[reference],
        # so touching the placement surface — required by the task itself —
        # was auto-labeled negation_error on every legitimate success. This
        # check is the symmetric twin of the target check above, which
        # existed but didn't cover reference — the actual gap that let the
        # bad frame through `validate_frames()` unnoticed in the first place.
        raise ValueError("slots.forbidden: reference must not be in forbidden")
    predicates = slots["success_predicates"]
    if not isinstance(predicates, list) or not predicates:
        raise ValueError("slots.success_predicates: expected a non-empty array")
    for index, predicate in enumerate(predicates):
        path = f"slots.success_predicates[{index}]"
        if not isinstance(predicate, dict) or predicate.get("type") not in PREDICATE_TYPES:
            raise ValueError(f"{path}: expected an object with type in {sorted(PREDICATE_TYPES)}")
        _exact_fields(predicate, PREDICATE_FIELDS_BY_TYPE[predicate["type"]], path)
        if predicate["type"] == "spatial_relation":
            if predicate["relation"] not in RELATION_VALUES - {None}:
                raise ValueError(f"{path}.relation: invalid relation {predicate['relation']!r}")
            for arg in ("arg1", "arg2"):
                if predicate[arg] not in ids:
                    raise ValueError(f"{path}.{arg}: must reference an id in scene.objects")
        else:  # state
            if predicate["predicate"] not in STATE_PREDICATE_VALUES:
                raise ValueError(f"{path}.predicate: expected one of {sorted(STATE_PREDICATE_VALUES)}")
            if predicate["arg1"] not in ids:
                raise ValueError(f"{path}.arg1: must reference an id in scene.objects")

    variants = record["variants"]
    if not isinstance(variants, dict):
        raise ValueError("variants: expected an object")
    _exact_fields(variants, VARIANT_FIELDS, "variants")
    for field in VARIANT_FIELDS:
        _string_or_null(variants[field], f"variants.{field}")
    _required_string(variants["en_canonical"], "variants.en_canonical")

    mt_metadata = record["mt_metadata"]
    if mt_metadata is None:
        if variants["mt_russian"] is not None:
            raise ValueError("mt_metadata: required once variants.mt_russian is filled")
    else:
        if variants["mt_russian"] is None:
            raise ValueError("mt_metadata: must be null while variants.mt_russian is null")
        if not isinstance(mt_metadata, dict):
            raise ValueError("mt_metadata: expected an object or null")
        _exact_fields(mt_metadata, MT_METADATA_FIELDS, "mt_metadata")
        _required_string(mt_metadata["system"], "mt_metadata.system")
        _required_string(mt_metadata["date"], "mt_metadata.date")

    axis_na = record["axis_na"]
    if not isinstance(axis_na, dict):
        raise ValueError("axis_na: expected an object")
    for key, reason in axis_na.items():
        if key not in AXIS_NA_KEYS:
            raise ValueError(f"axis_na: unexpected key {key!r}")
        _required_string(reason, f"axis_na.{key}")
        if variants.get(key) is not None:
            raise ValueError(f"axis_na.{key}: variant is filled, axis_na is not applicable")
    # Relaxed 2026-08-05: this used to require forbidden non-empty whenever
    # ru_negation is filled, on the assumption that every negation implies
    # "don't touch a distractor". That's wrong for a target/reference
    # role-swap negation ("pick X, not Y" where Y *is* the reference — e.g.
    # widowx_stack_cube's "возьми не желтый, а зеленый... и поставь на
    # желтый": yellow is legitimately touched as the placement surface
    # either way, there's no third object to forbid). A wrong pick there is
    # correctly caught by auto_label.py's target_grounding_error (first
    # contact != target), not negation_error — forbidden isn't the only
    # mechanism task.md's taxonomy has for a negation failure. The check
    # still fires when the scene actually has a spare object that a
    # distractor-avoidance negation could have been wired to but wasn't
    # (the real authoring mistake this check exists to catch).
    other_objects = ids - {slots["target"]} - ({reference} if reference else set())
    if variants["ru_negation"] is not None and not forbidden and other_objects:
        raise ValueError("variants.ru_negation: filled but slots.forbidden is empty")
    if variants["ru_case_swap"] is None and "ru_case_swap" not in axis_na:
        raise ValueError("variants.ru_case_swap: must be filled or have an axis_na reason")
    if variants["ru_negation"] is None and "ru_negation" not in axis_na:
        raise ValueError("variants.ru_negation: must be filled or have an axis_na reason")

    validation = record["validation"]
    if not isinstance(validation, dict):
        raise ValueError("validation: expected an object")
    _exact_fields(validation, VALIDATION_FIELDS, "validation")
    _required_string(validation["author"], "validation.author")
    if validation["native_check"] not in NATIVE_CHECK_VALUES:
        raise ValueError(f"validation.native_check: expected one of {sorted(NATIVE_CHECK_VALUES)}")
    for field in ("naturalness", "equivalence", "ambiguity"):
        if not isinstance(validation[field], dict):
            raise ValueError(f"validation.{field}: expected an object")
    if not isinstance(validation["notes"], str):
        raise ValueError("validation.notes: expected a string")

    filled_variants = {key for key, value in variants.items() if value is not None}
    token_len = record["token_len"]
    token_len_metadata = record["token_len_metadata"]
    if not isinstance(token_len, dict):
        raise ValueError("token_len: expected an object")
    if not token_len:
        if token_len_metadata is not None:
            raise ValueError("token_len_metadata: must be null while token_len is empty")
    else:
        if set(token_len) != TOKEN_LEN_TOKENIZERS:
            raise ValueError(f"token_len: expected exactly keys {sorted(TOKEN_LEN_TOKENIZERS)}")
        for tokenizer_key, counts in token_len.items():
            if not isinstance(counts, dict) or set(counts) != filled_variants:
                raise ValueError(f"token_len.{tokenizer_key}: expected keys {sorted(filled_variants)}")
            for variant_key, count in counts.items():
                if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                    raise ValueError(f"token_len.{tokenizer_key}.{variant_key}: expected a non-negative integer")
        if not isinstance(token_len_metadata, dict) or set(token_len_metadata) != TOKEN_LEN_TOKENIZERS:
            raise ValueError(f"token_len_metadata: expected exactly keys {sorted(TOKEN_LEN_TOKENIZERS)}")
        for tokenizer_key, checkpoint in token_len_metadata.items():
            _required_string(checkpoint, f"token_len_metadata.{tokenizer_key}")


def validate_frames(records: Iterable[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for index, record in enumerate(records, 1):
        try:
            validate_frame_record(record)
        except ValueError as exc:
            raise ValueError(f"record {index}: {exc}") from exc
        uid = record["task_uid"]
        if uid in seen:
            raise ValueError(f"record {index}: duplicate task_uid {uid!r}")
        seen.add(uid)
