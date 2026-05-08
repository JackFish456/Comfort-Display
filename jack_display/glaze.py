"""GlazeWM controller for Jack Display Comfort Workspace.

A small, dependency-injectable wrapper around the GlazeWM CLI so the Tk app
owns Glaze on/off as a single, explicit user action instead of relying on
fragile background autostart scripts.

The controller has no background daemon, no global hotkeys, and no shell
launchers. The Tk app polls ``state()`` from its existing ``after`` cadence
and calls ``start()`` / ``stop()`` / ``toggle()`` from button handlers.

All side-effecting operations (process listing, subprocess execution,
sleeping, spawning the WM) are exposed as injectable callables so the
controller is fully unit-testable without GlazeWM installed.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Sequence


DEFAULT_GLAZEWM_CLI = (
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "Programs"
    / "glzr.io"
    / "GlazeWM"
    / "PFiles64"
    / "glzr.io"
    / "GlazeWM"
    / "cli"
    / "glazewm.exe"
)
DEFAULT_GLAZEWM_CONFIG = (
    Path(os.environ.get("USERPROFILE", "")) / ".glzr" / "glazewm" / "config.yaml"
)
GLAZEWM_PROCESS_NAME = "glazewm.exe"

DEFAULT_QUERY_TIMEOUT_SECONDS = 2.0
DEFAULT_START_GRACE_SECONDS = 6.0
DEFAULT_STOP_GRACE_SECONDS = 4.0
RESPONSIVE_POLL_INTERVAL_SECONDS = 0.25

# Hide the transient cmd window when shelling out from a Tk app.
_CREATE_NO_WINDOW = 0x08000000


class GlazeState(Enum):
    """High-level GlazeWM state observed by the controller."""

    OFF = "off"
    STARTING = "starting"
    ON = "on"
    UNRESPONSIVE = "unresponsive"
    NOT_INSTALLED = "not_installed"


@dataclass(frozen=True)
class CommandResult:
    """Result of running a single subprocess invocation."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool


@dataclass(frozen=True)
class GlazeStatus:
    """Outcome of a controller action that the UI can surface to the user."""

    state: GlazeState
    message: str


ProcessLister = Callable[[], list[str]]
CommandRunner = Callable[[Sequence[str], float], CommandResult]
Spawner = Callable[[Sequence[str]], None]
Sleeper = Callable[[float], None]
ProcessTerminator = Callable[[str], int]


def _default_process_lister() -> list[str]:
    """Return the lowercased image names of currently running processes."""

    try:
        completed = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=4.0,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []

    names: list[str] = []
    for line in completed.stdout.splitlines():
        if not line.startswith('"'):
            continue
        end = line.find('"', 1)
        if end > 1:
            names.append(line[1:end].lower())
    return names


def _default_command_runner(args: Sequence[str], timeout: float) -> CommandResult:
    try:
        completed = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=_CREATE_NO_WINDOW,
        )
        return CommandResult(completed.returncode, completed.stdout, completed.stderr, False)
    except subprocess.TimeoutExpired:
        return CommandResult(-1, "", "timeout", True)
    except OSError as exc:
        return CommandResult(-1, "", str(exc), False)


def _default_spawner(args: Sequence[str]) -> None:
    """Spawn a long-lived process detached from the parent so it survives Jack Display exiting."""

    creationflags = _CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    subprocess.Popen(
        list(args),
        creationflags=creationflags,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _default_process_terminator(image_name: str) -> int:
    """Terminate every running instance of ``image_name`` and return the count terminated."""

    try:
        completed = subprocess.run(
            ["taskkill", "/F", "/IM", image_name],
            capture_output=True,
            text=True,
            timeout=4.0,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (subprocess.TimeoutExpired, OSError):
        return 0

    if completed.returncode != 0:
        return 0
    return completed.stdout.count("SUCCESS:")


class GlazeController:
    """Owns the on/off lifecycle of GlazeWM as a single, explicit operation."""

    def __init__(
        self,
        cli_path: Path | None = None,
        config_path: Path | None = None,
        *,
        process_lister: ProcessLister | None = None,
        command_runner: CommandRunner | None = None,
        spawner: Spawner | None = None,
        process_terminator: ProcessTerminator | None = None,
        sleeper: Sleeper | None = None,
        query_timeout_seconds: float = DEFAULT_QUERY_TIMEOUT_SECONDS,
        start_grace_seconds: float = DEFAULT_START_GRACE_SECONDS,
        stop_grace_seconds: float = DEFAULT_STOP_GRACE_SECONDS,
        responsive_poll_interval_seconds: float = RESPONSIVE_POLL_INTERVAL_SECONDS,
    ) -> None:
        self.cli_path = Path(cli_path) if cli_path is not None else DEFAULT_GLAZEWM_CLI
        self.config_path = Path(config_path) if config_path is not None else DEFAULT_GLAZEWM_CONFIG
        self._process_lister = process_lister or _default_process_lister
        self._command_runner = command_runner or _default_command_runner
        self._spawner = spawner or _default_spawner
        self._process_terminator = process_terminator or _default_process_terminator
        self._sleeper = sleeper or time.sleep
        self.query_timeout_seconds = float(query_timeout_seconds)
        self.start_grace_seconds = float(start_grace_seconds)
        self.stop_grace_seconds = float(stop_grace_seconds)
        self.responsive_poll_interval_seconds = float(responsive_poll_interval_seconds)

    def is_installed(self) -> bool:
        return self.cli_path.exists()

    def is_process_running(self) -> bool:
        return GLAZEWM_PROCESS_NAME in self._process_lister()

    def is_responsive(self) -> bool:
        result = self._command_runner(
            [str(self.cli_path), "query", "paused"],
            self.query_timeout_seconds,
        )
        return result.returncode == 0 and not result.timed_out

    def state(self) -> GlazeState:
        if not self.is_installed():
            return GlazeState.NOT_INSTALLED
        running = self.is_process_running()
        if not running:
            return GlazeState.OFF
        if self.is_responsive():
            return GlazeState.ON
        return GlazeState.UNRESPONSIVE

    def start(self) -> GlazeStatus:
        if not self.is_installed():
            return GlazeStatus(GlazeState.NOT_INSTALLED, f"GlazeWM CLI not found: {self.cli_path}")

        if self.is_process_running() and not self.is_responsive():
            terminated = self._process_terminator(GLAZEWM_PROCESS_NAME)
            if terminated == 0 and self.is_process_running():
                return GlazeStatus(
                    GlazeState.UNRESPONSIVE,
                    "GlazeWM process is wedged and could not be terminated",
                )
            self._sleeper(self.responsive_poll_interval_seconds)

        if self.is_responsive():
            return GlazeStatus(GlazeState.ON, "GlazeWM already running")

        self._spawner([str(self.cli_path), "start", "--config", str(self.config_path)])

        if self._wait_for_responsive(self.start_grace_seconds):
            return GlazeStatus(GlazeState.ON, "GlazeWM started")

        if self.is_process_running():
            return GlazeStatus(
                GlazeState.UNRESPONSIVE,
                f"GlazeWM started but is not responding to IPC after {self.start_grace_seconds:g}s",
            )
        return GlazeStatus(
            GlazeState.OFF,
            f"GlazeWM did not stay running. Check {self.config_path}",
        )

    def stop(self) -> GlazeStatus:
        if not self.is_process_running():
            return GlazeStatus(GlazeState.OFF, "GlazeWM was not running")

        if self.is_responsive():
            self._command_runner(
                [str(self.cli_path), "command", "wm-exit"],
                self.query_timeout_seconds,
            )
            if self._wait_for_stopped(self.stop_grace_seconds):
                return GlazeStatus(GlazeState.OFF, "GlazeWM exited")

        terminated = self._process_terminator(GLAZEWM_PROCESS_NAME)
        if self._wait_for_stopped(self.stop_grace_seconds):
            descriptor = "terminated" if terminated > 0 else "exited"
            return GlazeStatus(GlazeState.OFF, f"GlazeWM {descriptor}")

        return GlazeStatus(
            GlazeState.UNRESPONSIVE,
            "GlazeWM is still running and refused to stop",
        )

    def toggle(self) -> GlazeStatus:
        current = self.state()
        if current is GlazeState.ON or current is GlazeState.UNRESPONSIVE:
            return self.stop()
        return self.start()

    def _wait_for_responsive(self, timeout_seconds: float) -> bool:
        return self._poll_until(timeout_seconds, self.is_responsive)

    def _wait_for_stopped(self, timeout_seconds: float) -> bool:
        return self._poll_until(timeout_seconds, lambda: not self.is_process_running())

    def _poll_until(self, timeout_seconds: float, predicate: Callable[[], bool]) -> bool:
        if predicate():
            return True
        elapsed = 0.0
        interval = max(0.01, self.responsive_poll_interval_seconds)
        while elapsed < timeout_seconds:
            self._sleeper(interval)
            elapsed += interval
            if predicate():
                return True
        return False
