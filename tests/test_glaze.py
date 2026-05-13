from __future__ import annotations

from pathlib import Path
from typing import Sequence
import unittest

from jack_display.glaze import (
    GLAZEWM_PROCESS_NAME,
    GLAZEWM_WATCHER_PROCESS_NAME,
    CommandResult,
    GlazeController,
    GlazeState,
)


class FakeProcessTable:
    def __init__(self, names: list[str] | None = None) -> None:
        self.names = list(names or [])
        self.list_calls = 0

    def list(self) -> list[str]:
        self.list_calls += 1
        return list(self.names)

    def add(self, name: str) -> None:
        self.names.append(name.lower())

    def remove_all(self, name: str) -> int:
        before = len(self.names)
        self.names = [n for n in self.names if n != name.lower()]
        return before - len(self.names)


class ScriptedRunner:
    """Returns a queued :class:`CommandResult` for each invocation."""

    def __init__(self, results: list[CommandResult]) -> None:
        self.results = list(results)
        self.calls: list[tuple[tuple[str, ...], float]] = []

    def __call__(self, args: Sequence[str], timeout: float) -> CommandResult:
        self.calls.append((tuple(args), timeout))
        if not self.results:
            return CommandResult(0, "", "", False)
        return self.results.pop(0)


class RecordingSpawner:
    def __init__(self, on_spawn: callable | None = None) -> None:
        self.calls: list[tuple[str, ...]] = []
        self._on_spawn = on_spawn

    def __call__(self, args: Sequence[str]) -> None:
        self.calls.append(tuple(args))
        if self._on_spawn is not None:
            self._on_spawn()


class FakeSleeper:
    def __init__(self, on_sleep: callable | None = None) -> None:
        self.calls: list[float] = []
        self._on_sleep = on_sleep

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        if self._on_sleep is not None:
            self._on_sleep()


def _ok() -> CommandResult:
    return CommandResult(0, '{"success":true}', "", False)


def _failed() -> CommandResult:
    return CommandResult(1, "", "not connected", False)


def _timed_out() -> CommandResult:
    return CommandResult(-1, "", "timeout", True)


class GlazeControllerTests(unittest.TestCase):
    def _build(
        self,
        *,
        cli_exists: bool = True,
        process_table: FakeProcessTable | None = None,
        runner: ScriptedRunner | None = None,
        spawner: RecordingSpawner | None = None,
        terminator: callable | None = None,
        sleeper: FakeSleeper | None = None,
    ) -> tuple[GlazeController, FakeProcessTable, ScriptedRunner, RecordingSpawner, FakeSleeper]:
        process_table = process_table or FakeProcessTable()
        runner = runner or ScriptedRunner([])
        spawner = spawner or RecordingSpawner()
        sleeper = sleeper or FakeSleeper()
        cli_path = Path("Z:/fake/glazewm.exe") if cli_exists else Path("Z:/missing/glazewm.exe")

        class _StubPath(type(cli_path)):
            pass

        controller = GlazeController(
            cli_path=cli_path,
            config_path=Path("Z:/fake/config.yaml"),
            process_lister=process_table.list,
            command_runner=runner,
            spawner=spawner,
            process_terminator=terminator or process_table.remove_all,
            sleeper=sleeper,
            query_timeout_seconds=0.05,
            start_grace_seconds=0.5,
            stop_grace_seconds=0.5,
            responsive_poll_interval_seconds=0.05,
        )
        controller.is_installed = lambda: cli_exists  # type: ignore[assignment]
        return controller, process_table, runner, spawner, sleeper

    def test_state_reports_not_installed_when_cli_is_missing(self) -> None:
        controller, *_ = self._build(cli_exists=False)
        self.assertEqual(controller.state(), GlazeState.NOT_INSTALLED)

    def test_state_reports_off_when_no_process(self) -> None:
        controller, *_ = self._build()
        self.assertEqual(controller.state(), GlazeState.OFF)

    def test_state_reports_starting_when_only_watcher_is_running(self) -> None:
        process_table = FakeProcessTable([GLAZEWM_WATCHER_PROCESS_NAME])
        controller, *_ = self._build(process_table=process_table)
        self.assertEqual(controller.state(), GlazeState.STARTING)

    def test_state_reports_on_when_process_responds(self) -> None:
        process_table = FakeProcessTable([GLAZEWM_PROCESS_NAME])
        runner = ScriptedRunner([_ok()])
        controller, *_ = self._build(process_table=process_table, runner=runner)
        self.assertEqual(controller.state(), GlazeState.ON)

    def test_state_reports_unresponsive_when_process_does_not_respond(self) -> None:
        process_table = FakeProcessTable([GLAZEWM_PROCESS_NAME])
        runner = ScriptedRunner([_timed_out()])
        controller, *_ = self._build(process_table=process_table, runner=runner)
        self.assertEqual(controller.state(), GlazeState.UNRESPONSIVE)

    def test_state_invokes_process_lister_exactly_once(self) -> None:
        # The glazewm + glazewm-watcher checks share a single tasklist
        # snapshot per state() call so a one-off subprocess hiccup can't
        # make them disagree and flip the UI to OFF mid-poll.
        process_table = FakeProcessTable([GLAZEWM_PROCESS_NAME])
        runner = ScriptedRunner([_ok()])
        controller, table, *_ = self._build(
            process_table=process_table, runner=runner
        )
        controller.state()
        self.assertEqual(table.list_calls, 1)

    def test_state_invokes_process_lister_exactly_once_when_off(self) -> None:
        process_table = FakeProcessTable([])
        controller, table, *_ = self._build(process_table=process_table)
        self.assertEqual(controller.state(), GlazeState.OFF)
        self.assertEqual(table.list_calls, 1)

    def test_start_skips_when_already_running_and_responsive(self) -> None:
        process_table = FakeProcessTable([GLAZEWM_PROCESS_NAME])
        runner = ScriptedRunner([_ok(), _ok()])
        controller, _table, _runner, spawner, _sleeper = self._build(
            process_table=process_table, runner=runner
        )
        status = controller.start()
        self.assertEqual(status.state, GlazeState.ON)
        self.assertEqual(spawner.calls, [])

    def test_start_spawns_when_not_running(self) -> None:
        process_table = FakeProcessTable([])
        runner = ScriptedRunner([_failed(), _ok()])
        spawner = RecordingSpawner(on_spawn=lambda: process_table.add(GLAZEWM_PROCESS_NAME))
        controller, *_ = self._build(
            process_table=process_table, runner=runner, spawner=spawner
        )
        status = controller.start()
        self.assertEqual(status.state, GlazeState.ON)
        self.assertEqual(len(spawner.calls), 1)
        self.assertIn("start", spawner.calls[0])

    def test_start_terminates_orphan_then_spawns(self) -> None:
        process_table = FakeProcessTable([GLAZEWM_PROCESS_NAME])
        runner = ScriptedRunner([_timed_out(), _failed(), _ok()])
        spawner = RecordingSpawner(on_spawn=lambda: process_table.add(GLAZEWM_PROCESS_NAME))
        controller, _table, _runner, _spawner, _sleeper = self._build(
            process_table=process_table, runner=runner, spawner=spawner
        )
        status = controller.start()
        self.assertEqual(status.state, GlazeState.ON)
        self.assertEqual(len(spawner.calls), 1)

    def test_start_returns_unresponsive_when_ipc_never_comes_up(self) -> None:
        process_table = FakeProcessTable([])
        runner = ScriptedRunner(
            [_failed()] + [_failed()] * 30
        )
        spawner = RecordingSpawner(on_spawn=lambda: process_table.add(GLAZEWM_PROCESS_NAME))
        controller, *_ = self._build(
            process_table=process_table, runner=runner, spawner=spawner
        )
        status = controller.start()
        self.assertEqual(status.state, GlazeState.UNRESPONSIVE)

    def test_start_returns_off_when_process_dies_immediately(self) -> None:
        process_table = FakeProcessTable([])
        runner = ScriptedRunner([_failed()] + [_failed()] * 30)
        spawner = RecordingSpawner()
        controller, *_ = self._build(
            process_table=process_table, runner=runner, spawner=spawner
        )
        status = controller.start()
        self.assertEqual(status.state, GlazeState.OFF)
        self.assertIn("did not stay running", status.message)

    def test_stop_is_noop_when_not_running(self) -> None:
        controller, _table, _runner, _spawner, _sleeper = self._build()
        status = controller.stop()
        self.assertEqual(status.state, GlazeState.OFF)

    def test_stop_terminates_watcher_before_waiting_for_off(self) -> None:
        process_table = FakeProcessTable([GLAZEWM_PROCESS_NAME, GLAZEWM_WATCHER_PROCESS_NAME])
        ok_then_exit = ScriptedRunner([_ok(), CommandResult(0, "", "", False)])

        def on_sleep_remove() -> None:
            process_table.remove_all(GLAZEWM_PROCESS_NAME)

        sleeper = FakeSleeper(on_sleep=on_sleep_remove)
        controller, *_ = self._build(
            process_table=process_table,
            runner=ok_then_exit,
            sleeper=sleeper,
        )
        status = controller.stop()
        self.assertEqual(status.state, GlazeState.OFF)
        self.assertEqual(process_table.list(), [])

    def test_toggle_stops_when_only_watcher_is_running(self) -> None:
        process_table = FakeProcessTable([GLAZEWM_WATCHER_PROCESS_NAME])
        controller, *_ = self._build(process_table=process_table)
        status = controller.toggle()
        self.assertEqual(status.state, GlazeState.OFF)
        self.assertEqual(process_table.list(), [])

    def test_stop_uses_wm_exit_when_responsive(self) -> None:
        process_table = FakeProcessTable([GLAZEWM_PROCESS_NAME])
        ok_then_exit = ScriptedRunner([_ok(), CommandResult(0, "", "", False)])

        def on_sleep_remove() -> None:
            process_table.remove_all(GLAZEWM_PROCESS_NAME)

        sleeper = FakeSleeper(on_sleep=on_sleep_remove)
        controller, *_ = self._build(
            process_table=process_table, runner=ok_then_exit, sleeper=sleeper
        )
        status = controller.stop()
        self.assertEqual(status.state, GlazeState.OFF)
        executed = [call[0] for call in ok_then_exit.calls]
        self.assertTrue(any("wm-exit" in args for args in executed))

    def test_stop_falls_back_to_terminator_when_unresponsive(self) -> None:
        process_table = FakeProcessTable([GLAZEWM_PROCESS_NAME])
        runner = ScriptedRunner([_timed_out()])
        controller, *_ = self._build(process_table=process_table, runner=runner)
        status = controller.stop()
        self.assertEqual(status.state, GlazeState.OFF)
        self.assertEqual(process_table.list(), [])

    def test_toggle_starts_when_off(self) -> None:
        process_table = FakeProcessTable([])
        runner = ScriptedRunner([_failed(), _ok()])
        spawner = RecordingSpawner(on_spawn=lambda: process_table.add(GLAZEWM_PROCESS_NAME))
        controller, *_ = self._build(
            process_table=process_table, runner=runner, spawner=spawner
        )
        status = controller.toggle()
        self.assertEqual(status.state, GlazeState.ON)

    def test_toggle_stops_when_on(self) -> None:
        process_table = FakeProcessTable([GLAZEWM_PROCESS_NAME])
        ok_then_exit = ScriptedRunner([_ok(), _ok(), CommandResult(0, "", "", False)])

        def on_sleep_remove() -> None:
            process_table.remove_all(GLAZEWM_PROCESS_NAME)

        sleeper = FakeSleeper(on_sleep=on_sleep_remove)
        controller, *_ = self._build(
            process_table=process_table, runner=ok_then_exit, sleeper=sleeper
        )
        status = controller.toggle()
        self.assertEqual(status.state, GlazeState.OFF)


if __name__ == "__main__":
    unittest.main()
