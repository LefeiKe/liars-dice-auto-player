from __future__ import annotations

import cv2
import mss
import numpy as np


class ScreenCapture:
    """Small MSS wrapper used by the auto player during region selection."""

    def __init__(self) -> None:
        self._capture: mss.mss | None = None

    def __enter__(self) -> "ScreenCapture":
        self._capture = mss.mss()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._capture is not None:
            self._capture.close()
            self._capture = None

    def capture_all_monitors(self) -> tuple[np.ndarray, tuple[int, int]]:
        if self._capture is None:
            raise RuntimeError("ScreenCapture must be used as a context manager.")
        monitor = self._capture.monitors[0]
        shot = np.asarray(self._capture.grab(monitor))
        frame = cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR)
        return frame, (int(monitor["left"]), int(monitor["top"]))
