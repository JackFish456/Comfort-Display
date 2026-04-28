"""Small Win32 wrapper layer for moving ordinary user windows.

The module prefers pywin32 when it is installed, but keeps a ctypes-only path
for locked-down machines where extra packages are not available.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Callable

from .layout import Rect

try:  # pragma: no cover - exercised by runtime smoke tests on this machine.
    import win32api
    import win32con
    import win32gui
    import win32process

    HAS_PYWIN32 = True
except ImportError:  # pragma: no cover - fallback depends on local environment.
    win32api = None
    win32con = None
    win32gui = None
    win32process = None
    HAS_PYWIN32 = False


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

GWL_EXSTYLE = -20
MONITOR_DEFAULTTOPRIMARY = 1
MONITOR_DEFAULTTONEAREST = 2
SW_RESTORE = 9
SWP_NOZORDER = 0x0004
SWP_NOOWNERZORDER = 0x0200
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

user32 = ctypes.windll.user32


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def get_work_area() -> Rect:
    """Return the primary monitor work area, excluding the taskbar."""

    if HAS_PYWIN32:
        monitor = win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY)
        return monitor_work_area(monitor)

    monitor = user32.MonitorFromPoint(
        wintypes.POINT(0, 0),
        MONITOR_DEFAULTTOPRIMARY,
    )
    return monitor_work_area(monitor)


def get_window_work_area(hwnd: int | None) -> Rect:
    """Return the work area for a window, or the primary work area."""

    if HAS_PYWIN32:
        if hwnd and win32gui.IsWindow(hwnd):
            monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
            return monitor_work_area(monitor)
        return get_work_area()

    if hwnd and user32.IsWindow(wintypes.HWND(hwnd)):
        monitor = user32.MonitorFromWindow(wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST)
        return monitor_work_area(monitor)
    return get_work_area()


def monitor_work_area(monitor: int) -> Rect:
    """Return a monitor work area from a Win32 monitor handle."""

    if HAS_PYWIN32:
        info = win32api.GetMonitorInfo(monitor)
        left, top, right, bottom = info["Work"]
        return Rect(left, top, right - left, bottom - top)

    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(wintypes.HMONITOR(monitor), ctypes.byref(info)):
        raise OSError("GetMonitorInfoW failed")
    rect = info.rcWork
    return Rect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


def window_title(hwnd: int) -> str:
    try:
        if HAS_PYWIN32:
            return win32gui.GetWindowText(hwnd).strip()

        length = user32.GetWindowTextLengthW(wintypes.HWND(hwnd))
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(wintypes.HWND(hwnd), buffer, length + 1)
        return buffer.value.strip()
    except Exception:
        return ""


def window_class(hwnd: int) -> str:
    try:
        if HAS_PYWIN32:
            return win32gui.GetClassName(hwnd)

        buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(wintypes.HWND(hwnd), buffer, len(buffer))
        return buffer.value
    except Exception:
        return ""


def window_pid(hwnd: int) -> int:
    try:
        if HAS_PYWIN32:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return int(pid)

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        return int(pid.value)
    except Exception:
        return -1


def is_window(hwnd: int) -> bool:
    if HAS_PYWIN32:
        return bool(win32gui.IsWindow(hwnd))
    return bool(user32.IsWindow(wintypes.HWND(hwnd)))


def is_visible(hwnd: int) -> bool:
    if HAS_PYWIN32:
        return bool(win32gui.IsWindowVisible(hwnd))
    return bool(user32.IsWindowVisible(wintypes.HWND(hwnd)))


def is_minimized(hwnd: int) -> bool:
    if HAS_PYWIN32:
        return bool(win32gui.IsIconic(hwnd))
    return bool(user32.IsIconic(wintypes.HWND(hwnd)))


def get_ex_style(hwnd: int) -> int:
    if HAS_PYWIN32:
        return int(win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE))

    if hasattr(user32, "GetWindowLongPtrW"):
        return int(user32.GetWindowLongPtrW(wintypes.HWND(hwnd), GWL_EXSTYLE))
    return int(user32.GetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE))


def set_ex_style(hwnd: int, style: int) -> None:
    if HAS_PYWIN32:
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style)
        return

    if hasattr(user32, "SetWindowLongPtrW"):
        user32.SetWindowLongPtrW(wintypes.HWND(hwnd), GWL_EXSTYLE, style)
    else:
        user32.SetWindowLongW(wintypes.HWND(hwnd), GWL_EXSTYLE, style)


def is_eligible_window(hwnd: int) -> bool:
    """Return whether a window is a normal movable app window."""

    if not hwnd or not is_window(hwnd):
        return False
    if window_pid(hwnd) == os.getpid():
        return False
    if not is_visible(hwnd) or is_minimized(hwnd):
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
        ex_style = get_ex_style(hwnd)
    except Exception:
        return False
    if ex_style & WS_EX_TOOLWINDOW:
        return False

    return True


def get_active_window() -> int | None:
    if HAS_PYWIN32:
        hwnd = win32gui.GetForegroundWindow()
    else:
        hwnd = int(user32.GetForegroundWindow())
    return hwnd if is_eligible_window(hwnd) else None


def eligible_windows(limit: int | None = None) -> list[int]:
    """Return eligible top-level windows in z-order."""

    windows: list[int] = []

    if HAS_PYWIN32:
        def collect_pywin32(hwnd: int, _: object) -> bool:
            if is_eligible_window(hwnd):
                windows.append(hwnd)
            return limit is None or len(windows) < limit

        win32gui.EnumWindows(collect_pywin32, None)
        return windows

    @EnumWindowsProc
    def collect_ctypes(hwnd: int, _: int) -> bool:
        if is_eligible_window(int(hwnd)):
            windows.append(int(hwnd))
        return bool(limit is None or len(windows) < limit)

    user32.EnumWindows(collect_ctypes, 0)
    return windows


def move_window(hwnd: int, rect: Rect) -> bool:
    """Restore and move a window, returning whether Windows accepted it."""

    if not is_eligible_window(hwnd):
        return False
    try:
        if HAS_PYWIN32:
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

        user32.ShowWindow(wintypes.HWND(hwnd), SW_RESTORE)
        return bool(
            user32.SetWindowPos(
                wintypes.HWND(hwnd),
                None,
                rect.x,
                rect.y,
                rect.width,
                rect.height,
                SWP_NOZORDER | SWP_NOOWNERZORDER,
            )
        )
    except Exception:
        return False


def set_click_through(hwnd: int) -> bool:
    """Make a Tk overlay click-through when the OS permits it."""

    try:
        style = get_ex_style(hwnd)
        style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
        set_ex_style(hwnd, style)
        return True
    except Exception:
        return False


def describe_window(hwnd: int | None) -> str:
    if not hwnd:
        return "No eligible active window"
    title = window_title(hwnd)
    return title if title else f"Window {hwnd}"


def for_two_recent(callback: Callable[[int, Rect], bool], left: Rect, right: Rect) -> int:
    """Apply a callback to the first two eligible windows in z-order."""

    moved = 0
    for hwnd, rect in zip(eligible_windows(limit=2), (left, right), strict=False):
        if callback(hwnd, rect):
            moved += 1
    return moved
