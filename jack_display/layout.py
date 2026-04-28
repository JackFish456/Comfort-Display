"""Layout calculations for Jack Display Comfort Workspace."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "active_preset": "comfort_dual",
    "overlay": {
        "color": "#ffb05e",
        "alpha": 0.12,
        "step": 0.03,
        "min_alpha": 0.04,
        "max_alpha": 0.35,
    },
    "apple_float": {
        "guide_alpha": 0.22,
        "cycle_positions": ["left", "right", "reading", "float"],
    },
    "presets": {
        "comfort_dual": {
            "name": "Comfort Dual",
            "side_margin_ratio": 0.10,
            "top_margin_ratio": 0.08,
            "bottom_margin_ratio": 0.07,
            "gap": 24,
        },
        "tall_dual": {
            "name": "Tall Dual",
            "side_margin_ratio": 0.06,
            "top_margin_ratio": 0.04,
            "bottom_margin_ratio": 0.04,
            "gap": 20,
        },
        "single_reading": {
            "name": "Single Reading",
            "width_ratio": 0.60,
            "height_ratio": 0.82,
        },
    },
}


@dataclass(frozen=True)
class Rect:
    """Simple integer rectangle in Windows screen coordinates."""

    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge a user config onto defaults without requiring every key."""

    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: Path) -> dict[str, Any]:
    """Load JSON config, falling back to safe defaults if it is absent."""

    if not path.exists():
        return DEFAULT_CONFIG
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return deep_merge(DEFAULT_CONFIG, data)


def dual_panes(work_area: Rect, preset: dict[str, Any]) -> tuple[Rect, Rect]:
    """Return left and right centered panes for the given work area."""

    side = round(work_area.width * float(preset["side_margin_ratio"]))
    top = round(work_area.height * float(preset["top_margin_ratio"]))
    bottom = round(work_area.height * float(preset["bottom_margin_ratio"]))
    gap = int(preset["gap"])

    usable_width = max(200, work_area.width - (2 * side) - gap)
    pane_width = usable_width // 2
    pane_height = max(200, work_area.height - top - bottom)
    y = work_area.y + top
    left_x = work_area.x + side
    right_x = left_x + pane_width + gap

    left = Rect(left_x, y, pane_width, pane_height)
    right = Rect(right_x, y, pane_width, pane_height)
    return left, right


def reading_pane(work_area: Rect, preset: dict[str, Any]) -> Rect:
    """Return a centered single-window reading pane."""

    width = round(work_area.width * float(preset["width_ratio"]))
    height = round(work_area.height * float(preset["height_ratio"]))
    x = work_area.x + ((work_area.width - width) // 2)
    y = work_area.y + ((work_area.height - height) // 2)
    return Rect(x, y, width, height)


def float_pane(work_area: Rect) -> Rect:
    """Return a softer floating pane used by Apple Float cycling."""

    width = round(work_area.width * 0.56)
    height = round(work_area.height * 0.58)
    x = work_area.x + round(work_area.width * 0.22)
    y = work_area.y + round(work_area.height * 0.15)
    return Rect(x, y, width, height)


def named_position(
    name: str,
    work_area: Rect,
    dual_preset: dict[str, Any],
    reading_preset: dict[str, Any],
) -> Rect:
    """Resolve a named soft position into a rectangle."""

    left, right = dual_panes(work_area, dual_preset)
    normalized = name.strip().lower()
    if normalized == "left":
        return left
    if normalized == "right":
        return right
    if normalized == "reading":
        return reading_pane(work_area, reading_preset)
    if normalized == "float":
        return float_pane(work_area)
    raise ValueError(f"Unknown position: {name}")
