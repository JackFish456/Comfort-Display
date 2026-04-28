"""Tkinter control app and hotkey orchestration."""

from __future__ import annotations

import ctypes
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from typing import Any

from . import __version__
from .layout import (
    DEFAULT_CONFIG,
    Rect,
    dual_panes,
    load_config,
    reading_pane,
)
from . import winapi


MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001

VK = {
    "1": 0x31,
    "2": 0x32,
    "A": 0x41,
    "C": 0x43,
    "D": 0x44,
    "Q": 0x51,
    "R": 0x52,
    "T": 0x54,
    "UP": 0x26,
    "DOWN": 0x28,
}

HOTKEYS = {
    1: ("Ctrl+Alt+1", VK["1"], "place_left"),
    2: ("Ctrl+Alt+2", VK["2"], "place_right"),
    3: ("Ctrl+Alt+D", VK["D"], "place_dual"),
    4: ("Ctrl+Alt+C", VK["C"], "place_reading"),
    5: ("Ctrl+Alt+A", VK["A"], "toggle_apple"),
    6: ("Ctrl+Alt+T", VK["T"], "toggle_overlay"),
    7: ("Ctrl+Alt+Up", VK["UP"], "overlay_up"),
    8: ("Ctrl+Alt+Down", VK["DOWN"], "overlay_down"),
    9: ("Ctrl+Alt+R", VK["R"], "reload_config"),
    10: ("Ctrl+Alt+Q", VK["Q"], "quit"),
}


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint32),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
    ]


user32 = ctypes.windll.user32


class ComfortWorkspaceApp:
    """Small control surface for comfort layouts and warm overlays."""

    def __init__(self, root: tk.Tk, config_path: Path) -> None:
        self.root = root
        self.config_path = config_path
        self.config: dict[str, Any] = DEFAULT_CONFIG
        self.work_area = winapi.get_work_area()
        self.apple_enabled = False
        self.overlay_enabled = False
        self.overlay_alpha = float(DEFAULT_CONFIG["overlay"]["alpha"])
        self.overlay: tk.Toplevel | None = None
        self.guide: tk.Toplevel | None = None
        self.hotkey_failures: list[str] = []
        self.last_active_hwnd: int | None = None
        self.active_history: list[int] = []

        self.status_var = tk.StringVar()
        self.mode_var = tk.StringVar()
        self.screen_var = tk.StringVar()
        self.overlay_var = tk.StringVar()
        self.overlay_scale_var = tk.DoubleVar(value=self.overlay_alpha)
        self.overlay_scale: ttk.Scale | None = None

        self.root.title("Jack Display Comfort Workspace")
        self.root.geometry("390x420")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        self.load_or_reload_config(startup=True)
        self.build_ui()
        self.register_hotkeys()
        self.refresh_labels("Ready")
        self.root.after(50, self.poll_hotkeys)
        self.root.after(100, self.observe_active_window)

    @property
    def active_dual_preset(self) -> dict[str, Any]:
        preset_name = str(self.config.get("active_preset", "comfort_dual"))
        return self.config["presets"].get(preset_name, self.config["presets"]["comfort_dual"])

    @property
    def reading_preset(self) -> dict[str, Any]:
        return self.config["presets"]["single_reading"]

    def build_ui(self) -> None:
        pad = {"padx": 14, "pady": 7}
        header = ttk.Label(
            self.root,
            text="Jack Display Comfort Workspace",
            font=("Segoe UI", 14, "bold"),
        )
        header.pack(pady=(14, 4))

        ttk.Label(self.root, textvariable=self.screen_var).pack()
        ttk.Label(self.root, textvariable=self.mode_var).pack()
        ttk.Label(self.root, textvariable=self.overlay_var).pack()

        frame = ttk.Frame(self.root)
        frame.pack(fill="x", pady=(10, 4))
        ttk.Button(frame, text="Left Pane", command=self.place_left).grid(row=0, column=0, **pad)
        ttk.Button(frame, text="Right Pane", command=self.place_right).grid(row=0, column=1, **pad)
        ttk.Button(frame, text="Comfort Dual", command=self.place_dual).grid(row=1, column=0, **pad)
        ttk.Button(frame, text="Reading Pane", command=self.place_reading).grid(row=1, column=1, **pad)
        ttk.Button(frame, text="Apple Float", command=self.toggle_apple).grid(row=2, column=0, **pad)
        ttk.Button(frame, text="Warm Overlay", command=self.toggle_overlay).grid(row=3, column=0, **pad)
        ttk.Button(frame, text="Reload Config", command=self.reload_config).grid(row=3, column=1, **pad)

        controls = ttk.Frame(self.root)
        controls.pack(fill="x", pady=(4, 8))
        ttk.Button(controls, text="-", width=3, command=self.overlay_down).grid(
            row=0,
            column=0,
            padx=(14, 6),
            pady=7,
        )
        self.overlay_scale = ttk.Scale(
            controls,
            from_=float(self.config["overlay"]["min_alpha"]),
            to=float(self.config["overlay"]["max_alpha"]),
            variable=self.overlay_scale_var,
            command=self.overlay_slider_changed,
            length=210,
        )
        self.overlay_scale.grid(row=0, column=1, padx=4, pady=7)
        ttk.Button(controls, text="+", width=3, command=self.overlay_up).grid(
            row=0,
            column=2,
            padx=(6, 14),
            pady=7,
        )
        ttk.Button(controls, text="Quit", command=self.quit).grid(row=1, column=0, columnspan=3, **pad)

        ttk.Separator(self.root).pack(fill="x", padx=14, pady=(4, 8))
        ttk.Label(
            self.root,
            text="Hotkeys: Ctrl+Alt+1/2/D/C/A/T/Up/Down/R/Q",
            wraplength=350,
        ).pack()
        ttk.Label(self.root, textvariable=self.status_var, wraplength=350).pack(pady=(8, 0))

    def load_or_reload_config(self, startup: bool = False) -> None:
        try:
            self.config = load_config(self.config_path)
            self.overlay_alpha = float(self.config["overlay"]["alpha"])
            self.overlay_scale_var.set(self.overlay_alpha)
            message = "Config loaded" if startup else "Config reloaded"
        except Exception as exc:
            self.config = DEFAULT_CONFIG
            self.overlay_alpha = float(DEFAULT_CONFIG["overlay"]["alpha"])
            self.overlay_scale_var.set(self.overlay_alpha)
            message = f"Using defaults; config issue: {exc}"
        if self.overlay_scale is not None:
            self.overlay_scale.configure(
                from_=float(self.config["overlay"]["min_alpha"]),
                to=float(self.config["overlay"]["max_alpha"]),
            )
        self.work_area = winapi.get_work_area()
        self.refresh_labels(message)
        if self.overlay_enabled:
            self.show_overlay()
        if self.apple_enabled:
            self.show_guide()

    def refresh_labels(self, status: str | None = None) -> None:
        self.screen_var.set(
            f"Work area: {self.work_area.width}x{self.work_area.height} "
            f"at {self.work_area.x},{self.work_area.y}"
        )
        mode = "Apple Float on" if self.apple_enabled else "Comfort Dual ready"
        self.mode_var.set(f"Mode: {mode}")
        overlay = "on" if self.overlay_enabled else "off"
        self.overlay_var.set(f"Warm overlay: {overlay} ({self.overlay_alpha:.2f})")
        if status:
            self.status_var.set(status)

    def register_hotkeys(self) -> None:
        self.hotkey_failures.clear()
        for hotkey_id, (label, vk, _) in HOTKEYS.items():
            ok = user32.RegisterHotKey(None, hotkey_id, MOD_CONTROL | MOD_ALT, vk)
            if not ok:
                self.hotkey_failures.append(label)
        if self.hotkey_failures:
            self.refresh_labels("Unavailable hotkeys: " + ", ".join(self.hotkey_failures))

    def unregister_hotkeys(self) -> None:
        for hotkey_id in HOTKEYS:
            user32.UnregisterHotKey(None, hotkey_id)

    def poll_hotkeys(self) -> None:
        msg = MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, WM_HOTKEY, WM_HOTKEY, PM_REMOVE):
            hotkey = HOTKEYS.get(int(msg.wParam))
            if hotkey:
                getattr(self, hotkey[2])()
        self.root.after(50, self.poll_hotkeys)

    def observe_active_window(self) -> None:
        hwnd = winapi.get_active_window()
        if hwnd:
            self.last_active_hwnd = hwnd
            self.remember_window(hwnd)
        self.root.after(100, self.observe_active_window)

    def remember_window(self, hwnd: int) -> None:
        self.active_history = [item for item in self.active_history if item != hwnd]
        self.active_history.insert(0, hwnd)
        del self.active_history[10:]

    def recent_windows(self, limit: int = 2) -> list[int]:
        recent: list[int] = []
        for hwnd in self.active_history:
            if winapi.is_eligible_window(hwnd) and hwnd not in recent:
                recent.append(hwnd)
            if len(recent) >= limit:
                return recent
        for hwnd in winapi.eligible_windows():
            if hwnd not in recent:
                recent.append(hwnd)
            if len(recent) >= limit:
                return recent
        return recent

    def dual_rects(self) -> tuple[Rect, Rect]:
        return dual_panes(self.work_area, self.active_dual_preset)

    def dual_rects_for(self, hwnd: int | None = None) -> tuple[Rect, Rect]:
        return dual_panes(self.work_area_for(hwnd), self.active_dual_preset)

    def reading_rect_for(self, hwnd: int | None = None) -> Rect:
        return reading_pane(self.work_area_for(hwnd), self.reading_preset)

    def work_area_for(self, hwnd: int | None = None) -> Rect:
        try:
            return winapi.get_window_work_area(hwnd)
        except Exception:
            return self.work_area

    def move_active_to(self, rect: Rect, label: str) -> None:
        hwnd = self.target_window()
        if not hwnd:
            self.refresh_labels(f"{label}: no eligible active window")
            return
        moved = winapi.move_window(hwnd, rect)
        title = winapi.describe_window(hwnd)
        self.refresh_labels(f"{label}: {'moved' if moved else 'blocked'} - {title}")

    def target_window(self) -> int | None:
        active = winapi.get_active_window()
        if active:
            self.remember_window(active)
            return active
        if self.last_active_hwnd and winapi.is_eligible_window(self.last_active_hwnd):
            return self.last_active_hwnd
        return None

    def place_left(self) -> None:
        hwnd = self.target_window()
        left, _ = self.dual_rects_for(hwnd)
        self.move_window_to(hwnd, left, "Left pane")

    def place_right(self) -> None:
        hwnd = self.target_window()
        _, right = self.dual_rects_for(hwnd)
        self.move_window_to(hwnd, right, "Right pane")

    def place_dual(self) -> None:
        windows = self.recent_windows(limit=2)
        area = self.work_area_for(windows[0] if windows else None)
        left, right = dual_panes(area, self.active_dual_preset)
        moved = 0
        for hwnd, rect in zip(windows, (left, right), strict=False):
            if winapi.move_window(hwnd, rect):
                moved += 1
        self.refresh_labels(f"Comfort Dual: moved {moved} window(s)")

    def place_reading(self) -> None:
        hwnd = self.target_window()
        rect = self.reading_rect_for(hwnd)
        self.move_window_to(hwnd, rect, "Reading pane")

    def move_window_to(self, hwnd: int | None, rect: Rect, label: str) -> None:
        if not hwnd:
            self.refresh_labels(f"{label}: no eligible active window")
            return
        moved = winapi.move_window(hwnd, rect)
        title = winapi.describe_window(hwnd)
        self.refresh_labels(f"{label}: {'moved' if moved else 'blocked'} - {title}")

    def toggle_apple(self) -> None:
        self.apple_enabled = not self.apple_enabled
        if self.apple_enabled:
            self.show_guide()
            self.refresh_labels("Apple Float on")
        else:
            self.hide_guide()
            self.refresh_labels("Apple Float off")

    def overlay_geometry(self, area: Rect | None = None) -> str:
        area = area or self.work_area_for(self.target_window())
        return (
            f"{area.width}x{area.height}"
            f"+{area.x}+{area.y}"
        )

    def show_overlay(self) -> None:
        area = self.work_area_for(self.target_window())
        if self.overlay is None or not self.overlay.winfo_exists():
            self.overlay = tk.Toplevel(self.root)
            self.overlay.overrideredirect(True)
            self.overlay.attributes("-topmost", True)
            self.overlay.configure(bg=str(self.config["overlay"]["color"]))
            self.overlay.bind("<Button-1>", lambda _event: self.toggle_overlay())
            self.overlay.bind("<Escape>", lambda _event: self.toggle_overlay())
        self.overlay.geometry(self.overlay_geometry(area))
        if self.overlay is not None:
            self.overlay.update_idletasks()
            if not winapi.set_click_through(self.overlay.winfo_id()):
                self.overlay.focus_force()
                self.refresh_labels("Overlay fallback: click it or press Escape to dismiss")
        self.overlay.attributes("-alpha", self.overlay_alpha)
        self.overlay.deiconify()

    def hide_overlay(self) -> None:
        if self.overlay is not None and self.overlay.winfo_exists():
            self.overlay.withdraw()

    def toggle_overlay(self) -> None:
        self.overlay_enabled = not self.overlay_enabled
        if self.overlay_enabled:
            self.show_overlay()
            self.refresh_labels("Warm overlay on")
        else:
            self.hide_overlay()
            self.refresh_labels("Warm overlay off")

    def overlay_up(self) -> None:
        overlay = self.config["overlay"]
        self.overlay_alpha = min(
            float(overlay["max_alpha"]),
            self.overlay_alpha + float(overlay["step"]),
        )
        self.overlay_scale_var.set(self.overlay_alpha)
        if self.overlay_enabled:
            self.show_overlay()
        self.refresh_labels("Warm overlay increased")

    def overlay_down(self) -> None:
        overlay = self.config["overlay"]
        self.overlay_alpha = max(
            float(overlay["min_alpha"]),
            self.overlay_alpha - float(overlay["step"]),
        )
        self.overlay_scale_var.set(self.overlay_alpha)
        if self.overlay_enabled:
            self.show_overlay()
        self.refresh_labels("Warm overlay decreased")

    def overlay_slider_changed(self, value: str) -> None:
        self.overlay_alpha = float(value)
        if self.overlay_enabled:
            self.show_overlay()
        self.refresh_labels("Warm overlay adjusted")

    def show_guide(self) -> None:
        area = self.work_area_for(self.target_window())
        if self.guide is not None and self.guide.winfo_exists():
            self.guide.destroy()

        self.guide = tk.Toplevel(self.root)
        self.guide.overrideredirect(True)
        self.guide.attributes("-topmost", True)
        self.guide.attributes("-alpha", float(self.config["apple_float"]["guide_alpha"]))
        self.guide.configure(bg="#101820")
        self.guide.geometry(self.overlay_geometry(area))
        canvas = tk.Canvas(
            self.guide,
            width=area.width,
            height=area.height,
            highlightthickness=0,
            bg="#101820",
        )
        canvas.pack(fill="both", expand=True)
        self.guide.bind("<Button-1>", lambda _event: self.toggle_apple())
        self.guide.bind("<Escape>", lambda _event: self.toggle_apple())
        canvas.bind("<Button-1>", lambda _event: self.toggle_apple())

        left, right = dual_panes(area, self.active_dual_preset)
        reading = reading_pane(area, self.reading_preset)
        for rect, label, color in (
            (left, "left", "#9be7ff"),
            (right, "right", "#9be7ff"),
            (reading, "reading", "#ffd28a"),
        ):
            canvas.create_rectangle(
                rect.x - area.x,
                rect.y - area.y,
                rect.right - area.x,
                rect.bottom - area.y,
                outline=color,
                width=4,
            )
            canvas.create_text(
                rect.x - area.x + 18,
                rect.y - area.y + 18,
                anchor="nw",
                text=label,
                fill=color,
                font=("Segoe UI", 18, "bold"),
            )

        self.guide.update_idletasks()
        if not winapi.set_click_through(self.guide.winfo_id()):
            self.guide.focus_force()
            self.refresh_labels("Guide fallback: click it or press Escape to dismiss")

    def hide_guide(self) -> None:
        if self.guide is not None and self.guide.winfo_exists():
            self.guide.destroy()
        self.guide = None

    def reload_config(self) -> None:
        self.load_or_reload_config(startup=False)

    def quit(self) -> None:
        self.unregister_hotkeys()
        self.hide_overlay()
        self.hide_guide()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    root.tk.call("tk", "scaling", 1.0)
    config_path = Path(__file__).resolve().parent.parent / "comfort_layout.json"
    app = ComfortWorkspaceApp(root, config_path)
    app.refresh_labels(f"Ready - v{__version__}")
    root.mainloop()


if __name__ == "__main__":
    main()
