"""Small Win32 wrapper layer for moving ordinary user windows."""

from __future__ import annotations

import os
from typing import Callable

import win32api
import win32con
import win32gui
import win32process

from .layout import Rect


SKIP_CLASSES = {
    "Button",
    "Progman",
    "Shell_TrayWnd",
    "WorkerW",
    "DV2ControlHost",
    "MsgrIMEWindowClass",
}

SKIP_TITLE_PARTS = {
    "displayfusion",
    "program manager",
    "jack display comfort workspace",
}


def get_work_area() -> Rect:
    """Return the primary monitor work area, excluding the taskbar."""

    monitor = win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY)
    return monitor_work_area(monitor)


def get_window_work_area(hwnd: int | None) -> Rect:
    """Return the work area for a window, or the primary work area."""

    if hwnd and win32gui.IsWindow(hwnd):
        monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        return monitor_work_area(monitor)
    return get_work_area()


def monitor_work_area(monitor: int) -> Rect:
    """Return a monitor work area from a Win32 monitor handle."""

    info = win32api.GetMonitorInfo(monitor)
    left, top, right, bottom = info["Work"]
    return Rect(left, top, right - left, bottom - top)


def window_title(hwnd: int) -> str:
    try:
        return win32gui.GetWindowText(hwnd).strip()
    except Exception:
        return ""


def window_class(hwnd: int) -> str:
    try:
        return win32gui.GetClassName(hwnd)
    except Exception:
        return ""


def window_pid(hwnd: int) -> int:
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return int(pid)
    except Exception:
        return -1


def is_eligible_window(hwnd: int) -> bool:
    """Return whether a window is a normal movable app window."""

    if not hwnd or not win32gui.IsWindow(hwnd):
        return False
    if window_pid(hwnd) == os.getpid():
        return False
    if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
        return False

    title = window_title(hwnd)
    if not title:
        return False

    class_name = window_class(hwnd)
    if class_name in SKIP_CLASSES:
        return False

    title_lower = title.lower()
    if any(part in title_lower for part in SKIP_TITLE_PARTS):
        return False

    try:
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
    except Exception:
        return False
    if ex_style & win32con.WS_EX_TOOLWINDOW:
        return False

    return True


def get_active_window() -> int | None:
    hwnd = win32gui.GetForegroundWindow()
    return hwnd if is_eligible_window(hwnd) else None


def eligible_windows(limit: int | None = None) -> list[int]:
    """Return eligible top-level windows in z-order."""

    windows: list[int] = []

    def collect(hwnd: int, _: object) -> bool:
        if is_eligible_window(hwnd):
            windows.append(hwnd)
        return limit is None or len(windows) < limit

    win32gui.EnumWindows(collect, None)
    return windows


def move_window(hwnd: int, rect: Rect) -> bool:
    """Restore and move a window, returning whether Windows accepted it."""

    if not is_eligible_window(hwnd):
        return False
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetWindowPos(
            hwnd,
            None,
            rect.x,
            rect.y,
            rect.width,
            rect.height,
            win32con.SWP_NOZORDER | win32con.SWP_NOOWNERZORDER,
        )
        return True
    except Exception:
        return False


def set_click_through(hwnd: int) -> bool:
    """Make a Tk overlay click-through when the OS permits it."""

    try:
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        style |= (
            win32con.WS_EX_LAYERED
            | win32con.WS_EX_TRANSPARENT
            | win32con.WS_EX_TOOLWINDOW
        )
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style)
        return True
    except Exception:
        return False


def describe_window(hwnd: int | None) -> str:
    if not hwnd:
        return "No eligible active window"
    title = window_title(hwnd)
    return title if title else f"Window {hwnd}"


def for_two_recent(callback: Callable[[int, Rect], bool], left: Rect, right: Rect) -> int:
    """Apply a callback to the two most recent eligible windows."""

    moved = 0
    for hwnd, rect in zip(eligible_windows(limit=2), (left, right), strict=False):
        if callback(hwnd, rect):
            moved += 1
    return moved
