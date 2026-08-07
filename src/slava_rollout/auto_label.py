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


def _is_on(top: Optional[list[float]], bottom: Optional[list[float]]) -> Optional[bool]:
    """Грубая проверка «A стоит на B» по финальным позам.

    Нужна там, где предикат среды отвечает на другой вопрос (см.
    `_swapped_success`). Пороги сознательно широкие: 6 см по горизонтали и
    1-12 см по высоте покрывают и кубик 3 см на кубике, и тарелку на миске, а
    промахи мимо цели в наших сценах измеряются десятками сантиметров.
    Возвращает None, если поз нет — «не знаю» не то же самое, что «нет».
    """
    if not top or not bottom or len(top) < 3 or len(bottom) < 3:
        return None
    dx, dy = abs(top[0] - bottom[0]), abs(top[1] - bottom[1])
    dz = top[2] - bottom[2]
    return dx <= 0.06 and dy <= 0.06 and 0.01 <= dz <= 0.12


def _swapped_success(
    variant: Optional[str],
    relation: Optional[str],
    target_object: Optional[str],
    reference_object: Optional[str],
    final_object_poses: dict[str, list[float]],
) -> Optional[bool]:
    """Успех для `ru_case_swap` — выполнил ли робот ПЕРЕВЁРНУТУЮ инструкцию.

    Предикат среды в этом варианте намеренно не меняется (иначе получилась бы
    другая задача с другой физикой, и провал нельзя было бы отличить от «стало
    объективно труднее»). Но тогда `env_success` отвечает на вопрос «сделал ли
    робот ИСХОДНОЕ задание», то есть высокий SR означал «модель не заметила
    перестановку ролей» — величина, которую невозможно читать как обычный SR.
    Решение пользователя 07.08.2026: считать успехом то, о чём просила
    перевёрнутая инструкция, то есть отношение между теми же объектами в
    обратную сторону.

    Возвращает None, если вариант не тот, отношение не `on` или поз не хватает —
    вызывающий код тогда остаётся на `env_success`.
    """
    if variant != "ru_case_swap" or relation != "on":
        return None
    if not target_object or not reference_object:
        return None
    # Перевёрнутая инструкция просит поставить исходный reference на исходный target.
    return _is_on(final_object_poses.get(reference_object), final_object_poses.get(target_object))


def label_episode(
    *,
    env_success: bool,
    first_contact_object: Optional[str],
    touched_objects: list[str],
    target_object: Optional[str],
    reference_object: Optional[str],
    forbidden_objects: list[str],
    relation: Optional[str],
    variant: Optional[str] = None,
    action: Optional[str],
    final_object_poses: dict[str, list[float]],
    success_predicates: list[dict[str, Any]],
    step_count: int,
    ran_to_completion: bool = True,
    max_steps: Optional[int] = None,
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

    `ran_to_completion` — did the episode get its full allotted horizon (the
    environment declared `done`, or the orchestrator's outer cap was reached)?
    False only when an episode was cut short for an unrelated reason (crash,
    HTTP error, orchestrator kill), where "the model failed to act" is not a
    claim the data supports.

    `max_steps` is accepted but no longer used for labeling, and is kept only
    so old call sites don't break. It USED to gate the timeout branch as
    `step_count >= max_steps`, which was an environment-dependent bug:
    schema.MAX_EPISODE_STEPS is our OUTER safety cap, not the environment's
    real horizon. SimplerEnv's gymnasium TimeLimit fires at its registered
    per-task horizon (e.g. 60 for StackGreenCubeOnYellowCube) while our cap is
    120, so the condition was unreachable there and every no-contact episode
    fell through to `unclear`. The dataset showed the artifact cleanly:
    SimplerEnv had 0 `no_action_or_timeout` and 115 `unclear`, LIBERO had 199
    and 0 — a perfect split by environment, i.e. a property of this function
    rather than of the models. Termination is now expressed directly by
    `ran_to_completion` instead of being inferred from a step budget.
    """
    swapped = _swapped_success(
        variant, relation, target_object, reference_object, final_object_poses
    )
    success_source = "env"
    if swapped is None:
        success = bool(env_success)
    else:
        success = bool(swapped)
        success_source = "swapped_predicate"
    final_relation_success = _resolve_relation_success(
        final_object_poses, success_predicates, env_success
    )

    wrong_object = bool(
        first_contact_object is not None
        and target_object is not None
        and first_contact_object != target_object
    )
    # `forbidden_objects` приходит из слотов фрейма и заполнен у ВСЕХ вариантов
    # сцены, а не только у `ru_negation` — это удобный сырой сигнал «тронул ли
    # робот тот объект, который в негации назван неправильным». Но метка
    # negation_error по task.md означает нарушение запрета, а запрет существует
    # только там, где инструкция его произносит, то есть в `ru_negation`.
    # До 07.08.2026 метка ставилась по любому варианту: из 21 negation_error в
    # пилоте лишь 4 приходились на `ru_negation`, остальные 17 — на
    # en_canonical/mt_russian/ru_literal/code_switch, где никакого запрета в
    # инструкции не было. Найдено пользователем при ручной валидации.
    touched_forbidden = bool(set(touched_objects) & set(forbidden_objects))
    negation_axis = variant is None or variant == "ru_negation"
    forbidden_object_touched = touched_forbidden

    # conditional_execution_success: task.md defines this as separating
    # grounding failure from physical failure — meaningful only once grounding
    # (target+reference) was correct; null otherwise, matching the schema
    # example in task.md where a wrong-object episode has this field null.
    conditional_execution_success: Optional[bool] = None
    if not wrong_object and first_contact_object is not None:
        conditional_execution_success = success

    if success:
        failure_type_auto = "success"
    elif step_count <= 1:
        # Degenerate: the episode produced essentially no trajectory at all.
        failure_type_auto = "unclear"
    elif first_contact_object is None:
        # Never touched any task object. If the policy got its whole horizon,
        # that is task.md's "нет осмысленного действия"; if the episode was cut
        # short by an error, we cannot attribute anything and say so.
        failure_type_auto = "no_action_or_timeout" if ran_to_completion else "unclear"
    elif touched_forbidden and negation_axis:
        # Только на оси отрицания (см. negation_axis выше).
        # NOTE (precedence is a real judgement call, not an oversight): this
        # sits above target_grounding_error, and `forbidden_object_touched`
        # uses "touched at any point" while `wrong_object` uses "first
        # contact". So an episode that correctly grasps the target and only
        # later brushes the negated object still lands here. That matches
        # task.md's own wording ("робот тронул forbidden object", no ordering
        # qualifier) and keeps the negation axis conservative — but it does
        # mean negation_error counts are an upper bound. Both raw signals stay
        # in the row (`first_contact_object`, `forbidden_object_touched`), so a
        # stricter rule can be recomputed without re-running anything. Revisit
        # during the mandatory first-100 manual audit.
        failure_type_auto = "negation_error"
    elif wrong_object:
        failure_type_auto = "target_grounding_error"
    elif relation is not None and reference_object is not None:
        # target contact was correct; relation unmet. task.md distinguishes
        # reference_grounding_error (wrong reference) from relation_binding_error
        # (right target+reference, wrong spatial relation) — telling these apart
        # from contacts alone needs to know *which* object the arm ended up
        # relating the target to, which our first-contact signal alone can't
        # give for multi-touch episodes. Default to relation_binding_error
        # (target+reference both grounded correctly, per contact evidence) and
        # flag for the mandatory first-100 manual audit rather than guess.
        failure_type_auto = "relation_binding_error"
    else:
        # Right target, no relation to get wrong (open/turn_on-style tasks).
        failure_type_auto = "physical_execution_error"

    return {
        "success": success,
        "success_source": success_source,
        "first_contact_object": first_contact_object,
        "wrong_object": wrong_object,
        "forbidden_object_touched": forbidden_object_touched,
        "final_relation_success": final_relation_success,
        "conditional_execution_success": conditional_execution_success,
        "failure_type_auto": failure_type_auto,
    }
