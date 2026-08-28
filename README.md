# Liars Dice Auto Player

A Windows computer-vision and desktop-automation project for a liar's-dice mini-game interface.

## Features

- Local screen capture with `mss`
- OpenCV template matching and color-based UI detection
- Detects bid, force-open, and replay states
- Automatically selects dice quantity / point controls and clicks the corresponding UI
- Scales coordinates from a reference resolution for different window sizes
- Debug/status window with pause/resume support
- Windows-focused input handling with PyAutoGUI and PyDirectInput

## Requirements

- Windows
- Python 3.10+

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run

```bash
python auto_player.py
```

The program asks you to select the game area before automation starts.

## Templates

The recovered source references UI templates stored in `text_templates/`:

```text
text_templates/
├── bid.png
├── force_open.png
├── play_again.png
└── start.png
```

Those template image files were not available in the archived project files I recovered, so they are not included in this initial upload.

## Tech stack

Python, OpenCV, MSS, NumPy, PyAutoGUI, PyDirectInput, Pillow.

## Disclaimer

This repository is published as a computer-vision / desktop-automation project. Use automation only where it is permitted by the software or service you interact with.
