"""Tkinter control app and hotkey orchestration."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
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
WM_TRAYICON = 0x8001
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
PM_REMOVE = 0x0001
GWLP_WNDPROC = -4
NIM_ADD = 0x00000000
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
IDI_APPLICATION = 32512
TRAY_ICON_ID = 1
APP_BG = "#f1e9ff"
PANEL_BG = "#eadfff"
BUTTON_BG = "#ded0ff"
BUTTON_ACTIVE_BG = "#d2c0ff"
TEXT_FG = "#241b35"
SNAP_TOLERANCE = 16

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
shell32 = ctypes.windll.shell32


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
    ]


WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


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
        self.hotkey_failures: list[str] = []
        self.last_active_hwnd: int | None = None
        self.active_history: list[int] = []
        self.auto_snap_work_area: Rect | None = None
        self.auto_snapping_hwnd: int | None = None
        self.structured_windows: dict[int, Rect] = {}
        self.tray_added = False
        self.tray_hwnd: int | None = None
        self.tray_old_wndproc: int | None = None
        self.tray_wndproc: WNDPROC | None = None

        self.status_var = tk.StringVar()
        self.mode_var = tk.StringVar()
        self.screen_var = tk.StringVar()
        self.overlay_var = tk.StringVar()
        self.root.title("Jack Display Comfort Workspace")
        self.root.geometry("")
        self.root.configure(bg=APP_BG)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.root.bind("<Unmap>", self.hide_to_tray_on_minimize)

        self.load_or_reload_config(startup=True)
        self.build_ui()
        self.setup_tray_icon()
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
        style.map("TButton", background=[("active", BUTTON_ACTIVE_BG)])

    def build_ui(self) -> None:
        self.configure_styles()
        pad = {"padx": 6, "pady": 3}
        frame = ttk.Frame(self.root)
        frame.pack(padx=8, pady=8)
        ttk.Button(frame, text="Comfort Dual", command=self.open_dual_selector).grid(row=0, column=0, **pad)
        ttk.Button(frame, text="Reading Pane", command=self.place_reading).grid(row=0, column=1, **pad)
        ttk.Button(frame, text="Apple Float", command=self.toggle_apple).grid(row=1, column=0, **pad)
        ttk.Button(frame, text="Reload Config", command=self.reload_config).grid(row=1, column=1, **pad)
        ttk.Button(frame, text="Quit", command=self.quit).grid(row=2, column=0, columnspan=2, **pad)

    def setup_tray_icon(self) -> None:
        self.root.update_idletasks()
        hwnd = int(self.root.winfo_id())
        self.tray_hwnd = hwnd
        self.tray_wndproc = WNDPROC(self.tray_window_proc)

        if hasattr(user32, "SetWindowLongPtrW"):
            set_window_proc = user32.SetWindowLongPtrW
        else:
            set_window_proc = user32.SetWindowLongW
        set_window_proc.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        set_window_proc.restype = ctypes.c_void_p
        user32.CallWindowProcW.argtypes = [
            ctypes.c_void_p,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.CallWindowProcW.restype = ctypes.c_ssize_t
        user32.DefWindowProcW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.LoadIconW.restype = wintypes.HICON
        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
        shell32.Shell_NotifyIconW.restype = wintypes.BOOL

        self.tray_old_wndproc = int(
            set_window_proc(
                wintypes.HWND(hwnd),
                GWLP_WNDPROC,
                ctypes.cast(self.tray_wndproc, ctypes.c_void_p).value,
            )
            or 0
        )

        icon = user32.LoadIconW(None, IDI_APPLICATION)
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = wintypes.HWND(hwnd)
        data.uID = TRAY_ICON_ID
        data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        data.uCallbackMessage = WM_TRAYICON
        data.hIcon = icon
        data.szTip = "Jack Display Comfort Workspace"
        self.tray_added = bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data)))

    def tray_window_proc(
        self,
        hwnd: int,
        message: int,
        wparam: int,
        lparam: int,
    ) -> int:
        if message == WM_TRAYICON and int(wparam) == TRAY_ICON_ID:
            if int(lparam) in {WM_LBUTTONUP, WM_LBUTTONDBLCLK, WM_RBUTTONUP}:
                self.root.after(0, self.show_from_tray)
                return 0

        if self.tray_old_wndproc:
            return int(
                user32.CallWindowProcW(
                    ctypes.c_void_p(self.tray_old_wndproc),
                    wintypes.HWND(hwnd),
                    message,
                    wparam,
                    lparam,
                )
            )
        return int(user32.DefWindowProcW(wintypes.HWND(hwnd), message, wparam, lparam))

    def hide_to_tray_on_minimize(self, event: tk.Event) -> None:
        if event.widget is self.root and self.root.state() == "iconic":
            self.hide_to_tray()

    def hide_to_tray(self) -> None:
        if self.tray_added:
            self.root.withdraw()
        else:
            self.root.iconify()

    def show_from_tray(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.refresh_labels("Restored from tray")

    def remove_tray_icon(self) -> None:
        if not self.tray_added or self.tray_hwnd is None:
            return
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = wintypes.HWND(self.tray_hwnd)
        data.uID = TRAY_ICON_ID
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))
        self.tray_added = False

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
            self.snap_window_if_needed(hwnd)
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

    def snap_window_if_needed(self, hwnd: int) -> None:
        if self.apple_enabled or self.auto_snap_work_area is None:
            return
        if hwnd == self.auto_snapping_hwnd:
            return
        try:
            if winapi.get_window_work_area(hwnd) != self.auto_snap_work_area:
                return
            current = winapi.get_window_rect(hwnd)
        except Exception:
            return

        structured_rect = self.structured_windows.get(hwnd)
        if structured_rect is not None:
            if self.rects_close(current, structured_rect):
                return
            self.structured_windows.pop(hwnd, None)

        left, right = dual_panes(self.auto_snap_work_area, self.active_dual_preset)
        if self.rects_close(current, left) or self.rects_close(current, right):
            return

        target = self.nearest_pane(current, left, right)
        self.auto_snapping_hwnd = hwnd
        try:
            winapi.move_window(hwnd, target)
        finally:
            self.auto_snapping_hwnd = None

    def rects_close(self, first: Rect, second: Rect) -> bool:
        return (
            abs(first.x - second.x) <= SNAP_TOLERANCE
            and abs(first.y - second.y) <= SNAP_TOLERANCE
            and abs(first.width - second.width) <= SNAP_TOLERANCE
            and abs(first.height - second.height) <= SNAP_TOLERANCE
        )

    def nearest_pane(self, current: Rect, left: Rect, right: Rect) -> Rect:
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
            self.auto_snap_work_area = self.work_area_for(hwnd)
            self.structured_windows[hwnd] = left
        self.move_window_to(hwnd, left, "Left pane")

    def place_right(self) -> None:
        hwnd = self.target_window()
        _, right = self.dual_rects_for(hwnd)
        if hwnd:
            self.auto_snap_work_area = self.work_area_for(hwnd)
            self.structured_windows[hwnd] = right
        self.move_window_to(hwnd, right, "Right pane")

    def open_dual_selector(self) -> None:
        target = self.target_window()
        if not target:
            self.refresh_labels("Comfort Dual: no eligible target window")
            return

        area = self.work_area_for(target)
        windows = self.windows_on_work_area(area)
        labels = self.window_choice_labels(windows)
        if len(labels) < 2:
            self.place_dual()
            return

        selector = tk.Toplevel(self.root)
        selector.title("Choose Dual Panels")
        selector.configure(bg=APP_BG)
        selector.resizable(False, False)
        selector.transient(self.root)
        selector.attributes("-topmost", True)

        frame = ttk.Frame(selector)
        frame.pack(padx=10, pady=10)
        choices = list(labels.keys())
        defaults = self.recent_windows_on_work_area(area, limit=2)
        default_labels = [
            label
            for label, hwnd in labels.items()
            if hwnd in defaults
        ]

        ttk.Label(frame, text="Left").grid(row=0, column=0, sticky="w", padx=4, pady=(0, 2))
        left_var = tk.StringVar(value=default_labels[0] if default_labels else choices[0])
        left_box = ttk.Combobox(frame, textvariable=left_var, values=choices, state="readonly", width=42)
        left_box.grid(row=1, column=0, padx=4, pady=(0, 6))

        ttk.Label(frame, text="Right").grid(row=2, column=0, sticky="w", padx=4, pady=(0, 2))
        fallback_right = choices[1] if len(choices) > 1 else choices[0]
        right_var = tk.StringVar(value=default_labels[1] if len(default_labels) > 1 else fallback_right)
        right_box = ttk.Combobox(frame, textvariable=right_var, values=choices, state="readonly", width=42)
        right_box.grid(row=3, column=0, padx=4, pady=(0, 8))

        message_var = tk.StringVar()
        ttk.Label(frame, textvariable=message_var).grid(row=4, column=0, padx=4, pady=(0, 6))

        actions = ttk.Frame(frame)
        actions.grid(row=5, column=0)
        ttk.Button(
            actions,
            text="Apply",
            command=lambda: self.apply_dual_selection(
                selector,
                labels,
                left_var.get(),
                right_var.get(),
                area,
                message_var,
            ),
        ).grid(row=0, column=0, padx=4)
        ttk.Button(actions, text="Cancel", command=selector.destroy).grid(row=0, column=1, padx=4)
        left_box.focus_set()

    def apply_dual_selection(
        self,
        selector: tk.Toplevel,
        labels: dict[str, int],
        left_label: str,
        right_label: str,
        area: Rect,
        message_var: tk.StringVar,
    ) -> None:
        left_hwnd = labels.get(left_label)
        right_hwnd = labels.get(right_label)
        if not left_hwnd or not right_hwnd:
            message_var.set("Choose two windows.")
            return
        if left_hwnd == right_hwnd:
            message_var.set("Choose different windows.")
            return

        left_rect, right_rect = dual_panes(area, self.active_dual_preset)
        self.auto_snap_work_area = area
        moved = 0
        for hwnd, rect in ((left_hwnd, left_rect), (right_hwnd, right_rect)):
            if winapi.move_window(hwnd, rect):
                self.structured_windows[hwnd] = rect
                moved += 1
        selector.destroy()
        self.refresh_labels(f"Comfort Dual: moved {moved} selected window(s)")

    def place_dual(self) -> None:
        target = self.target_window()
        if not target:
            self.refresh_labels("Comfort Dual: no eligible target window")
            return

        area = self.work_area_for(target)
        self.auto_snap_work_area = area
        windows = self.recent_windows_on_work_area(area, limit=2)
        left, right = dual_panes(area, self.active_dual_preset)
        moved = 0
        for hwnd, rect in zip(windows, (left, right), strict=False):
            if winapi.move_window(hwnd, rect):
                self.structured_windows[hwnd] = rect
                moved += 1
        self.refresh_labels(f"Comfort Dual: moved {moved} window(s)")

    def place_reading(self) -> None:
        hwnd = self.target_window()
        rect = self.reading_rect_for(hwnd)
        if hwnd:
            self.auto_snap_work_area = self.work_area_for(hwnd)
            self.structured_windows[hwnd] = rect
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
            self.refresh_labels("Apple Float on")
        else:
            self.refresh_labels("Apple Float off")
            hwnd = self.target_window()
            if hwnd:
                self.snap_window_if_needed(hwnd)

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

    def quit(self) -> None:
        self.unregister_hotkeys()
        self.hide_overlay()
        self.remove_tray_icon()
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
