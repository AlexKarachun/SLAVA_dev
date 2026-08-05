#!/usr/bin/env python3
"""Build the v0.2 grounded semantic frame draft (data/pilot_v0_release/frames_v0.jsonl).

Reads the frozen 20-task manifest (data/selected_tasks_v0.jsonl) and the
object lexicon, attaches grounded target/reference/relation/forbidden slots
and Tier-1 instruction variants per hand-authored task-family template, and
writes one frame per scene. This is an LLM draft per the QA pipeline in
task.md ("LLM draft -> ручная доводка -> validate_frames.py -> native check
-> freeze") -- every record is emitted with validation.native_check="pending"
and is NOT meant to be frozen without human review.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_inventory.io_utils import LEXICON_COLUMNS, load_jsonl, save_jsonl  # noqa: E402
from slava_inventory.frames_schema import FRAME_VERSION, validate_frames  # noqa: E402

SELECTED_PATH = PROJECT_ROOT / "data" / "selected_tasks_v0.jsonl"
LEXICON_PATH = PROJECT_ROOT / "data" / "object_lexicon.csv"
OUTPUT_PATH = PROJECT_ROOT / "data" / "pilot_v0_release" / "frames_v0.jsonl"

AUTHOR = "claude-sonnet-5 (llm draft, pending human review + native check)"


def load_lexicon() -> dict[str, dict[str, str]]:
    with LEXICON_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == LEXICON_COLUMNS
        return {row["raw_name"]: row for row in reader}


# Per-task-family template. `roles` maps sim_handle -> role for every object
# in objects_raw (all objects must be covered, or explicitly None if replaced
# by `extra_objects`). `target_id`/`reference_id`/`forbidden_ids` use
# sim_handle as the scene-object id, which is always unique per scene.
TEMPLATES: dict[str, dict[str, Any]] = {
    "open_the_middle_drawer_of_the_cabinet": {
        "action": "open",
        "target_id": "wooden_cabinet_1_middle_region",
        "reference_id": None,
        "relation": None,
        "forbidden_ids": ["wooden_cabinet_1_top_region"],
        "extra_objects": [
            # Synthetic sub-objects: same physical cabinet, two addressable
            # drawers. ids match the BDDL region names for wooden_cabinet_1
            # (see data/libero_bddl/libero_goal/open_the_middle_drawer_of_the_cabinet.bddl
            # :regions top_region/middle_region/bottom_region, :goal Open
            # wooden_cabinet_1_middle_region) so they trace back to the
            # original task semantics instead of an invented naming scheme.
            # sim_handle stays wooden_cabinet_1 for both; only the id differs.
            {"id": "wooden_cabinet_1_middle_region", "sim_handle": "wooden_cabinet_1", "raw_name": "wooden_cabinet", "role": "target"},
            {"id": "wooden_cabinet_1_top_region", "sim_handle": "wooden_cabinet_1", "raw_name": "wooden_cabinet", "role": "distractor"},
            # bottom_region is a plausible wrong-drawer pick too (role=distractor),
            # but is not named in ru_negation's "не X, а Y" text, so it stays out
            # of slots.forbidden -- see AGENTS.md's task.md-contract section.
            {"id": "wooden_cabinet_1_bottom_region", "sim_handle": "wooden_cabinet_1", "raw_name": "wooden_cabinet", "role": "distractor"},
        ],
        "roles": {
            "wooden_cabinet_1": None,  # replaced by extra_objects above
            "akita_black_bowl_1": "background", "cream_cheese_1": "background",
            "wine_bottle_1": "background", "plate_1": "background",
            "flat_stove_1": "background", "wine_rack_1": "background",
        },
        "en_paraphrase": "pull open the cabinet's middle drawer",
        "ru_literal": "открой средний ящик шкафа",
        "ru_free_order": "у шкафа открой средний ящик",
        "ru_case_swap": None,
        "ru_case_swap_na": "нет объекта-reference: open — изменение состояния одного объекта (ящика), а не перестановка ролей между двумя предметами.",
        "ru_negation": "не верхний, а средний ящик шкафа открой",
        "code_switch": "открой middle drawer шкафа",
    },
    "push_the_plate_to_the_front_of_the_stove": {
        "action": "push",
        "target_id": "plate_1", "reference_id": "flat_stove_1", "relation": "in_front_of",
        "forbidden_ids": ["akita_black_bowl_1"],
        "roles": {
            "plate_1": "target", "flat_stove_1": "reference", "akita_black_bowl_1": "distractor",
            "cream_cheese_1": "background", "wine_bottle_1": "background",
            "wooden_cabinet_1": "background", "wine_rack_1": "background",
        },
        "en_paraphrase": "shove the plate to the front of the stove",
        "ru_literal": "подвинь тарелку к передней части плиты",
        "ru_free_order": "к передней части плиты подвинь тарелку",
        "ru_case_swap": None,
        "ru_case_swap_na": "плита — несъемный крупный прибор, не переносимый объект; обратная команда 'подвинь плиту к тарелке' физически невыполнима (асимметричная пара).",
        "ru_negation": "не миску, а тарелку подвинь к плите",
        "code_switch": "подвинь plate к передней части stove",
    },
    "put_the_wine_bottle_on_the_rack": {
        "action": "pick_place",
        "target_id": "wine_bottle_1", "reference_id": "wine_rack_1", "relation": "on",
        "forbidden_ids": ["akita_black_bowl_1"],
        "roles": {
            "wine_bottle_1": "target", "wine_rack_1": "reference", "akita_black_bowl_1": "distractor",
            "cream_cheese_1": "background", "plate_1": "background",
            "wooden_cabinet_1": "background", "flat_stove_1": "background",
        },
        "en_paraphrase": "place the wine bottle onto the rack",
        "ru_literal": "поставь бутылку вина на стойку",
        "ru_free_order": "на стойку поставь бутылку вина",
        "ru_case_swap": None,
        "ru_case_swap_na": "винная стойка — крупный несъемный предмет мебели, не может быть помещена на бутылку; пара асимметрична (аналогично 'предмет -> корзина' из AGENTS.md).",
        "ru_negation": "не миску, а бутылку вина поставь на стойку",
        "code_switch": "поставь wine bottle на rack",
    },
    "turn_on_the_stove": {
        "action": "turn_on",
        "target_id": "flat_stove_1", "reference_id": None, "relation": None,
        "forbidden_ids": [],
        "roles": {
            "flat_stove_1": "target", "akita_black_bowl_1": "background", "cream_cheese_1": "background",
            "wine_bottle_1": "background", "plate_1": "background", "wooden_cabinet_1": "background",
            "wine_rack_1": "background",
        },
        "en_paraphrase": "switch the stove on",
        "ru_literal": "включи плиту",
        "ru_free_order": "плиту включи",
        "ru_case_swap": None,
        "ru_case_swap_na": "нет reference-объекта: задача не подразумевает пару target/reference.",
        "ru_negation": None,
        "ru_negation_na": "нет правдоподобного альтернативного включаемого объекта в сцене (плита — единственный прибор с состоянием turn_on).",
        "code_switch": "включи the stove",
    },
    "pick_up_the_butter_and_place_it_in_the_basket": {
        "action": "pick_place",
        "target_id": "butter_1", "reference_id": "basket_1", "relation": "in",
        "forbidden_ids": ["chocolate_pudding_1"],
        "roles": {
            "butter_1": "target", "basket_1": "reference", "chocolate_pudding_1": "distractor",
            "tomato_sauce_1": "distractor", "orange_juice_1": "distractor",
            "bbq_sauce_1": "distractor", "ketchup_1": "distractor",
        },
        "en_paraphrase": "grab the butter and put it into the basket",
        "ru_literal": "положи масло в корзину",
        "ru_free_order": "в корзину положи масло",
        "ru_case_swap": None,
        "ru_case_swap_na": "корзина — контейнер, а не соразмерный предмет; обратная команда 'положи корзину в масло' физически бессмысленна.",
        "ru_negation": "не шоколадный пудинг, а масло положи в корзину",
        "code_switch": "положи butter в корзину",
    },
    "pick_up_the_cream_cheese_and_place_it_in_the_basket": {
        "action": "pick_place",
        "target_id": "cream_cheese_1", "reference_id": "basket_1", "relation": "in",
        "forbidden_ids": ["butter_1"],
        "roles": {
            "cream_cheese_1": "target", "basket_1": "reference", "butter_1": "distractor",
            "alphabet_soup_1": "distractor", "milk_1": "distractor",
            "tomato_sauce_1": "distractor", "orange_juice_1": "distractor",
        },
        "en_paraphrase": "grab the cream cheese and put it into the basket",
        "ru_literal": "положи сливочный сыр в корзину",
        "ru_free_order": "в корзину положи сливочный сыр",
        "ru_case_swap": None,
        "ru_case_swap_na": "корзина — контейнер, а не соразмерный предмет; обратная команда физически бессмысленна.",
        "ru_negation": "не масло, а сливочный сыр положи в корзину",
        "code_switch": "положи cream cheese в корзину",
    },
    "pick_up_the_milk_and_place_it_in_the_basket": {
        "action": "pick_place",
        "target_id": "milk_1", "reference_id": "basket_1", "relation": "in",
        "forbidden_ids": ["orange_juice_1"],
        "roles": {
            "milk_1": "target", "basket_1": "reference", "orange_juice_1": "distractor",
            "cream_cheese_1": "distractor", "tomato_sauce_1": "distractor",
            "butter_1": "distractor", "chocolate_pudding_1": "distractor",
        },
        "en_paraphrase": "grab the milk and put it into the basket",
        "ru_literal": "положи молоко в корзину",
        "ru_free_order": "в корзину положи молоко",
        "ru_case_swap": None,
        "ru_case_swap_na": "корзина — контейнер, а не соразмерный предмет; обратная команда физически бессмысленна.",
        "ru_negation": "не сок, а молоко положи в корзину",
        "code_switch": "положи milk в корзину",
    },
    "pick_up_the_tomato_sauce_and_place_it_in_the_basket": {
        "action": "pick_place",
        "target_id": "tomato_sauce_1", "reference_id": "basket_1", "relation": "in",
        "forbidden_ids": ["butter_1"],
        "roles": {
            "tomato_sauce_1": "target", "basket_1": "reference", "butter_1": "distractor",
            "milk_1": "distractor", "orange_juice_1": "distractor",
            "chocolate_pudding_1": "distractor", "bbq_sauce_1": "distractor",
        },
        "en_paraphrase": "grab the tomato sauce and put it into the basket",
        "ru_literal": "положи томатный соус в корзину",
        "ru_free_order": "в корзину положи томатный соус",
        "ru_case_swap": None,
        "ru_case_swap_na": "корзина — контейнер, а не соразмерный предмет; обратная команда физически бессмысленна.",
        "ru_negation": "не масло, а томатный соус положи в корзину",
        "code_switch": "положи tomato sauce в корзину",
    },
    "pick_up_the_black_bowl_from_table_center_and_place_it_on_the_plate": {
        "action": "pick_place",
        "target_id": "akita_black_bowl_1", "reference_id": "plate_1", "relation": "on",
        "forbidden_ids": ["akita_black_bowl_2"],
        "roles": {
            "akita_black_bowl_1": "target", "akita_black_bowl_2": "distractor",
            "plate_1": "reference", "cookies_1": "background",
            "glazed_rim_porcelain_ramekin_1": "background", "wooden_cabinet_1": "background",
            "flat_stove_1": "background",
        },
        "en_paraphrase": "grab the black bowl at the center of the table and set it on the plate",
        "ru_literal": "подними черную миску по центру стола и поставь ее на тарелку",
        "ru_free_order": "черную миску по центру стола подними и поставь на тарелку",
        "ru_case_swap": "поставь тарелку на черную миску",
        "ru_negation": "не ту миску, что рядом с формочкой, а ту, что по центру стола, подними и поставь на тарелку",
        "code_switch": "подними black bowl по центру стола и поставь на plate",
    },
    "widowx_stack_cube": {
        "action": "stack",
        "target_id": "baked_green_cube_3cm", "reference_id": "baked_yellow_cube_3cm", "relation": "on",
        # forbidden_ids intentionally empty (fixed 2026-08-05 — was
        # ["baked_yellow_cube_3cm"], i.e. the reference itself): this
        # 2-object scene has no distractor, and the task ("stack green on
        # yellow") requires legitimate contact with the reference object as
        # the placement surface. The previous value made every real success
        # auto-label as negation_error — see frames_schema.py's new
        # reference-not-in-forbidden validator check, which now catches this
        # class of authoring mistake before it reaches frames_v0.jsonl again.
        "forbidden_ids": [],
        "roles": {"baked_green_cube_3cm": "target", "baked_yellow_cube_3cm": "reference"},
        "en_paraphrase": "pick up the green block and place it on the yellow block",
        "ru_literal": "поставь зеленый кубик на желтый кубик",
        "ru_free_order": "на желтый кубик поставь зеленый кубик",
        "ru_case_swap": "поставь желтый кубик на зеленый кубик",
        "ru_negation": "не желтый, а зеленый кубик возьми и поставь на желтый",
        "code_switch": "поставь green cube на yellow cube",
    },
}
# akita_black_bowl needs per-instance roles for the two-bowl scene; handled
# via raw_name+index below since raw_name alone is ambiguous there.


def build_scene_objects(
    record: dict[str, Any], template: dict[str, Any], lexicon: dict[str, dict[str, str]]
) -> list[dict[str, Any]]:
    objects = []
    for obj in record["objects_raw"]:
        raw_name = obj["raw_name"]
        oid = obj["sim_handle"]
        role = template["roles"].get(oid)
        if role is None:
            continue  # covered by extra_objects (e.g. cabinet drawers)
        lex = lexicon[raw_name]
        objects.append(
            {
                "id": oid,
                "sim_handle": obj["sim_handle"],
                "raw_name": raw_name,
                "category_en": lex["category_en"],
                "category_ru": lex["category_ru"],
                "color_en": lex["color_en"],
                "color_ru": lex["color_ru"],
                "pose_xyz_initial": obj["pose_xyz"],
                "visible_agentview": obj["visible_agentview"],
                "visible_wrist": obj["visible_wrist"],
                "bbox2d_agentview": None,
                "mask_id_agentview": None,
                "role": role,
            }
        )
    for extra in template.get("extra_objects", []):
        base = next(o for o in record["objects_raw"] if o["sim_handle"] == extra["sim_handle"])
        lex = lexicon[extra["raw_name"]]
        objects.append(
            {
                "id": extra["id"],
                "sim_handle": extra["sim_handle"],
                "raw_name": extra["raw_name"],
                "category_en": lex["category_en"],
                "category_ru": lex["category_ru"],
                "color_en": lex["color_en"],
                "color_ru": lex["color_ru"],
                "pose_xyz_initial": base["pose_xyz"],
                "visible_agentview": base["visible_agentview"],
                "visible_wrist": base["visible_wrist"],
                "bbox2d_agentview": None,
                "mask_id_agentview": None,
                "role": extra["role"],
            }
        )
    return objects


def build_success_predicates(template: dict[str, Any]) -> list[dict[str, Any]]:
    """Structured success_predicates per task.md's "type: spatial_relation,
    relation, arg1, arg2" example, extended with a "state" type for the
    single-object open/turn_on tasks that example doesn't cover."""
    action = template["action"]
    if action == "open":
        return [{"type": "state", "predicate": "open", "arg1": template["target_id"]}]
    if action == "turn_on":
        return [{"type": "state", "predicate": "turned_on", "arg1": template["target_id"]}]
    return [
        {
            "type": "spatial_relation",
            "relation": template["relation"],
            "arg1": template["target_id"],
            "arg2": template["reference_id"],
        }
    ]


def build_frame(record: dict[str, Any], lexicon: dict[str, dict[str, str]]) -> dict[str, Any]:
    source = record["source"]
    task_name = source["task_name"]
    template = TEMPLATES[task_name]
    scene_objects = build_scene_objects(record, template, lexicon)

    axis_na: dict[str, str] = {}
    if template.get("ru_case_swap") is None:
        axis_na["ru_case_swap"] = template["ru_case_swap_na"]
    if template.get("ru_negation") is None and "ru_negation_na" in template:
        axis_na["ru_negation"] = template["ru_negation_na"]

    variants = {
        "en_canonical": record["canonical_en"],
        "en_paraphrase": template["en_paraphrase"],
        "mt_russian": None,
        "ru_literal": template["ru_literal"],
        "ru_free_order": template["ru_free_order"],
        "ru_case_swap": template.get("ru_case_swap"),
        "ru_negation": template.get("ru_negation"),
        "code_switch": template["code_switch"],
        "ru_translit": None,
        "ru_colloquial": None,
        "ru_anaphora": None,
    }

    is_libero = source["environment"] == "LIBERO"
    return {
        "task_uid": record["task_uid"],
        "suite": record["suite"],
        "task_id": record["task_id"],
        "init_state_id": source["init_state_id"] if is_libero else None,
        "frame_version": FRAME_VERSION,
        "canonical_en": record["canonical_en"],
        "bddl_file": source["bddl_file"] if is_libero else None,
        "environment": source["environment"],
        "commit": source["commit"],
        "task_name": source["task_name"],
        "episode_id": None if is_libero else source["episode_id"],
        "reset_seed": None if is_libero else source["reset_seed"],
        "gym_env_name": None if is_libero else source["gym_env_name"],
        "images": {
            "agentview_rgb": record["images"]["agentview_rgb"],
            "wrist_rgb": record["images"]["wrist_rgb"],
            "agentview_segmentation": None,
            "wrist_segmentation": None,
            "depth": None,
        },
        "scene": {"objects": scene_objects},
        "slots": {
            "action": template["action"],
            "target": template["target_id"],
            "reference": template["reference_id"],
            "relation": template["relation"],
            "forbidden": template["forbidden_ids"],
            "success_predicates": build_success_predicates(template),
        },
        "variants": variants,
        "mt_metadata": None,
        "axis_na": axis_na,
        "validation": {
            "author": AUTHOR,
            "native_check": "pending",
            "naturalness": {},
            "equivalence": {},
            "ambiguity": {},
            "notes": (
                "mt_russian requires a real MT pass (e.g. Google Translate), "
                "not authored by the LLM draft. All RU variants are LLM drafts "
                "pending human native check before freeze."
            ),
        },
        "token_len": {},
        "token_len_metadata": None,
    }


def main() -> None:
    lexicon = load_lexicon()
    selected = load_jsonl(SELECTED_PATH)
    missing = {r["source"]["task_name"] for r in selected} - set(TEMPLATES)
    if missing:
        raise SystemExit(f"No template for task_name(s): {sorted(missing)}")

    frames = [build_frame(record, lexicon) for record in selected]
    validate_frames(frames)
    save_jsonl(frames, OUTPUT_PATH)
    print(f"Wrote {len(frames)} frames to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
