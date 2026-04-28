# Jack Display Comfort Workspace

A small Windows 10 helper for making a close-up TV display feel more like a comfortable dual-monitor workspace.

It uses normal user-mode Windows APIs only. It does not change firewall rules, alter company security settings, inject into apps, or reconfigure DisplayFusion.

## Run

```powershell
python .\run_jack_display.py
```

The control window can stay open in the corner while you work.

## Hotkeys

- `Ctrl+Alt+1`: move the active window to the left centered pane.
- `Ctrl+Alt+2`: move the active window to the right centered pane.
- `Ctrl+Alt+D`: move the two most recent eligible windows into both panes.
- `Ctrl+Alt+C`: move the active window to a centered reading pane.
- `Ctrl+Alt+A`: toggle Apple Float visual guides.
- `Ctrl+Alt+Space`: cycle the active window through Apple Float positions.
- `Ctrl+Alt+T`: toggle the warm dim overlay.
- `Ctrl+Alt+Up`: increase overlay warmth/dimming.
- `Ctrl+Alt+Down`: decrease overlay warmth/dimming.
- `Ctrl+Alt+R`: reload `comfort_layout.json`.
- `Ctrl+Alt+Q`: quit.

## Modes

`Comfort Dual` creates two centered virtual-monitor panes while leaving surrounding space free for Explorer, browser tabs, or reference windows.

`Apple Float` adds subtle visual guides and lets you cycle the active window through soft positions. It only moves windows when you press a hotkey or button.

If Windows blocks click-through overlay behavior, the warm overlay or Apple Float guide can be dismissed by clicking it or pressing `Escape`.

## Configuration

Edit `comfort_layout.json` to tune margins, gap, overlay strength, and Apple Float cycle order. Press `Ctrl+Alt+R` after editing to reload.

## Verify

```powershell
python -B -c "import ast, pathlib; files=list(pathlib.Path('.').rglob('*.py')); [ast.parse(p.read_text(encoding='utf-8'), filename=str(p)) for p in files]; print('parsed', len(files), 'python files')"
python -B -m unittest discover -s tests
```
