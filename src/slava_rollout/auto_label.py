"""Auto-labeling logic for rollout_annotations.jsonl, per task.md
"Auto-labeling для первых прогонов" / "Failure labels" (rules copied verbatim
below in comments — do not invent new labels or rules, see
.claude/skills/slava-model-rollouts/SKILL.md).
"""
from __future__ import annotations

from typing import Any, Optional


def _resolve_relation_success(
    final_object_poses: dict[str, list[float]],
    success_predicates: list[dict[str, Any]],
    env_success: bool,
) -> Optional[bool]:
    """final_relation_success.

    Our 20 frames each carry exactly one success_predicate, and for LIBERO it
    is literally the BDDL goal state libero's own env.check_success() already
    evaluates; for SimplerEnv it is literally what env.evaluate()/info["success"]
    checks. So in this pilot final_relation_success == env_success — see
    SKILL.md "Native success" section for why this collapses instead of being
    computed independently from raw poses.
    """
    if not success_predicates:
        return None
    return env_success


def label_episode(
    *,
    env_success: bool,
    first_contact_object: Optional[str],
    touched_objects: list[str],
    target_object: Optional[str],
    reference_object: Optional[str],
    forbidden_objects: list[str],
    relation: Optional[str],
    action: Optional[str],
    final_object_poses: dict[str, list[float]],
    success_predicates: list[dict[str, Any]],
    step_count: int,
    max_steps: int,
) -> dict[str, Any]:
    """Compute the auto-labeled fields of one rollout_annotations.jsonl row.

    failure_type_auto rules (task.md "Failure labels", verbatim):
      target_grounding_error: робот первым тронул не target.
      reference_grounding_error: target выбран правильно, но relation строится
        относительно неправильного reference.
      relation_binding_error: target и reference правильные, но
        left/right/on/in/near выполнено неверно.
      negation_error: робот тронул forbidden object.
      physical_execution_error: target выбран правильно, intent правильный, но
        физически не получилось.
      no_action_or_timeout: нет осмысленного действия.
      unclear: невозможно уверенно определить.
    """
    success = bool(env_success)
    final_relation_success = _resolve_relation_success(
        final_object_poses, success_predicates, env_success
    )

    wrong_object = bool(
        first_contact_object is not None
        and target_object is not None
        and first_contact_object != target_object
    )
    forbidden_object_touched = bool(set(touched_objects) & set(forbidden_objects))

    # conditional_execution_success: task.md defines this as separating
    # grounding failure from physical failure — meaningful only once grounding
    # (target+reference) was correct; null otherwise, matching the schema
    # example in task.md where a wrong-object episode has this field null.
    conditional_execution_success: Optional[bool] = None
    if not wrong_object and first_contact_object is not None:
        conditional_execution_success = success

    if success:
        failure_type_auto = "success"
    elif step_count <= 1 or first_contact_object is None:
        failure_type_auto = "no_action_or_timeout" if step_count >= max_steps else "unclear"
    elif forbidden_object_touched:
        failure_type_auto = "negation_error"
    elif wrong_object:
        failure_type_auto = "target_grounding_error"
    elif relation is not None and reference_object is not None and not success:
        # target contact was correct; relation unmet. task.md distinguishes
        # reference_grounding_error (wrong reference) from relation_binding_error
        # (right target+reference, wrong spatial relation) — telling these apart
        # from contacts alone needs to know *which* object the arm ended up
        # relating the target to, which our first-contact signal alone can't
        # give for multi-touch episodes. Default to relation_binding_error
        # (target+reference both grounded correctly, per contact evidence) and
        # flag for the mandatory first-100 manual audit rather than guess.
        failure_type_auto = "relation_binding_error"
    elif not success:
        failure_type_auto = "physical_execution_error"
    else:
        failure_type_auto = "unclear"

    return {
        "success": success,
        "first_contact_object": first_contact_object,
        "wrong_object": wrong_object,
        "forbidden_object_touched": forbidden_object_touched,
        "final_relation_success": final_relation_success,
        "conditional_execution_success": conditional_execution_success,
        "failure_type_auto": failure_type_auto,
    }
