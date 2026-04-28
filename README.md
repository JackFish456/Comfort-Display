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

The control window can stay open in the corner while you work. Closing or
minimizing it hides it in the Windows system tray; click the tray icon to bring
it back. Use the `Quit` button or `Ctrl+Alt+Q` to fully exit.

## Hotkeys

- `Ctrl+Alt+1`: move the active window to the left centered pane.
- `Ctrl+Alt+2`: move the active window to the right centered pane.
- `Ctrl+Alt+D`: move the two most recently observed eligible windows into both panes.
- `Ctrl+Alt+C`: move the active window to a centered reading pane.
- `Ctrl+Alt+A`: toggle Apple Float free movement.
- `Ctrl+Alt+T`: toggle the warm dim overlay.
- `Ctrl+Alt+Up`: increase overlay warmth/dimming.
- `Ctrl+Alt+Down`: decrease overlay warmth/dimming.
- `Ctrl+Alt+R`: reload `comfort_layout.json`.
- `Ctrl+Alt+Q`: quit.

## Modes

`Comfort Dual` creates two virtual-monitor panes on the target display. It only
arranges windows that are already on that same display, so it will not pull a
laptop-screen window onto the TV. After Comfort Dual is selected, manually moved
windows on that display snap back into the nearest pane unless Apple Float is on.
Clicking the `Comfort Dual` button opens a selector so you can choose the exact
left and right panel windows; the hotkey keeps using the recent-window shortcut.

`Apple Float` temporarily allows free-form window placement on the target
display. It does not add a visual overlay.

If Windows blocks click-through overlay behavior, the warm overlay can be
dismissed by clicking it or pressing `Escape`.

If Windows refuses to move a protected, elevated, or otherwise restricted window, the status line reports it as `blocked` and leaves the window alone.

## Configuration

Edit `comfort_layout.json` to tune margins, gap, and overlay strength. Press
`Ctrl+Alt+R` after editing to reload.

## Verify

```powershell
python -B -c "import ast, pathlib; files=list(pathlib.Path('.').rglob('*.py')); [ast.parse(p.read_text(encoding='utf-8'), filename=str(p)) for p in files]; print('parsed', len(files), 'python files')"
python -B -m unittest discover -s tests
```
