# EXE recovery notes

The uploaded Windows executable `逆水寒大乱斗助手(3).exe` is a PyInstaller package built with Python 3.13.

## Recovered structure

The package contains a main module named `game_vision_clicker.py` and an embedded `rules.json` configuration. A readable reconstruction is included as:

```text
game_vision_clicker_reconstructed.py
```

The reconstruction follows the recovered rule-driven architecture, module/function names, Windows-input behavior, and OpenCV/MSS workflow. It is not presented as a byte-for-byte copy of the original source.

## Template set

The EXE references the following UI assets:

- `confirm_button.png` (135×130)
- `force_open_button.png` (155×130)
- `force_open_button_new.png` (155×130)
- `play_again_button.png` (295×89)
- `play_button.png` (105×90)
- `rank_first.png` (896×424)
- `rank_second.png` (896×424)

Five of those assets were successfully extracted as standalone image files during recovery:

- `confirm_button.png`
- `force_open_button.png`
- `force_open_button_new.png`
- `play_again_button.png`
- `play_button.png`

The two rank templates are referenced by the recovered configuration, but their standalone image bytes are not currently present in the ChatGPT file archive used for this repository cleanup.

## Recovered rules

The included `rules.json` directly defines actions for:

- confirmation
- first-place replay
- second-place replay
- force-open
- play-card interaction

Each rule includes normalized detection regions, click points, match thresholds, priority, and re-arm timing.

## Relationship to the main source

This EXE is not an exact packaged copy of the current root `auto_player.py`.

The main source expects:

```text
bid.png
force_open.png
play_again.png
start.png
```

The historical EXE uses a different asset set. `force_open_button.png` and `play_again_button.png` are strong semantic matches for two of the later templates, but assets are intentionally not blindly renamed because the two versions use different detection logic and layouts.

Keeping this material in `recovered_exe/` preserves the project history without mixing incompatible generations of the code.
