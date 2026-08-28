# EXE recovery notes

The uploaded Windows executable `逆水寒大乱斗助手(3).exe` is a PyInstaller package built with Python 3.13.

The executable contains a main module named `game_vision_clicker.py`, a `rules.json` file, and these embedded PNG assets:

- `confirm_button.png` (135×130)
- `force_open_button.png` (155×130)
- `force_open_button_new.png` (155×130)
- `play_again_button.png` (295×89)
- `play_button.png` (105×90)
- `rank_first.png` (896×424)
- `rank_second.png` (896×424)

The embedded rules directly use `confirm_button.png`, `rank_first.png`, `rank_second.png`, `force_open_button.png`, and `play_button.png`.

Important: this executable is not an exact packaged copy of the current `auto_player.py` source in this repository. The current source expects `bid.png`, `force_open.png`, `play_again.png`, and `start.png`. The EXE contains strong candidates for `force_open.png` and `play_again.png`, but no exact `bid.png` or `start.png` asset was found, so files are not blindly renamed.

The recovered `rules.json` is included in this folder for reference.
