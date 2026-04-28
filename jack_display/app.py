"""Tkinter control app and hotkey orchestration."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import math
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
ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9
APP_TITLE = "Jack Display Comfort Workspace"
APP_USER_MODEL_ID = "JackDisplay.ComfortWorkspace"
APP_BG = "#f1e9ff"
PANEL_BG = "#eadfff"
BUTTON_BG = "#ded0ff"
BUTTON_ACTIVE_BG = "#d2c0ff"
TEXT_FG = "#241b35"
READING_ACTIVE_BG = "#c8b6ff"
SNAP_ACTIVE_BG = "#7a3fd1"
ACTIVE_TEXT_FG = "#ffffff"
PICKER_HOVER_BG = "#b991ff"
PICKER_SELECTED_BG = "#4b168f"
ICON_BG = "#4b168f"
ICON_ACCENT = "#f7c948"
ICON_MARK = "#ffffff"

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
    5: ("Ctrl+Alt+A", VK["A"], "toggle_snap_mode"),
    6: ("Ctrl+Alt+T", VK["T"], "toggle_overlay"),
    7: ("Ctrl+Alt+Up", VK["UP"], "overlay_up"),
    8: ("Ctrl+Alt+Down", VK["DOWN"], "overlay_down"),
    9: ("Ctrl+Alt+R", VK["R"], "undo_view"),
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
shell32 = ctypes.windll.shell32
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def configure_taskbar_app_id() -> None:
    try:
        shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
        shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def activate_existing_app_window() -> bool:
    found_hwnd: list[int] = []

    @EnumWindowsProc
    def collect(hwnd: int, _lparam: int) -> bool:
        length = user32.GetWindowTextLengthW(wintypes.HWND(hwnd))
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(wintypes.HWND(hwnd), buffer, length + 1)
        if buffer.value == APP_TITLE:
            found_hwnd.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(collect, 0)
    if not found_hwnd:
        return False

    hwnd = wintypes.HWND(found_hwnd[0])
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    return True


def claim_single_instance() -> int | None:
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    mutex = kernel32.CreateMutexW(None, True, "Local\\JackDisplayComfortWorkspace")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        activate_existing_app_window()
        if mutex:
            kernel32.CloseHandle(wintypes.HANDLE(mutex))
        return None
    return int(mutex) if mutex else 0


class ComfortWorkspaceApp:
    """Small control surface for comfort layouts and warm overlays."""

    def __init__(self, root: tk.Tk, config_path: Path) -> None:
        self.root = root
        self.config_path = config_path
        self.config: dict[str, Any] = DEFAULT_CONFIG
        self.work_area = winapi.get_work_area()
        self.snap_enabled = False
        self.snap_work_area: Rect | None = None
        self.snap_moving_hwnd: int | None = None
        self.overlay_enabled = False
        self.overlay_alpha = float(DEFAULT_CONFIG["overlay"]["alpha"])
        self.overlay: tk.Toplevel | None = None
        self.hotkey_failures: list[str] = []
        self.last_active_hwnd: int | None = None
        self.active_history: list[int] = []
        self.picker_active = False
        self.reading_origins: dict[int, Rect] = {}
        self.structured_windows: dict[int, Rect] = {}
        self.view_history: list[dict[int, Rect]] = []
        self.icon_images: list[tk.PhotoImage] = []

        self.status_var = tk.StringVar()
        self.mode_var = tk.StringVar()
        self.screen_var = tk.StringVar()
        self.overlay_var = tk.StringVar()
        self.reading_button: ttk.Button | None = None
        self.snap_button: ttk.Button | None = None
        self.root.title(APP_TITLE)
        self.root.geometry("")
        self.root.configure(bg=APP_BG)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

        self.load_or_reload_config(startup=True)
        self.apply_window_icon()
        self.build_ui()
        self.register_hotkeys()
        self.refresh_labels("Ready")
        self.refresh_button_states()
        self.root.after(50, self.poll_hotkeys)
        self.root.after(100, self.observe_active_window)

    @property
    def active_dual_preset(self) -> dict[str, Any]:
        preset_name = str(self.config.get("active_preset", "comfort_dual"))
        return self.config["presets"].get(preset_name, self.config["presets"]["comfort_dual"])

    @property
    def reading_preset(self) -> dict[str, Any]:
        return self.config["presets"]["single_reading"]

    def configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=APP_BG, foreground=TEXT_FG, font=("Segoe UI", 9))
        style.configure("TFrame", background=APP_BG)
        style.configure("TLabel", background=APP_BG, foreground=TEXT_FG)
        style.configure("TButton", background=BUTTON_BG, foreground=TEXT_FG, padding=(8, 4))
        style.configure("ReadingActive.TButton", background=READING_ACTIVE_BG, foreground=TEXT_FG, padding=(8, 4))
        style.configure("SnapActive.TButton", background=SNAP_ACTIVE_BG, foreground=ACTIVE_TEXT_FG, padding=(8, 4))
        style.map("TButton", background=[("active", BUTTON_ACTIVE_BG)])
        style.map("ReadingActive.TButton", background=[("active", BUTTON_ACTIVE_BG)])
        style.map("SnapActive.TButton", background=[("active", PICKER_SELECTED_BG)])

    def build_ui(self) -> None:
        self.configure_styles()
        pad = {"padx": 6, "pady": 3}
        frame = ttk.Frame(self.root)
        frame.pack(padx=8, pady=8)
        ttk.Button(frame, text="Comfort Dual", command=self.open_dual_selector).grid(row=0, column=0, **pad)
        self.reading_button = ttk.Button(frame, text="Reading Pane", command=self.place_reading)
        self.reading_button.grid(row=0, column=1, **pad)
        self.snap_button = ttk.Button(frame, text="Snap Mode", command=self.toggle_snap_mode)
        self.snap_button.grid(row=1, column=0, **pad)
        ttk.Button(frame, text="Undo View", command=self.undo_view).grid(row=1, column=1, **pad)
        ttk.Button(frame, text="Quit", command=self.quit).grid(row=2, column=0, columnspan=2, **pad)

    def refresh_button_states(self) -> None:
        if self.snap_button is not None:
            style = "SnapActive.TButton" if self.snap_enabled else "TButton"
            self.snap_button.configure(style=style)
        if self.reading_button is not None:
            style = "ReadingActive.TButton" if self.active_reading_window() else "TButton"
            self.reading_button.configure(style=style)

    def apply_window_icon(self) -> None:
        configure_taskbar_app_id()
        self.icon_images = [self.build_icon_image(64), self.build_icon_image(32)]
        try:
            self.root.iconphoto(True, *self.icon_images)
        except tk.TclError:
            pass

    def build_icon_image(self, size: int) -> tk.PhotoImage:
        image = tk.PhotoImage(width=size, height=size)

        def fill(color: str, gx: int, gy: int, gw: int, gh: int) -> None:
            x1 = max(0, round((gx / 16) * size))
            y1 = max(0, round((gy / 16) * size))
            x2 = min(size, round(((gx + gw) / 16) * size))
            y2 = min(size, round(((gy + gh) / 16) * size))
            if x2 > x1 and y2 > y1:
                image.put(color, to=(x1, y1, x2, y2))

        fill(ICON_BG, 0, 0, 16, 16)
        fill(ICON_ACCENT, 0, 0, 16, 2)
        fill(ICON_ACCENT, 0, 14, 16, 2)
        fill(ICON_ACCENT, 0, 0, 2, 16)
        fill(ICON_ACCENT, 14, 0, 2, 16)
        fill(ICON_MARK, 5, 4, 7, 2)
        fill(ICON_MARK, 8, 4, 2, 7)
        fill(ICON_MARK, 4, 9, 2, 3)
        fill(ICON_MARK, 5, 11, 5, 2)
        return image

    def load_or_reload_config(self, startup: bool = False) -> None:
        try:
            self.config = load_config(self.config_path)
            self.overlay_alpha = float(self.config["overlay"]["alpha"])
            message = "Config loaded" if startup else "Config reloaded"
        except Exception as exc:
            self.config = DEFAULT_CONFIG
            self.overlay_alpha = float(DEFAULT_CONFIG["overlay"]["alpha"])
            message = f"Using defaults; config issue: {exc}"
        self.work_area = winapi.get_work_area()
        self.refresh_labels(message)
        if self.overlay_enabled:
            self.show_overlay()

    def refresh_labels(self, status: str | None = None) -> None:
        self.screen_var.set(
            f"Work area: {self.work_area.width}x{self.work_area.height} "
            f"at {self.work_area.x},{self.work_area.y}"
        )
        mode = "Snap Mode on" if self.snap_enabled else "Comfort Dual ready"
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
            self.snap_active_window_if_needed(hwnd)
        self.refresh_button_states()
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

    def recent_windows_on_work_area(self, work_area: Rect, limit: int = 2) -> list[int]:
        recent: list[int] = []

        def add_if_same_monitor(hwnd: int) -> bool:
            if hwnd in recent or not winapi.is_eligible_window(hwnd):
                return False
            try:
                if winapi.get_window_work_area(hwnd) != work_area:
                    return False
            except Exception:
                return False
            recent.append(hwnd)
            return len(recent) >= limit

        for hwnd in self.active_history:
            if add_if_same_monitor(hwnd):
                return recent
        for hwnd in winapi.eligible_windows():
            if add_if_same_monitor(hwnd):
                return recent
        return recent

    def windows_on_work_area(self, work_area: Rect) -> list[int]:
        windows: list[int] = []
        for hwnd in self.active_history + winapi.eligible_windows():
            if hwnd in windows or not winapi.is_eligible_window(hwnd):
                continue
            try:
                if winapi.get_window_work_area(hwnd) == work_area:
                    windows.append(hwnd)
            except Exception:
                continue
        return windows

    def window_choice_labels(self, windows: list[int]) -> dict[str, int]:
        labels: dict[str, int] = {}
        for index, hwnd in enumerate(windows, start=1):
            title = winapi.describe_window(hwnd)
            if len(title) > 44:
                title = title[:41] + "..."
            labels[f"{index}. {title}"] = hwnd
        return labels

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

    def active_reading_window(self) -> bool:
        hwnd = self.target_window()
        if not hwnd or hwnd not in self.reading_origins:
            return False
        try:
            return self.rects_close(winapi.get_window_rect(hwnd), self.reading_rect_for(hwnd))
        except Exception:
            return False

    def remember_view(self, windows: list[int]) -> None:
        snapshot: dict[int, Rect] = {}
        for hwnd in windows:
            if hwnd in snapshot or not winapi.is_eligible_window(hwnd):
                continue
            try:
                snapshot[hwnd] = winapi.get_window_rect(hwnd)
            except Exception:
                continue
        if not snapshot:
            return
        self.view_history.append(snapshot)
        del self.view_history[:-20]

    def remember_view_snapshot(self, snapshot: dict[int, Rect]) -> None:
        clean_snapshot = {
            hwnd: rect
            for hwnd, rect in snapshot.items()
            if winapi.is_eligible_window(hwnd)
        }
        if not clean_snapshot:
            return
        self.view_history.append(clean_snapshot)
        del self.view_history[:-20]

    def snap_active_window_if_needed(self, hwnd: int) -> None:
        if not self.snap_enabled or self.picker_active or hwnd == self.snap_moving_hwnd:
            return
        try:
            area = winapi.get_window_work_area(hwnd)
            if self.snap_work_area is not None and area != self.snap_work_area:
                return
        except Exception:
            return
        self.snap_window_to_nearest_pane(hwnd)

    def snap_window_to_nearest_pane(self, hwnd: int) -> bool:
        try:
            area = winapi.get_window_work_area(hwnd)
            current = winapi.get_window_rect(hwnd)
        except Exception:
            return False

        self.snap_work_area = area
        left, right = dual_panes(area, self.active_dual_preset)
        target = self.snap_target_for_rect(current, left, right)
        if self.rects_close(current, target):
            return False

        self.remember_view_snapshot({hwnd: current})
        self.snap_moving_hwnd = hwnd
        try:
            return winapi.move_window(hwnd, target)
        finally:
            self.snap_moving_hwnd = None

    def snap_target_for_rect(self, current: Rect, left: Rect, right: Rect) -> Rect:
        if current.width > max(left.width, right.width) * 1.25:
            try:
                cursor_x, _ = winapi.get_cursor_position()
                return left if cursor_x < right.x else right
            except Exception:
                pass

        current_center = current.x + (current.width // 2)
        left_center = left.x + (left.width // 2)
        right_center = right.x + (right.width // 2)
        return left if abs(current_center - left_center) <= abs(current_center - right_center) else right

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
        if hwnd:
            self.remember_view([hwnd])
            self.snap_work_area = self.work_area_for(hwnd)
            self.structured_windows[hwnd] = left
        self.move_window_to(hwnd, left, "Left pane")

    def place_right(self) -> None:
        hwnd = self.target_window()
        _, right = self.dual_rects_for(hwnd)
        if hwnd:
            self.remember_view([hwnd])
            self.snap_work_area = self.work_area_for(hwnd)
            self.structured_windows[hwnd] = right
        self.move_window_to(hwnd, right, "Right pane")

    def open_dual_selector(self) -> None:
        target = self.target_window()
        if not target:
            self.refresh_labels("Comfort Dual: no eligible target window")
            return

        area = self.work_area_for(target)
        windows = self.windows_on_work_area(area)
        if len(windows) < 2:
            self.place_dual()
            return

        self.start_spatial_dual_picker(area, windows)

    def preview_rects(self, area: Rect, count: int) -> list[Rect]:
        columns = min(4, max(2, math.ceil(math.sqrt(count))))
        rows = math.ceil(count / columns)
        gap = 28
        tile_width = min(760, (area.width - (gap * (columns + 1))) // columns)
        tile_height = min(460, (area.height - (gap * (rows + 1))) // rows)
        total_width = (tile_width * columns) + (gap * (columns - 1))
        total_height = (tile_height * rows) + (gap * (rows - 1))
        start_x = area.x + max(gap, (area.width - total_width) // 2)
        start_y = area.y + max(gap, (area.height - total_height) // 2)

        rects: list[Rect] = []
        for index in range(count):
            row = index // columns
            column = index % columns
            rects.append(
                Rect(
                    start_x + (column * (tile_width + gap)),
                    start_y + (row * (tile_height + gap)),
                    tile_width,
                    tile_height,
                )
            )
        return rects

    def start_spatial_dual_picker(self, area: Rect, windows: list[int]) -> None:
        original_rects: dict[int, Rect] = {}
        badges: list[tk.Toplevel] = []
        borders: dict[int, list[tk.Toplevel]] = {}
        number_badges: dict[int, tk.Toplevel] = {}
        selected: list[int] = []
        previews = self.preview_rects(area, len(windows))
        self.picker_active = True

        def cleanup(restore_unselected: bool) -> None:
            self.root.unbind_all("<Escape>")
            for badge in badges:
                if badge.winfo_exists():
                    badge.destroy()
            if restore_unselected:
                for hwnd, rect in original_rects.items():
                    if hwnd not in selected:
                        winapi.move_window(hwnd, rect)
            self.picker_active = False

        def cancel() -> None:
            cleanup(restore_unselected=True)
            self.refresh_labels("Comfort Dual: picker cancelled")

        def set_border(hwnd: int, color: str) -> None:
            for border in borders.get(hwnd, []):
                if border.winfo_exists():
                    border.configure(bg=color)
                    border.deiconify()
                    border.lift()

        def hide_border(hwnd: int) -> None:
            if hwnd in selected:
                return
            for border in borders.get(hwnd, []):
                if border.winfo_exists():
                    border.withdraw()

        def show_number(hwnd: int, number: int) -> None:
            marker = number_badges.get(hwnd)
            if marker is None or not marker.winfo_exists():
                return
            for child in marker.winfo_children():
                child.configure(text=str(number))
            marker.deiconify()
            marker.lift()

        def choose(hwnd: int) -> None:
            if hwnd in selected:
                return
            selected.append(hwnd)
            set_border(hwnd, PICKER_SELECTED_BG)
            show_number(hwnd, len(selected))
            if len(selected) < 2:
                self.refresh_labels("Comfort Dual: choose right panel")
                return

            previous_view = {
                hwnd: original_rects[hwnd]
                for hwnd in selected
                if hwnd in original_rects
            }
            cleanup(restore_unselected=True)
            self.apply_dual_pair(selected[0], selected[1], area, previous_view)

        def bind_picker_events(widget: tk.Misc, hwnd: int) -> None:
            widget.bind("<Button-1>", lambda _event, selected_hwnd=hwnd: choose(selected_hwnd))
            widget.bind("<Enter>", lambda _event, selected_hwnd=hwnd: set_border(selected_hwnd, PICKER_HOVER_BG))
            widget.bind("<Leave>", lambda _event, selected_hwnd=hwnd: hide_border(selected_hwnd))

        for hwnd, rect in zip(windows, previews, strict=False):
            try:
                original_rects[hwnd] = winapi.get_window_rect(hwnd)
            except Exception:
                continue
            winapi.move_window(hwnd, rect)

            badge = tk.Toplevel(self.root)
            badge.overrideredirect(True)
            badge.attributes("-topmost", True)
            badge.attributes("-alpha", 0.01)
            badge.configure(bg=APP_BG)
            badge.geometry(f"{rect.width}x{rect.height}+{rect.x}+{rect.y}")
            badge.selected_hwnd = hwnd
            bind_picker_events(badge, hwnd)

            border_specs = (
                (rect.width, 7, rect.x, rect.y),
                (rect.width, 7, rect.x, rect.bottom - 7),
                (7, rect.height, rect.x, rect.y),
                (7, rect.height, rect.right - 7, rect.y),
            )
            pane_borders: list[tk.Toplevel] = []
            for width, height, x, y in border_specs:
                border = tk.Toplevel(self.root)
                border.overrideredirect(True)
                border.attributes("-topmost", True)
                border.configure(bg=PICKER_HOVER_BG)
                border.geometry(f"{width}x{height}+{x}+{y}")
                border.selected_hwnd = hwnd
                bind_picker_events(border, hwnd)
                border.withdraw()
                pane_borders.append(border)
                badges.append(border)
            borders[hwnd] = pane_borders

            label_badge = tk.Toplevel(self.root)
            label_badge.overrideredirect(True)
            label_badge.attributes("-topmost", True)
            label_badge.configure(bg=BUTTON_BG)
            label_badge.geometry(f"310x44+{rect.x + 12}+{rect.y + 12}")
            label_badge.selected_hwnd = hwnd
            bind_picker_events(label_badge, hwnd)
            title = winapi.describe_window(hwnd)
            if len(title) > 32:
                title = title[:29] + "..."
            label = tk.Label(
                label_badge,
                text=title,
                bg=BUTTON_BG,
                fg=TEXT_FG,
                font=("Segoe UI", 13, "bold"),
                padx=8,
                pady=4,
            )
            label.pack(fill="both", expand=True)
            bind_picker_events(label, hwnd)

            marker = tk.Toplevel(self.root)
            marker.overrideredirect(True)
            marker.attributes("-topmost", True)
            marker.configure(bg=PICKER_SELECTED_BG)
            marker.geometry(f"42x42+{rect.right - 54}+{rect.y + 12}")
            marker.selected_hwnd = hwnd
            bind_picker_events(marker, hwnd)
            marker_label = tk.Label(
                marker,
                text="",
                bg=PICKER_SELECTED_BG,
                fg="white",
                font=("Segoe UI", 19, "bold"),
            )
            marker_label.pack(fill="both", expand=True)
            bind_picker_events(marker_label, hwnd)
            marker.withdraw()
            number_badges[hwnd] = marker

            badges.append(badge)
            badges.append(label_badge)
            badges.append(marker)

        cancel_badge = tk.Toplevel(self.root)
        cancel_badge.overrideredirect(True)
        cancel_badge.attributes("-topmost", True)
        cancel_badge.configure(bg=APP_BG)
        cancel_badge.geometry(f"90x34+{area.x + area.width - 112}+{area.y + 22}")
        ttk.Button(cancel_badge, text="Cancel", command=cancel).pack(fill="both", expand=True)
        cancel_badge.bind("<Escape>", lambda _event: cancel())
        badges.append(cancel_badge)
        self.root.bind_all("<Escape>", lambda _event: cancel())
        cancel_badge.focus_force()
        self.refresh_labels("Comfort Dual: choose left panel")

    def apply_dual_pair(
        self,
        left_hwnd: int,
        right_hwnd: int,
        area: Rect,
        previous_view: dict[int, Rect] | None = None,
    ) -> None:
        left_rect, right_rect = dual_panes(area, self.active_dual_preset)
        self.snap_work_area = area
        self.structured_windows.clear()
        if previous_view is not None:
            self.remember_view_snapshot(previous_view)
        else:
            self.remember_view([left_hwnd, right_hwnd])
        moved = 0
        for hwnd, rect in ((left_hwnd, left_rect), (right_hwnd, right_rect)):
            if winapi.move_window(hwnd, rect):
                self.structured_windows[hwnd] = rect
                moved += 1
        self.refresh_labels(f"Comfort Dual: moved {moved} selected window(s)")

    def place_dual(self) -> None:
        target = self.target_window()
        if not target:
            self.refresh_labels("Comfort Dual: no eligible target window")
            return

        area = self.work_area_for(target)
        self.snap_work_area = area
        windows = self.recent_windows_on_work_area(area, limit=2)
        left, right = dual_panes(area, self.active_dual_preset)
        self.structured_windows.clear()
        self.remember_view(windows)
        moved = 0
        for hwnd, rect in zip(windows, (left, right), strict=False):
            if winapi.move_window(hwnd, rect):
                self.structured_windows[hwnd] = rect
                moved += 1
        self.refresh_labels(f"Comfort Dual: moved {moved} window(s)")

    def place_reading(self) -> None:
        hwnd = self.target_window()
        if not hwnd:
            self.refresh_labels("Reading pane: no eligible active window")
            return

        rect = self.reading_rect_for(hwnd)
        try:
            current = winapi.get_window_rect(hwnd)
        except Exception:
            current = None

        original = self.reading_origins.get(hwnd)
        if original is not None and current is not None and self.rects_close(current, rect):
            self.remember_view([hwnd])
            moved = winapi.move_window(hwnd, original)
            self.reading_origins.pop(hwnd, None)
            self.structured_windows.pop(hwnd, None)
            title = winapi.describe_window(hwnd)
            self.refresh_labels(f"Reading pane: {'restored' if moved else 'blocked'} - {title}")
            self.refresh_button_states()
            return

        if current is not None:
            self.remember_view_snapshot({hwnd: current})
        self.reading_origins[hwnd] = current
        self.structured_windows[hwnd] = rect
        self.move_window_to(hwnd, rect, "Reading pane")
        self.refresh_button_states()

    def rects_close(self, first: Rect, second: Rect) -> bool:
        return (
            abs(first.x - second.x) <= 16
            and abs(first.y - second.y) <= 16
            and abs(first.width - second.width) <= 16
            and abs(first.height - second.height) <= 16
        )

    def move_window_to(self, hwnd: int | None, rect: Rect, label: str) -> None:
        if not hwnd:
            self.refresh_labels(f"{label}: no eligible active window")
            return
        moved = winapi.move_window(hwnd, rect)
        title = winapi.describe_window(hwnd)
        self.refresh_labels(f"{label}: {'moved' if moved else 'blocked'} - {title}")

    def toggle_snap_mode(self) -> None:
        self.snap_enabled = not self.snap_enabled
        if not self.snap_enabled:
            self.refresh_labels("Snap Mode off")
            self.refresh_button_states()
            return

        hwnd = self.target_window()
        if not hwnd:
            self.refresh_labels("Snap Mode on: no eligible target window")
            self.refresh_button_states()
            return

        self.snap_work_area = self.work_area_for(hwnd)
        moved = self.snap_window_to_nearest_pane(hwnd)
        self.refresh_labels(f"Snap Mode on: {'snapped active window' if moved else 'ready'}")
        self.refresh_button_states()

    def overlay_geometry(self, area: Rect | None = None) -> str:
        area = area or self.work_area_for(self.target_window())
        return (
            f"{area.width}x{area.height}"
            f"+{area.x}+{area.y}"
        )

    def apply_overlay_alpha(self) -> None:
        if self.overlay is None or not self.overlay.winfo_exists():
            return
        self.overlay.attributes("-alpha", self.overlay_alpha)

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
        self.apply_overlay_alpha()
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
        if self.overlay_enabled:
            if self.overlay is None or not self.overlay.winfo_exists():
                self.show_overlay()
            else:
                self.apply_overlay_alpha()
        self.refresh_labels("Warm overlay increased")

    def overlay_down(self) -> None:
        overlay = self.config["overlay"]
        self.overlay_alpha = max(
            float(overlay["min_alpha"]),
            self.overlay_alpha - float(overlay["step"]),
        )
        if self.overlay_enabled:
            if self.overlay is None or not self.overlay.winfo_exists():
                self.show_overlay()
            else:
                self.apply_overlay_alpha()
        self.refresh_labels("Warm overlay decreased")

    def reload_config(self) -> None:
        self.load_or_reload_config(startup=False)

    def undo_view(self) -> None:
        if not self.view_history:
            self.refresh_labels("Undo View: no previous view")
            return

        snapshot = self.view_history.pop()
        moved = 0
        for hwnd, rect in snapshot.items():
            if winapi.move_window(hwnd, rect):
                self.structured_windows[hwnd] = rect
                moved += 1
        self.refresh_labels(f"Undo View: restored {moved} window(s)")

    def quit(self) -> None:
        self.unregister_hotkeys()
        self.hide_overlay()
        self.root.destroy()


def main() -> None:
    mutex = claim_single_instance()
    if mutex is None:
        return

    configure_taskbar_app_id()
    root = tk.Tk()
    root.tk.call("tk", "scaling", 1.0)
    config_path = Path(__file__).resolve().parent.parent / "comfort_layout.json"
    app = ComfortWorkspaceApp(root, config_path)
    app.refresh_labels(f"Ready - v{__version__}")
    try:
        root.mainloop()
    finally:
        if mutex:
            kernel32.CloseHandle(wintypes.HANDLE(mutex))


if __name__ == "__main__":
    main()
