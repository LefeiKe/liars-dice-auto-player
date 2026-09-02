# Liars Dice Auto Player

A Windows computer-vision and desktop-automation project for a liar's-dice mini-game interface.

The project uses local screen capture, OpenCV-based UI recognition, and Windows input automation to detect game states and execute configured actions.

## Project structure

```text
liars-dice-auto-player/
├── auto_player.py
├── calibrator.py
├── screen_capture.py
├── config_manager.py
├── selection_console.py
├── requirements.txt
├── text_templates/
└── recovered_exe/
    ├── game_vision_clicker_reconstructed.py
    ├── rules.json
    └── README.md
```

There are two related code lines in this repository:

- **`auto_player.py`** — the later GPT-assisted version of the project, kept as the main source.
- **`recovered_exe/`** — a reconstruction of an earlier packaged Windows executable, preserved separately so the two generations are not mixed together.

## Features

- Local screen capture with `mss`
- OpenCV template matching and color-based UI detection
- Detects bid, force-open, replay, and related UI states
- Automatically selects dice controls and corresponding actions
- Coordinates scale from a reference resolution to the selected game area
- Debug/status window with pause and resume support
- Windows-focused input handling with PyAutoGUI / PyDirectInput
- Recovered rule-based architecture from the packaged EXE

## Tech stack

- Python
- OpenCV
- MSS
- NumPy
- PyAutoGUI
- PyDirectInput
- Pillow
- Windows APIs via `ctypes`

## Requirements

- Windows
- Python 3.10+

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run the main version

```bash
python auto_player.py
```

The program asks you to select the game area before automation starts.

## Template assets

The main `auto_player.py` source expects the following template filenames:

```text
text_templates/
├── bid.png
├── force_open.png
├── play_again.png
└── start.png
```

The uploaded historical EXE was also inspected. It contains or references a different template set, including:

```text
confirm_button.png
force_open_button.png
force_open_button_new.png
play_again_button.png
play_button.png
rank_first.png
rank_second.png
```

Because the EXE is from a different generation of the project, its assets are being kept under the recovered-EXE branch rather than blindly renamed into the main version. The two sets are not assumed to be interchangeable.

## Recovered EXE

See `recovered_exe/README.md` for details.

The reconstructed source is intentionally named:

```text
game_vision_clicker_reconstructed.py
```

This makes clear that it is a readable reconstruction derived from the packaged executable's resources, rules, module structure, and bytecode-level information—not a claim of byte-for-byte recovery of the original source file.

## Current status

- Main Python source: recovered and organized
- Supporting Python modules: included
- Requirements and repository structure: included
- Historical EXE rules: recovered
- Historical EXE reconstruction: included
- Template assets: partially recovered; the EXE asset set and main-source asset set are not identical

## Disclaimer

This repository is published as a computer-vision / desktop-automation project. Use automation only where it is permitted by the software or service you interact with.
