from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import ipywidgets as widgets
import pandas as pd
from IPython.display import display

from .io_utils import LEXICON_COLUMNS, build_object_lexicon, load_jsonl, save_jsonl, save_lexicon


REVIEW_FIELDS = (
    "usable_for_slava",
    "selected_for_v0",
    "review_status",
    "exclusion_reasons",
    "notes",
    "candidate_slots",
)


def merge_inventories(data_dir: str | Path) -> pd.DataFrame:
    """Merge collector outputs while preserving annotations in task_inventory.jsonl."""
    data_dir = Path(data_dir)
    combined_path = data_dir / "task_inventory.jsonl"
    previous = {row["task_uid"]: row for row in load_jsonl(combined_path)}

    fresh: dict[str, dict[str, Any]] = {}
    for name in ("libero_inventory.jsonl", "simpler_inventory.jsonl"):
        for row in load_jsonl(data_dir / name):
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
    save_jsonl(records, combined_path)
    return pd.DataFrame(records)


def load_inventory_dataframe(data_dir: str | Path) -> pd.DataFrame:
    records = load_jsonl(Path(data_dir) / "task_inventory.jsonl")
    return pd.DataFrame(records)


def export_inventory_dataframe(df: pd.DataFrame, path: str | Path) -> None:
    save_jsonl(df.to_dict(orient="records"), path)


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
    return "unknown"


def _visibility_from_widget(value: str) -> bool | None:
    return {"visible": True, "not_visible": False, "unknown": None}[value]


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
        self.selected = widgets.Checkbox(description="Selected for v0")
        self.review_status = widgets.Dropdown(
            options=["pending", "reviewed", "needs_discussion"], description="Review"
        )
        self.exclusion_reasons = widgets.Textarea(
            description="Exclusions", placeholder="comma-separated reasons", layout=widgets.Layout(width="95%")
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
                widgets.HBox([self.usable, self.selected, self.review_status]),
                self.exclusion_reasons,
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
            indices = [i for i in indices if self.df.at[i, "review_status"] == "pending"]
        elif self.status_filter.value == "reviewed":
            indices = [i for i in indices if self.df.at[i, "review_status"] != "pending"]
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
        reviewed = int((self.df["review_status"] != "pending").sum())
        selected = int(self.df["selected_for_v0"].fillna(False).astype(bool).sum())
        self.progress.value = (
            f"Scene {self.position + 1}/{len(self.filtered_indices)} · "
            f"reviewed {reviewed}/{len(self.df)} · selected {selected}"
        )
        self.title.value = f"<h3>{html.escape(str(row['canonical_en']))}</h3><code>{html.escape(str(row['task_uid']))}</code>"
        state_label = (
            f"init_state={row.get('init_state_id')}" if pd.notna(row.get("init_state_id")) else f"episode={row.get('episode_id')}"
        )
        self.metadata.value = (
            f"<b>suite:</b> {html.escape(str(row['suite']))} · "
            f"<b>task:</b> {html.escape(str(row['task_name']))} · "
            f"<b>{html.escape(state_label)}</b>"
        )
        images = row["images"]
        self._load_image(images.get("agentview_rgb"), self.agent_image)
        has_wrist = self._load_image(images.get("wrist_rgb"), self.wrist_image)
        self.wrist_placeholder.value = "" if has_wrist else "<i>Not available for this environment</i>"

        usable = row.get("usable_for_slava")
        self.usable.value = "yes" if usable is True else "no" if usable is False else "pending"
        self.selected.value = bool(row.get("selected_for_v0", False))
        self.review_status.value = str(row.get("review_status") or "pending")
        self.exclusion_reasons.value = ", ".join(row.get("exclusion_reasons") or [])
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
        visibility_options = [("Unknown", "unknown"), ("Visible", "visible"), ("Not visible", "not_visible")]
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
                f"({html.escape(str(obj.get('kind', 'object')))})",
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
        self.df.at[idx, "selected_for_v0"] = self.selected.value
        self.df.at[idx, "review_status"] = self.review_status.value
        self.df.at[idx, "exclusion_reasons"] = [x.strip() for x in self.exclusion_reasons.value.split(",") if x.strip()]
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
