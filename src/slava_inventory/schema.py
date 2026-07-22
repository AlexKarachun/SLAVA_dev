from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "1.0"

RECORD_FIELDS = {
    "task_uid",
    "suite",
    "task_id",
    "canonical_en",
    "source",
    "images",
    "objects_raw",
    "success_predicates",
    "candidate_slots",
    "usable_for_slava",
    "notes",
}
LIBERO_SOURCE_FIELDS = {
    "environment",
    "commit",
    "task_name",
    "bddl_file",
    "init_state_id",
}
SIMPLER_SOURCE_FIELDS = {
    "environment",
    "commit",
    "task_name",
    "gym_env_name",
    "episode_id",
    "reset_seed",
}
IMAGE_FIELDS = {"agentview_rgb", "wrist_rgb"}
OBJECT_FIELDS = {
    "sim_handle",
    "raw_name",
    "pose_xyz",
    "visible_agentview",
    "visible_wrist",
}
SLOT_FIELDS = {"action", "target", "reference", "relation", "forbidden_candidates"}
VISIBILITY_VALUES = {None, True, False, "visible_partial"}


def _exact_fields(value: dict[str, Any], expected: set[str], path: str) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"missing {sorted(missing)}")
        if extra:
            parts.append(f"unexpected {sorted(extra)}")
        raise ValueError(f"{path}: {'; '.join(parts)}")


def _required_string(value: Any, path: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: expected a non-empty string")


def _portable_path(value: Any, path: str, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    _required_string(value, path)
    if Path(value).is_absolute() or str(value).startswith("/workspace/"):
        raise ValueError(f"{path}: expected a portable relative path, got {value!r}")


def _legacy_integer(value: Any, path: str) -> int:
    """Accept integer-valued legacy floats introduced by pandas JSON export."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path}: expected an integer, got {value!r}")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{path}: expected an integer, got {value!r}")
    return int(value)


def validate_inventory_record(record: dict[str, Any]) -> None:
    """Validate one canonical inventory v1 record, rejecting every extra field."""
    if not isinstance(record, dict):
        raise ValueError("record: expected an object")
    _exact_fields(record, RECORD_FIELDS, "record")
    _required_string(record["task_uid"], "task_uid")
    _required_string(record["suite"], "suite")
    if not isinstance(record["task_id"], int) or isinstance(record["task_id"], bool):
        raise ValueError("task_id: expected an integer")
    _required_string(record["canonical_en"], "canonical_en")

    source = record["source"]
    if not isinstance(source, dict):
        raise ValueError("source: expected an object")
    environment = source.get("environment")
    if environment == "LIBERO":
        _exact_fields(source, LIBERO_SOURCE_FIELDS, "source")
        if not isinstance(source["init_state_id"], int):
            raise ValueError("source.init_state_id: expected an integer")
        _portable_path(source["bddl_file"], "source.bddl_file")
    elif environment == "SimplerEnv":
        _exact_fields(source, SIMPLER_SOURCE_FIELDS, "source")
        if not isinstance(source["episode_id"], int):
            raise ValueError("source.episode_id: expected an integer")
        if not isinstance(source["reset_seed"], int):
            raise ValueError("source.reset_seed: expected an integer")
    else:
        raise ValueError("source.environment: expected 'LIBERO' or 'SimplerEnv'")
    _required_string(source["commit"], "source.commit")
    _required_string(source["task_name"], "source.task_name")

    images = record["images"]
    if not isinstance(images, dict):
        raise ValueError("images: expected an object")
    _exact_fields(images, IMAGE_FIELDS, "images")
    _portable_path(images["agentview_rgb"], "images.agentview_rgb")
    _portable_path(images["wrist_rgb"], "images.wrist_rgb", nullable=True)
    if environment == "SimplerEnv" and images["wrist_rgb"] is not None:
        raise ValueError("images.wrist_rgb: SimplerEnv WidowX must have null wrist_rgb")

    objects = record["objects_raw"]
    if not isinstance(objects, list):
        raise ValueError("objects_raw: expected an array")
    handles: set[str] = set()
    for index, obj in enumerate(objects):
        path = f"objects_raw[{index}]"
        if not isinstance(obj, dict):
            raise ValueError(f"{path}: expected an object")
        _exact_fields(obj, OBJECT_FIELDS, path)
        _required_string(obj["sim_handle"], f"{path}.sim_handle")
        _required_string(obj["raw_name"], f"{path}.raw_name")
        if obj["sim_handle"] in handles:
            raise ValueError(f"{path}.sim_handle: duplicate {obj['sim_handle']!r}")
        handles.add(obj["sim_handle"])
        pose = obj["pose_xyz"]
        if not isinstance(pose, list) or len(pose) != 3 or not all(
            isinstance(number, (int, float)) and not isinstance(number, bool) for number in pose
        ):
            raise ValueError(f"{path}.pose_xyz: expected three numbers")
        for camera in ("visible_agentview", "visible_wrist"):
            if obj[camera] not in VISIBILITY_VALUES:
                raise ValueError(f"{path}.{camera}: invalid visibility value {obj[camera]!r}")
        if environment == "SimplerEnv" and obj["visible_wrist"] is not None:
            raise ValueError(f"{path}.visible_wrist: SimplerEnv WidowX must be null")

    if not isinstance(record["success_predicates"], list):
        raise ValueError("success_predicates: expected an array")
    slots = record["candidate_slots"]
    if not isinstance(slots, dict):
        raise ValueError("candidate_slots: expected an object")
    _exact_fields(slots, SLOT_FIELDS, "candidate_slots")
    for key in ("action", "target", "reference", "relation"):
        if slots[key] is not None and not isinstance(slots[key], str):
            raise ValueError(f"candidate_slots.{key}: expected string or null")
    if not isinstance(slots["forbidden_candidates"], list) or not all(
        isinstance(value, str) for value in slots["forbidden_candidates"]
    ):
        raise ValueError("candidate_slots.forbidden_candidates: expected an array of strings")
    if record["usable_for_slava"] not in (None, True, False):
        raise ValueError("usable_for_slava: expected true, false, or null")
    if not isinstance(record["notes"], str):
        raise ValueError("notes: expected a string")


def validate_inventory(records: Iterable[dict[str, Any]]) -> None:
    seen: set[str] = set()
    for index, record in enumerate(records, 1):
        try:
            validate_inventory_record(record)
        except ValueError as exc:
            raise ValueError(f"record {index}: {exc}") from exc
        uid = record["task_uid"]
        if uid in seen:
            raise ValueError(f"record {index}: duplicate task_uid {uid!r}")
        seen.add(uid)


def normalize_inventory_record(record: dict[str, Any]) -> dict[str, Any]:
    """Convert either the legacy collector shape or canonical v1 into canonical v1."""
    legacy_source = record.get("source") or {}
    environment = legacy_source.get("environment")
    if environment == "LIBERO":
        source = {
            "environment": "LIBERO",
            "commit": legacy_source.get("commit"),
            "task_name": legacy_source.get("task_name") or record.get("task_name"),
            "bddl_file": legacy_source.get("bddl_file") or record.get("bddl_file"),
            "init_state_id": _legacy_integer(
                legacy_source.get("init_state_id")
                if legacy_source.get("init_state_id") is not None
                else record.get("init_state_id"),
                "source.init_state_id",
            ),
        }
    elif environment == "SimplerEnv":
        source = {
            "environment": "SimplerEnv",
            "commit": legacy_source.get("commit"),
            "task_name": legacy_source.get("task_name") or record.get("task_name"),
            "gym_env_name": legacy_source.get("gym_env_name") or record.get("gym_env_name"),
            "episode_id": _legacy_integer(
                legacy_source.get("episode_id")
                if legacy_source.get("episode_id") is not None
                else record.get("episode_id"),
                "source.episode_id",
            ),
            "reset_seed": _legacy_integer(
                legacy_source.get("reset_seed")
                if legacy_source.get("reset_seed") is not None
                else record.get("reset_seed"),
                "source.reset_seed",
            ),
        }
    else:
        raise ValueError(f"Cannot normalize unknown source environment {environment!r}")

    images = record.get("images") or {}
    objects = []
    for obj in record.get("objects_raw") or []:
        objects.append(
            {
                "sim_handle": obj.get("sim_handle"),
                "raw_name": obj.get("raw_name") or obj.get("sim_handle"),
                "pose_xyz": obj.get("pose_xyz"),
                "visible_agentview": obj.get("visible_agentview"),
                "visible_wrist": None if environment == "SimplerEnv" else obj.get("visible_wrist"),
            }
        )
    slots = record.get("candidate_slots") or {}
    normalized = {
        "task_uid": record.get("task_uid"),
        "suite": record.get("suite"),
        "task_id": _legacy_integer(record.get("task_id"), "task_id"),
        "canonical_en": record.get("canonical_en"),
        "source": source,
        "images": {
            "agentview_rgb": images.get("agentview_rgb"),
            "wrist_rgb": None if environment == "SimplerEnv" else images.get("wrist_rgb"),
        },
        "objects_raw": objects,
        "success_predicates": record.get("success_predicates") or [],
        "candidate_slots": {
            "action": slots.get("action"),
            "target": slots.get("target"),
            "reference": slots.get("reference"),
            "relation": slots.get("relation"),
            "forbidden_candidates": slots.get("forbidden_candidates") or [],
        },
        "usable_for_slava": record.get("usable_for_slava"),
        "notes": record.get("notes") or "",
    }
    validate_inventory_record(normalized)
    return normalized
