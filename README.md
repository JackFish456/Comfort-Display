# Jack Display Comfort Workspace

A small Windows 10 helper for making a close-up TV display feel more like a comfortable dual-monitor workspace.

It uses normal user-mode Windows APIs only. It does not change firewall rules, alter company security settings, inject into apps, or reconfigure DisplayFusion.

The app prefers `pywin32` when available and falls back to direct `ctypes` Win32 calls for the core window operations if those modules are missing.

## Run

Double-click `run_jack_display.pyw` for a no-console launcher, or `Launch Jack Display.vbs` (uses your per-user Python install under `%LOCALAPPDATA%`, then falls back to the `pyw` launcher).

You can pin File Explorer or the taskbar to `run_jack_display.pyw` for a one-click shortcut. Machine-specific `.lnk` files are not tracked here because they embed absolute profile paths (see `.gitignore`).

You can also run it from PowerShell:

```powershell
python .\run_jack_display.py
```

To start Jack Display automatically when you sign in to Windows and add a
clickable desktop shortcut, install the user shortcuts:

```powershell
.\install_startup_shortcut.ps1
```

To remove those shortcuts:

```powershell
.\remove_startup_shortcut.ps1
```

The control window can stay open in the corner while you work. It uses a simple
purple-and-gold pixel `J` icon so it is easier to spot on the Windows taskbar.
Close the window, use the `Quit` button, or press `Ctrl+Alt+Q` to fully exit.

## Hotkeys

- `Ctrl+Alt+1`: move the active window to the left centered pane.
- `Ctrl+Alt+2`: move the active window to the right centered pane.
- `Ctrl+Alt+D`: move the two most recently observed eligible windows into both panes.
- `Ctrl+Alt+C`: toggle the active window into or out of a centered reading pane.
- `Ctrl+Alt+A`: toggle Snap Mode.
- `Ctrl+Alt+T`: toggle the warm dim overlay.
- `Ctrl+Alt+Up`: increase overlay warmth/dimming.
- `Ctrl+Alt+Down`: decrease overlay warmth/dimming.
- `Ctrl+Alt+R`: undo the most recent view change.
- `Ctrl+Alt+Q`: quit.

## Modes

`Comfort Dual` creates two virtual-monitor panes on the target display. It only
arranges windows that are already on that same display, so it will not pull a
laptop-screen window onto the TV. Once panels are selected, you can still drag
or click windows normally; use `Undo View` or `Ctrl+Alt+R` to restore the most
recent previous view.
Clicking the `Comfort Dual` button temporarily shrinks the eligible windows on
that display into a picker grid. Click anywhere on the preview you want for the
left panel, then click anywhere on the preview you want for the right panel;
hovered previews get a violet outline, selected previews get a deep purple
outline with `1` or `2` in the corner, and `Escape` cancels the picker.
Unselected windows return to where they were. The hotkey keeps using the
recent-window shortcut.

`Snap Mode` is off by default so windows can be moved freely. Turn it on when
you want active windows on the target display to fit into the nearest left or
right pane. If a window is stretched or maximized across the display, Snap Mode
uses the cursor side to decide which pane should receive it. The `Snap Mode`
button turns deep purple while it is on.

`Reading Pane` stores the active window's current position before centering it.
Clicking `Reading Pane` again while that window is still in the reading position
restores it to where it started. The `Reading Pane` button shifts violet when
the active window is currently in reading position.

If Windows blocks click-through overlay behavior, the warm overlay can be
dismissed by clicking it or pressing `Escape`.

If Windows refuses to move a protected, elevated, or otherwise restricted window, the status line reports it as `blocked` and leaves the window alone.

## Configuration

Edit `comfort_layout.json` to tune margins, gap, and overlay strength.

## Verify

```powershell
python -B -c "import ast, pathlib; files=list(pathlib.Path('.').rglob('*.py')); [ast.parse(p.read_text(encoding='utf-8'), filename=str(p)) for p in files]; print('parsed', len(files), 'python files')"
python -B -m unittest discover -s tests
```
