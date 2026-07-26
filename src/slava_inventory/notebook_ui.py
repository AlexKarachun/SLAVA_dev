from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import ipywidgets as widgets
import pandas as pd
from IPython.display import display
from ipyevents import Event

from .io_utils import LEXICON_COLUMNS, build_object_lexicon, load_jsonl, save_jsonl, save_lexicon
from .schema import normalize_inventory_record, validate_inventory


REVIEW_FIELDS = (
    "usable_for_slava",
    "notes",
    "candidate_slots",
)


def merge_inventories(data_dir: str | Path) -> pd.DataFrame:
    """Merge collector outputs while preserving annotations in task_inventory.jsonl."""
    data_dir = Path(data_dir)
    combined_path = data_dir / "task_inventory.jsonl"
    previous = {
        row["task_uid"]: normalize_inventory_record(row) for row in load_jsonl(combined_path)
    }

    fresh: dict[str, dict[str, Any]] = {}
    for name in ("libero_inventory.jsonl", "simpler_inventory.jsonl"):
        for raw_row in load_jsonl(data_dir / name):
            row = normalize_inventory_record(raw_row)
            fresh[row["task_uid"]] = row

    if not fresh and previous:
        return pd.DataFrame(sorted(previous.values(), key=lambda row: row["task_uid"]))

    for uid, row in fresh.items():
        old = previous.get(uid)
        if old is None:
            continue
        for field in REVIEW_FIELDS:
            if field in old:
                row[field] = old[field]
        old_objects = {obj.get("sim_handle"): obj for obj in old.get("objects_raw", [])}
        for obj in row.get("objects_raw", []):
            old_obj = old_objects.get(obj.get("sim_handle"))
            if old_obj:
                obj["visible_agentview"] = old_obj.get("visible_agentview")
                obj["visible_wrist"] = old_obj.get("visible_wrist")

    records = sorted(fresh.values(), key=lambda row: row["task_uid"])
    validate_inventory(records)
    save_jsonl(records, combined_path)
    return pd.DataFrame(records)


def load_inventory_dataframe(data_dir: str | Path) -> pd.DataFrame:
    records = [
        normalize_inventory_record(row)
        for row in load_jsonl(Path(data_dir) / "task_inventory.jsonl")
    ]
    validate_inventory(records)
    return pd.DataFrame(records)


def export_inventory_dataframe(df: pd.DataFrame, path: str | Path) -> None:
    records = [normalize_inventory_record(row) for row in df.to_dict(orient="records")]
    validate_inventory(records)
    save_jsonl(records, path)


def create_or_update_lexicon(data_dir: str | Path, df: pd.DataFrame) -> pd.DataFrame:
    data_dir = Path(data_dir)
    lexicon_path = data_dir / "object_lexicon.csv"
    rows = build_object_lexicon(df.to_dict(orient="records"), lexicon_path)
    save_lexicon(rows, lexicon_path)
    return pd.DataFrame(rows, columns=LEXICON_COLUMNS)


def _visibility_to_widget(value: Any) -> str:
    if value is True:
        return "visible"
    if value is False:
        return "not_visible"
    if value in {"visible_partial", "partial"}:
        return "visible_partial"
    return "unknown"


def _visibility_from_widget(value: str) -> bool | str | None:
    return {
        "visible": True,
        "visible_partial": "visible_partial",
        "not_visible": False,
        "unknown": None,
    }[value]


class InventoryReviewer:
    """Small ipywidgets form that edits a scene-inventory DataFrame in place."""

    def __init__(self, df: pd.DataFrame, data_dir: str | Path):
        if df.empty:
            raise ValueError("Inventory is empty. Run collectors and merge their outputs first.")
        self.df = df.reset_index(drop=True)
        self.data_dir = Path(data_dir)
        self.position = 0
        self.filtered_indices: list[int] = []
        self.object_visibility_widgets: list[tuple[widgets.Dropdown, widgets.Dropdown]] = []

        suites = ["all"] + sorted(str(x) for x in self.df["suite"].dropna().unique())
        self.suite_filter = widgets.Dropdown(options=suites, value="all", description="Suite")
        self.status_filter = widgets.Dropdown(
            options=["all", "pending", "reviewed"], value="all", description="Status"
        )
        self.prev_button = widgets.Button(description="← Previous")
        self.next_button = widgets.Button(description="Next →")
        self.save_button = widgets.Button(description="Save scene", button_style="success")
        self.export_button = widgets.Button(description="Export JSONL", button_style="info")
        self.progress = widgets.HTML()
        self.title = widgets.HTML()
        self.metadata = widgets.HTML()
        self.agent_image = widgets.Image(format="png", layout=widgets.Layout(max_width="520px"))
        self.wrist_image = widgets.Image(format="png", layout=widgets.Layout(max_width="320px"))
        self.wrist_placeholder = widgets.HTML()

        self.usable = widgets.Dropdown(
            options=[("Pending", "pending"), ("Yes", "yes"), ("No", "no")],
            description="Usable",
        )
        self.notes = widgets.Textarea(description="Notes", layout=widgets.Layout(width="95%"))
        self.action = widgets.Text(description="Action")
        self.target = widgets.Text(description="Target")
        self.reference = widgets.Text(description="Reference")
        self.relation = widgets.Text(description="Relation")
        self.forbidden = widgets.Textarea(
            description="Forbidden", placeholder="comma-separated sim handles", layout=widgets.Layout(width="95%")
        )
        self.objects_box = widgets.VBox()
        self.message = widgets.HTML()

        self.suite_filter.observe(self._on_filter_change, names="value")
        self.status_filter.observe(self._on_filter_change, names="value")
        self.prev_button.on_click(self._previous)
        self.next_button.on_click(self._next)
        self.save_button.on_click(self._save_clicked)
        self.export_button.on_click(self._export_clicked)

        controls = widgets.HBox([self.suite_filter, self.status_filter, self.prev_button, self.next_button])
        images = widgets.HBox(
            [
                widgets.VBox([widgets.HTML("<b>Agent view</b>"), self.agent_image]),
                widgets.VBox([widgets.HTML("<b>Wrist view</b>"), self.wrist_image, self.wrist_placeholder]),
            ]
        )
        decisions = widgets.VBox(
            [
                self.usable,
                self.notes,
            ]
        )
        slots = widgets.VBox(
            [widgets.HTML("<h4>Candidate semantic slots</h4>"), self.action, self.target, self.reference, self.relation, self.forbidden]
        )
        self.widget = widgets.VBox(
            [
                controls,
                self.progress,
                self.title,
                self.metadata,
                images,
                widgets.HTML("<h4>Decision</h4>"),
                decisions,
                slots,
                widgets.HTML("<h4>Object visibility</h4>"),
                self.objects_box,
                widgets.HBox([self.save_button, self.export_button]),
                self.message,
            ]
        )
        self._apply_filters()

    def _apply_filters(self) -> None:
        indices = list(range(len(self.df)))
        if self.suite_filter.value != "all":
            indices = [i for i in indices if self.df.at[i, "suite"] == self.suite_filter.value]
        if self.status_filter.value == "pending":
            indices = [i for i in indices if pd.isna(self.df.at[i, "usable_for_slava"])]
        elif self.status_filter.value == "reviewed":
            indices = [i for i in indices if pd.notna(self.df.at[i, "usable_for_slava"])]
        self.filtered_indices = indices
        self.position = min(self.position, max(len(indices) - 1, 0))
        self._render()

    def _current_index(self) -> int:
        if not self.filtered_indices:
            raise IndexError("No scenes match the current filter")
        return self.filtered_indices[self.position]

    def _on_filter_change(self, change: dict[str, Any]) -> None:
        self.position = 0
        self._apply_filters()

    def _load_image(self, relative_path: str | None, target: widgets.Image) -> bool:
        if not relative_path:
            target.value = b""
            return False
        path = self.data_dir / relative_path
        if not path.exists():
            target.value = b""
            return False
        target.value = path.read_bytes()
        return True

    def _render(self) -> None:
        if not self.filtered_indices:
            self.progress.value = "<b>No scenes match this filter.</b>"
            self.title.value = ""
            self.metadata.value = ""
            return
        idx = self._current_index()
        row = self.df.loc[idx]
        reviewed = int(self.df["usable_for_slava"].notna().sum())
        self.progress.value = (
            f"Scene {self.position + 1}/{len(self.filtered_indices)} · "
            f"reviewed {reviewed}/{len(self.df)}"
        )
        self.title.value = f"<h3>{html.escape(str(row['canonical_en']))}</h3><code>{html.escape(str(row['task_uid']))}</code>"
        source = row["source"]
        state_label = (
            f"init_state={source['init_state_id']}"
            if source["environment"] == "LIBERO"
            else f"episode={source['episode_id']}"
        )
        self.metadata.value = (
            f"<b>suite:</b> {html.escape(str(row['suite']))} · "
            f"<b>task:</b> {html.escape(str(source['task_name']))} · "
            f"<b>{html.escape(state_label)}</b>"
        )
        images = row["images"]
        self._load_image(images.get("agentview_rgb"), self.agent_image)
        has_wrist = self._load_image(images.get("wrist_rgb"), self.wrist_image)
        self.wrist_placeholder.value = "" if has_wrist else "<i>Not available for this environment</i>"

        usable = row.get("usable_for_slava")
        self.usable.value = "yes" if usable is True else "no" if usable is False else "pending"
        self.notes.value = str(row.get("notes") or "")
        slots = row.get("candidate_slots") or {}
        self.action.value = str(slots.get("action") or "")
        self.target.value = str(slots.get("target") or "")
        self.reference.value = str(slots.get("reference") or "")
        self.relation.value = str(slots.get("relation") or "")
        self.forbidden.value = ", ".join(slots.get("forbidden_candidates") or [])

        object_rows = []
        self.object_visibility_widgets = []
        wrist_available = bool(images.get("wrist_rgb"))
        visibility_options = [
            ("Unknown", "unknown"),
            ("Visible", "visible"),
            ("Partially visible", "visible_partial"),
            ("Not visible", "not_visible"),
        ]
        for obj in row.get("objects_raw", []):
            agent = widgets.Dropdown(
                options=visibility_options,
                value=_visibility_to_widget(obj.get("visible_agentview")),
                description="agent",
                layout=widgets.Layout(width="210px"),
            )
            wrist = widgets.Dropdown(
                options=visibility_options,
                value=_visibility_to_widget(obj.get("visible_wrist")),
                description="wrist",
                disabled=not wrist_available,
                layout=widgets.Layout(width="210px"),
            )
            label = widgets.HTML(
                f"<code>{html.escape(str(obj.get('sim_handle')))}</code> "
                f"({html.escape(str(obj.get('raw_name')))})",
                layout=widgets.Layout(width="420px"),
            )
            object_rows.append(widgets.HBox([label, agent, wrist]))
            self.object_visibility_widgets.append((agent, wrist))
        self.objects_box.children = tuple(object_rows)
        self.message.value = ""

    def save_current(self) -> None:
        idx = self._current_index()
        self.df.at[idx, "usable_for_slava"] = {
            "yes": True,
            "no": False,
            "pending": None,
        }[self.usable.value]
        self.df.at[idx, "notes"] = self.notes.value.strip()
        self.df.at[idx, "candidate_slots"] = {
            "action": self.action.value.strip() or None,
            "target": self.target.value.strip() or None,
            "reference": self.reference.value.strip() or None,
            "relation": self.relation.value.strip() or None,
            "forbidden_candidates": [x.strip() for x in self.forbidden.value.split(",") if x.strip()],
        }
        objects = self.df.at[idx, "objects_raw"]
        for obj, (agent, wrist) in zip(objects, self.object_visibility_widgets):
            obj["visible_agentview"] = _visibility_from_widget(agent.value)
            obj["visible_wrist"] = _visibility_from_widget(wrist.value) if not wrist.disabled else None
        self.df.at[idx, "objects_raw"] = objects

    def _save_clicked(self, button: widgets.Button) -> None:
        self.save_current()
        self._render()
        self.message.value = "<span style='color:green'>Scene saved in DataFrame.</span>"

    def _previous(self, button: widgets.Button) -> None:
        self.save_current()
        self.position = max(0, self.position - 1)
        self._render()

    def _next(self, button: widgets.Button) -> None:
        self.save_current()
        self.position = min(len(self.filtered_indices) - 1, self.position + 1)
        self._render()

    def _export_clicked(self, button: widgets.Button) -> None:
        self.save_current()
        path = self.data_dir / "task_inventory.jsonl"
        export_inventory_dataframe(self.df, path)
        self.message.value = f"<span style='color:green'>Exported {len(self.df)} rows to {html.escape(str(path))}.</span>"

    def show(self) -> None:
        display(self.widget)


class VisibilityReviewer:
    """Fast scene-by-scene review of benchmark-object visibility."""

    def __init__(self, df: pd.DataFrame, data_dir: str | Path):
        if df.empty:
            raise ValueError("Inventory is empty. Run collectors and merge their outputs first.")
        self.df = df.reset_index(drop=True)
        self.data_dir = Path(data_dir)
        self.position = 0
        self.filtered_indices: list[int] = []
        self.object_widgets: list[tuple[dict[str, Any], widgets.ToggleButtons, widgets.ToggleButtons]] = []

        suites = ["all"] + sorted(str(x) for x in self.df["suite"].dropna().unique())
        self.suite_filter = widgets.Dropdown(options=suites, value="all", description="Suite")
        self.status_filter = widgets.Dropdown(
            options=[("Only unfinished", "pending"), ("All scenes", "all"), ("Finished", "finished")],
            value="pending",
            description="Show",
        )
        self.prev_button = widgets.Button(description="← Previous")
        self.save_next_button = widgets.Button(
            description="Save + next →", button_style="success", icon="check"
        )
        self.all_agent_button = widgets.Button(description="All visible: agent")
        self.all_wrist_button = widgets.Button(description="All visible: wrist")
        self.progress = widgets.HTML()
        self.title = widgets.HTML()
        self.metadata = widgets.HTML()
        self.agent_image = widgets.Image(format="png", layout=widgets.Layout(max_width="560px"))
        self.wrist_image = widgets.Image(format="png", layout=widgets.Layout(max_width="420px"))
        self.wrist_placeholder = widgets.HTML()
        self.objects_box = widgets.VBox()
        self.message = widgets.HTML()

        self.suite_filter.observe(self._on_filter_change, names="value")
        self.status_filter.observe(self._on_filter_change, names="value")
        self.prev_button.on_click(self._previous)
        self.save_next_button.on_click(self._save_and_next)
        self.all_agent_button.on_click(self._all_agent_visible)
        self.all_wrist_button.on_click(self._all_wrist_visible)

        controls = widgets.HBox(
            [self.suite_filter, self.status_filter, self.prev_button, self.save_next_button]
        )
        images = widgets.HBox(
            [
                widgets.VBox([widgets.HTML("<b>Agent view</b>"), self.agent_image]),
                widgets.VBox(
                    [widgets.HTML("<b>Wrist view</b>"), self.wrist_image, self.wrist_placeholder]
                ),
            ]
        )
        bulk_controls = widgets.HBox([self.all_agent_button, self.all_wrist_button])
        self.widget = widgets.VBox(
            [
                controls,
                self.progress,
                self.title,
                self.metadata,
                images,
                widgets.HTML("<h4>Objects mentioned by the benchmark</h4>"),
                bulk_controls,
                self.objects_box,
                self.message,
            ]
        )
        self._apply_filters(jump_to_first_pending=True)

    @staticmethod
    def _benchmark_objects(row: pd.Series) -> tuple[list[tuple[str, dict[str, Any]]], list[str]]:
        """Return all canonical inventory objects for visibility review."""
        objects = list(row.get("objects_raw") or [])
        return [(str(obj.get("sim_handle")), obj) for obj in objects], []

    def _scene_complete(self, idx: int) -> bool:
        row = self.df.loc[idx]
        objects, _ = self._benchmark_objects(row)
        wrist_available = bool((row.get("images") or {}).get("wrist_rgb"))
        return bool(objects) and all(
            obj.get("visible_agentview") is not None
            and (not wrist_available or obj.get("visible_wrist") is not None)
            for _, obj in objects
        )

    def _apply_filters(self, *, jump_to_first_pending: bool = False) -> None:
        indices = list(range(len(self.df)))
        if self.suite_filter.value != "all":
            indices = [i for i in indices if self.df.at[i, "suite"] == self.suite_filter.value]
        if self.status_filter.value == "pending":
            indices = [i for i in indices if not self._scene_complete(i)]
        elif self.status_filter.value == "finished":
            indices = [i for i in indices if self._scene_complete(i)]
        self.filtered_indices = indices
        self.position = 0 if jump_to_first_pending else min(self.position, max(len(indices) - 1, 0))
        self._render()

    def _on_filter_change(self, change: dict[str, Any]) -> None:
        self._apply_filters(jump_to_first_pending=True)

    def _current_index(self) -> int:
        if not self.filtered_indices:
            raise IndexError("No scenes match the current filter")
        return self.filtered_indices[self.position]

    def _load_image(self, relative_path: str | None, target: widgets.Image) -> bool:
        if not relative_path:
            target.value = b""
            return False
        path = self.data_dir / relative_path
        if not path.exists():
            target.value = b""
            return False
        target.value = path.read_bytes()
        return True

    @staticmethod
    def _toggle(value: Any, description: str, disabled: bool = False) -> widgets.ToggleButtons:
        return widgets.ToggleButtons(
            options=[
                ("?", "unknown"),
                ("✓ visible", "visible"),
                ("◐ partial", "visible_partial"),
                ("✗ not visible", "not_visible"),
            ],
            value=_visibility_to_widget(value),
            description=description,
            disabled=disabled,
            style={"button_width": "105px"},
            layout=widgets.Layout(width="500px"),
        )

    def _render(self) -> None:
        if not self.filtered_indices:
            complete = sum(self._scene_complete(i) for i in range(len(self.df)))
            self.progress.value = f"<b>No scenes match this filter. Finished {complete}/{len(self.df)}.</b>"
            self.title.value = ""
            self.metadata.value = ""
            self.objects_box.children = ()
            return

        idx = self._current_index()
        row = self.df.loc[idx]
        complete = sum(self._scene_complete(i) for i in range(len(self.df)))
        self.progress.value = (
            f"Scene {self.position + 1}/{len(self.filtered_indices)} in filter · "
            f"visibility finished {complete}/{len(self.df)}"
        )
        self.title.value = (
            f"<h3>{html.escape(str(row['canonical_en']))}</h3>"
            f"<code>{html.escape(str(row['task_uid']))}</code>"
        )
        self.metadata.value = (
            f"<b>suite:</b> {html.escape(str(row['suite']))} · "
            f"<b>task:</b> {html.escape(str(row['source']['task_name']))}"
        )
        images = row.get("images") or {}
        self._load_image(images.get("agentview_rgb"), self.agent_image)
        wrist_available = self._load_image(images.get("wrist_rgb"), self.wrist_image)
        self.wrist_placeholder.value = "" if wrist_available else "<i>No wrist camera in this dataset</i>"
        self.all_wrist_button.disabled = not wrist_available

        resolved, unresolved = self._benchmark_objects(row)
        object_rows: list[widgets.Widget] = []
        self.object_widgets = []
        for interest, obj in resolved:
            handle = str(obj.get("sim_handle"))
            mapping = "" if interest == handle else f" ← {interest}"
            label = widgets.HTML(
                f"<code>{html.escape(handle)}</code>{html.escape(mapping)}<br>"
                f"<small>{html.escape(str(obj.get('raw_name') or ''))}</small>",
                layout=widgets.Layout(width="430px"),
            )
            agent = self._toggle(obj.get("visible_agentview"), "agent")
            wrist = self._toggle(obj.get("visible_wrist"), "wrist", disabled=not wrist_available)
            object_rows.append(widgets.HBox([label, agent, wrist]))
            self.object_widgets.append((obj, agent, wrist))
        if unresolved:
            object_rows.append(
                widgets.HTML(
                    "<b style='color:#b45309'>Unresolved semantic regions (no body visibility field):</b> "
                    + html.escape(", ".join(unresolved))
                )
            )
        self.objects_box.children = tuple(object_rows)
        self.message.value = ""

    def save_current(self) -> None:
        idx = self._current_index()
        objects = self.df.at[idx, "objects_raw"]
        for obj, agent, wrist in self.object_widgets:
            obj["visible_agentview"] = _visibility_from_widget(agent.value)
            obj["visible_wrist"] = _visibility_from_widget(wrist.value) if not wrist.disabled else None
        self.df.at[idx, "objects_raw"] = objects
        export_inventory_dataframe(self.df, self.data_dir / "task_inventory.jsonl")

    def _all_agent_visible(self, button: widgets.Button) -> None:
        for _, agent, _ in self.object_widgets:
            agent.value = "visible"

    def _all_wrist_visible(self, button: widgets.Button) -> None:
        for _, _, wrist in self.object_widgets:
            if not wrist.disabled:
                wrist.value = "visible"

    def _previous(self, button: widgets.Button) -> None:
        self.save_current()
        self.position = max(0, self.position - 1)
        self._render()

    def _save_and_next(self, button: widgets.Button) -> None:
        self.save_current()
        if self.status_filter.value == "pending":
            self._apply_filters(jump_to_first_pending=True)
        else:
            self.position = min(self.position + 1, len(self.filtered_indices) - 1)
            self._render()
        self.message.value = "<span style='color:green'>Saved to task_inventory.jsonl.</span>"

    def show(self) -> None:
        display(self.widget)


class LexiconReviewer:
    """Form for editing object_lexicon.csv without requiring a spreadsheet widget."""

    def __init__(self, df: pd.DataFrame, path: str | Path):
        if df.empty:
            raise ValueError("Lexicon is empty")
        self.df = df.reset_index(drop=True)
        self.path = Path(path)
        self.position = 0
        self.progress = widgets.HTML()
        self.raw_name = widgets.Text(description="Raw name", disabled=True, layout=widgets.Layout(width="90%"))
        self.category_en = widgets.Text(description="EN category", layout=widgets.Layout(width="90%"))
        self.category_ru = widgets.Text(description="RU category", layout=widgets.Layout(width="90%"))
        self.color_en = widgets.Text(description="EN color", layout=widgets.Layout(width="90%"))
        self.color_ru = widgets.Text(description="RU color", layout=widgets.Layout(width="90%"))
        self.synonyms = widgets.Text(description="RU synonyms", layout=widgets.Layout(width="90%"))
        self.usable = widgets.Dropdown(options=["review", "yes", "no"], description="Usable v0")
        self.notes = widgets.Textarea(description="Notes", layout=widgets.Layout(width="90%"))
        self.prev_button = widgets.Button(description="← Previous")
        self.next_button = widgets.Button(description="Next →")
        self.save_button = widgets.Button(description="Save CSV", button_style="success")
        self.message = widgets.HTML()
        self.prev_button.on_click(self._previous)
        self.next_button.on_click(self._next)
        self.save_button.on_click(self._save_clicked)
        self.widget = widgets.VBox(
            [
                self.progress,
                self.raw_name,
                self.category_en,
                self.category_ru,
                self.color_en,
                self.color_ru,
                self.synonyms,
                self.usable,
                self.notes,
                widgets.HBox([self.prev_button, self.next_button, self.save_button]),
                self.message,
            ]
        )
        self._render()

    def _render(self) -> None:
        row = self.df.loc[self.position]
        annotated = int((self.df["usable_v0"] != "review").sum())
        self.progress.value = f"Object {self.position + 1}/{len(self.df)} · annotated {annotated}/{len(self.df)}"
        self.raw_name.value = str(row["raw_name"])
        self.category_en.value = str(row["category_en"] or "")
        self.category_ru.value = str(row["category_ru"] or "")
        self.color_en.value = str(row["color_en"] or "")
        self.color_ru.value = str(row["color_ru"] or "")
        self.synonyms.value = str(row["allowed_synonyms_ru"] or "")
        self.usable.value = str(row["usable_v0"] or "review")
        self.notes.value = str(row["notes"] or "")
        self.message.value = ""

    def save_current(self) -> None:
        idx = self.position
        self.df.at[idx, "category_en"] = self.category_en.value.strip()
        self.df.at[idx, "category_ru"] = self.category_ru.value.strip()
        self.df.at[idx, "color_en"] = self.color_en.value.strip()
        self.df.at[idx, "color_ru"] = self.color_ru.value.strip()
        self.df.at[idx, "allowed_synonyms_ru"] = self.synonyms.value.strip()
        self.df.at[idx, "usable_v0"] = self.usable.value
        self.df.at[idx, "notes"] = self.notes.value.strip()

    def _previous(self, button: widgets.Button) -> None:
        self.save_current()
        self.position = max(0, self.position - 1)
        self._render()

    def _next(self, button: widgets.Button) -> None:
        self.save_current()
        self.position = min(len(self.df) - 1, self.position + 1)
        self._render()

    def _save_clicked(self, button: widgets.Button) -> None:
        self.save_current()
        save_lexicon(self.df.to_dict(orient="records"), self.path)
        self._render()
        self.message.value = f"<span style='color:green'>Saved {html.escape(str(self.path))}.</span>"

    def show(self) -> None:
        display(self.widget)


class TopSceneSelector:
    """Dashboard that keeps qualifying scenes unless the reviewer excludes them."""

    TARGET_REMAINING = 20

    def __init__(
        self,
        df: pd.DataFrame,
        lexicon_df: pd.DataFrame,
        data_dir: str | Path,
    ):
        if df.empty:
            raise ValueError("Inventory is empty")
        if lexicon_df.empty:
            raise ValueError("Object lexicon is empty")

        self.df = df.reset_index(drop=True)
        self.data_dir = Path(data_dir)
        self.lexicon = {
            str(row["raw_name"]): row
            for row in lexicon_df.fillna("").to_dict(orient="records")
        }
        self.checkboxes: dict[int, widgets.Checkbox] = {}
        self.card_widgets: dict[int, widgets.Widget] = {}
        self.card_events: list[Event] = []
        self.exclusion_stack: list[int] = []
        self._updating_checkbox = False

        self.qualifying_indices = [
            idx for idx in range(len(self.df)) if self._qualifies(self.df.loc[idx])
        ]
        self.summary = widgets.HTML()
        self.message = widgets.HTML()
        self.save_button = widgets.Button(
            description="Сохранить оставшиеся сцены",
            button_style="success",
            icon="save",
            layout=widgets.Layout(width="280px"),
        )
        self.undo_button = widgets.Button(
            description="← Вернуть последнюю",
            icon="undo",
            layout=widgets.Layout(width="220px"),
        )
        self.save_button.on_click(self._save_clicked)
        self.undo_button.on_click(self._undo_clicked)

        for idx in self.qualifying_indices:
            self.card_widgets[idx] = self._build_card(idx)
        self.exclusion_stack = [
            idx for idx in self.qualifying_indices if self.checkboxes[idx].value
        ]
        self.cards = widgets.GridBox(
            [],
            layout=widgets.Layout(
                width="100%",
                grid_template_columns="repeat(auto-fit, minmax(620px, 1fr))",
                grid_gap="16px",
                align_items="flex-start",
            ),
        )
        self.empty_state = widgets.HTML()
        self._refresh_cards()

        criteria = widgets.HTML(
            "<h3>Отбор сцен через исключение неудачных</h3>"
            "<p>Minimum annotated <code>visible_agentview = true</code> · "
            "minimum annotated <code>visible_wrist ≥ visible_partial</code> when "
            "a wrist camera exists · <code>object_lexicon.usable_v0 = yes</code> "
            "for every object. Null visibility values are ignored, matching the "
            "screenshot-sheet filters. SimplerEnv wrist visibility is treated as N/A.</p>"
            "<p>Все показанные сцены по умолчанию остаются. Отметьте галочкой только "
            "неудачные сцены, которые нужно исключить: отмеченная карточка сразу "
            "исчезнет. Кнопка «← Вернуть последнюю» отменяет последнее исключение. "
            "При сохранении оставшиеся получат <code>usable_for_slava=true</code>, "
            "исключенные — <code>usable_for_slava=false</code>.</p>"
        )
        self.widget = widgets.VBox(
            [
                criteria,
                self.summary,
                widgets.HBox([self.save_button, self.undo_button]),
                self.message,
                self.empty_state,
                self.cards,
            ],
            layout=widgets.Layout(width="100%"),
        )
        self._update_summary()

    @staticmethod
    def _visibility_rank(value: Any) -> int:
        if value is True:
            return 2
        if value == "visible_partial":
            return 1
        return 0

    def _qualifies(self, row: pd.Series) -> bool:
        objects = list(row.get("objects_raw") or [])
        if not objects:
            return False
        agent_ranks = [
            self._visibility_rank(obj.get("visible_agentview"))
            for obj in objects
            if obj.get("visible_agentview") is not None
        ]
        if not agent_ranks or min(agent_ranks) < 2:
            return False

        wrist_available = bool((row.get("images") or {}).get("wrist_rgb"))
        if wrist_available:
            wrist_ranks = [
                self._visibility_rank(obj.get("visible_wrist"))
                for obj in objects
                if obj.get("visible_wrist") is not None
            ]
            if not wrist_ranks or min(wrist_ranks) < 1:
                return False

        return all(
            str(obj.get("raw_name")) in self.lexicon
            and self.lexicon[str(obj.get("raw_name"))].get("usable_v0") == "yes"
            for obj in objects
        )

    def _image_widget(self, relative_path: str | None, label: str) -> widgets.Widget:
        if not relative_path:
            return widgets.HTML(f"<b>{html.escape(label)}</b><br><i>N/A</i>")
        path = self.data_dir / relative_path
        if not path.is_file():
            return widgets.HTML(
                f"<b>{html.escape(label)}</b><br>"
                f"<span style='color:#b91c1c'>Missing: {html.escape(str(relative_path))}</span>"
            )
        image = widgets.Image(
            value=path.read_bytes(),
            format=path.suffix.lstrip(".") or "png",
            layout=widgets.Layout(width="100%", max_width="340px", height="auto"),
        )
        return widgets.VBox([widgets.HTML(f"<b>{html.escape(label)}</b>"), image])

    def _lexicon_table(self, objects: list[dict[str, Any]]) -> widgets.HTML:
        rows = []
        for obj in objects:
            raw_name = str(obj.get("raw_name") or "")
            lexical = self.lexicon[raw_name]
            cells = [
                raw_name,
                str(obj.get("sim_handle") or ""),
                str(lexical.get("category_en") or ""),
                str(lexical.get("category_ru") or ""),
                str(lexical.get("color_en") or ""),
                str(lexical.get("color_ru") or ""),
                str(lexical.get("allowed_synonyms_ru") or ""),
                str(lexical.get("usable_v0") or ""),
            ]
            rows.append(
                "<tr>"
                + "".join(f"<td>{html.escape(value)}</td>" for value in cells)
                + "</tr>"
            )
        headers = [
            "raw_name",
            "sim_handle",
            "category_en",
            "category_ru",
            "color_en",
            "color_ru",
            "allowed_synonyms_ru",
            "usable_v0",
        ]
        return widgets.HTML(
            "<div style='overflow-x:auto'>"
            "<table style='border-collapse:collapse;width:100%;font-size:12px'>"
            "<thead><tr>"
            + "".join(
                f"<th style='border:1px solid #cbd5e1;padding:4px;text-align:left'>"
                f"{html.escape(field)}</th>"
                for field in headers
            )
            + "</tr></thead><tbody>"
            + "".join(rows).replace(
                "<td>", "<td style='border:1px solid #cbd5e1;padding:4px'>"
            )
            + "</tbody></table></div>"
        )

    def _build_card(self, idx: int) -> widgets.Widget:
        row = self.df.loc[idx]
        checkbox = widgets.Checkbox(
            value=row.get("usable_for_slava") is False,
            description="Исключить сцену",
            indent=False,
            style={"description_width": "initial"},
        )
        checkbox.observe(
            lambda change, scene_idx=idx: self._exclusion_changed(scene_idx, change),
            names="value",
        )
        self.checkboxes[idx] = checkbox

        source = row["source"]
        state = (
            f"init_state_id={source['init_state_id']}"
            if source["environment"] == "LIBERO"
            else f"episode_id={source['episode_id']} · reset_seed={source['reset_seed']}"
        )
        heading = widgets.HTML(
            f"<h4 style='margin:0 0 4px'>{html.escape(str(row['canonical_en']))}</h4>"
            f"<code>{html.escape(str(row['task_uid']))}</code><br>"
            f"<small>suite={html.escape(str(row['suite']))} · "
            f"{html.escape(state)}</small>"
        )
        images = row.get("images") or {}
        image_row = widgets.HBox(
            [
                self._image_widget(images.get("agentview_rgb"), "agentview_rgb"),
                self._image_widget(images.get("wrist_rgb"), "wrist_rgb"),
            ],
            layout=widgets.Layout(width="100%", gap="12px", align_items="flex-start"),
        )
        card = widgets.VBox(
            [
                widgets.HBox([checkbox]),
                heading,
                image_row,
                self._lexicon_table(list(row.get("objects_raw") or [])),
            ],
            layout=widgets.Layout(
                border="1px solid #cbd5e1",
                padding="12px",
                width="100%",
                cursor="pointer",
            ),
        )
        card_event = Event(source=card, watched_events=["click"])
        card_event.on_dom_event(
            lambda event, scene_checkbox=checkbox: self._card_clicked(
                event, scene_checkbox
            )
        )
        self.card_events.append(card_event)
        return card

    def _card_clicked(
        self, event: dict[str, Any], checkbox: widgets.Checkbox
    ) -> None:
        target = event.get("target") or {}
        if str(target.get("tagName") or "").upper() in {"INPUT", "LABEL"}:
            return
        checkbox.value = not checkbox.value

    def _excluded_indices(self) -> list[int]:
        return [idx for idx, checkbox in self.checkboxes.items() if checkbox.value]

    def _kept_indices(self) -> list[int]:
        excluded = set(self._excluded_indices())
        return [idx for idx in self.qualifying_indices if idx not in excluded]

    def _exclusion_changed(self, idx: int, change: dict[str, Any]) -> None:
        if self._updating_checkbox:
            return
        if change["new"]:
            if idx not in self.exclusion_stack:
                self.exclusion_stack.append(idx)
        else:
            self.exclusion_stack = [
                excluded_idx
                for excluded_idx in self.exclusion_stack
                if excluded_idx != idx
            ]
        self.message.value = ""
        self._refresh_cards()
        self._update_summary()

    def _refresh_cards(self) -> None:
        visible_indices = [
            idx for idx in self.qualifying_indices if not self.checkboxes[idx].value
        ]
        self.cards.children = tuple(self.card_widgets[idx] for idx in visible_indices)
        if not self.qualifying_indices:
            self.empty_state.value = (
                "<b>No scenes meet all three filters yet.</b> "
                "Finish visibility review and rerun this cell."
            )
        elif not visible_indices:
            self.empty_state.value = (
                "<b>Все подходящие сцены исключены.</b> "
                "Нажмите «← Вернуть последнюю», чтобы отменить последнее исключение."
            )
        else:
            self.empty_state.value = ""
        self.undo_button.disabled = not self.exclusion_stack

    def _update_summary(self) -> None:
        kept = self._kept_indices()
        excluded = self._excluded_indices()
        suites = {
            suite: sum(self.df.at[idx, "suite"] == suite for idx in kept)
            for suite in sorted({str(self.df.at[idx, "suite"]) for idx in kept})
        }
        suite_text = " · ".join(f"{suite}: {count}" for suite, count in suites.items())
        target_delta = len(kept) - self.TARGET_REMAINING
        if target_delta > 0:
            target_text = f"До ориентира 20 нужно исключить еще {target_delta}."
        elif target_delta < 0:
            target_text = f"Осталось на {-target_delta} меньше ориентира 20."
        else:
            target_text = "Ориентир 20 сцен достигнут."
        self.summary.value = (
            f"<b>Кандидатов: {len(self.qualifying_indices)} · "
            f"останется: {len(kept)} · исключено: {len(excluded)}</b>"
            f"<br>{html.escape(target_text)}"
            + (f"<br>{html.escape(suite_text)}" if suite_text else "")
        )

    def _undo_clicked(self, button: widgets.Button) -> None:
        if not self.exclusion_stack:
            self.message.value = "<span>Нет исключенных сцен для возврата.</span>"
            return
        idx = self.exclusion_stack.pop()
        self._updating_checkbox = True
        self.checkboxes[idx].value = False
        self._updating_checkbox = False
        self.message.value = (
            f"<span>Возвращена сцена <code>"
            f"{html.escape(str(self.df.at[idx, 'task_uid']))}</code>.</span>"
        )
        self._refresh_cards()
        self._update_summary()

    def _save_clicked(self, button: widgets.Button) -> None:
        for idx, checkbox in self.checkboxes.items():
            self.df.at[idx, "usable_for_slava"] = not bool(checkbox.value)
        path = self.data_dir / "task_inventory.jsonl"
        export_inventory_dataframe(self.df, path)
        self.message.value = (
            f"<span style='color:green'>Сохранено: {len(self._kept_indices())} удачных, "
            f"{len(self._excluded_indices())} исключенных сцен · "
            f"{html.escape(str(path))}.</span>"
        )
        self._update_summary()

    def show(self) -> None:
        display(self.widget)
