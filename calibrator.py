from __future__ import annotations

import cv2
import numpy as np


class RegionSelector:
    """Interactive OpenCV rectangle selector for choosing the game area."""

    def __init__(
        self,
        image: np.ndarray,
        origin: tuple[int, int],
        title: str = "Select region",
    ) -> None:
        self.image = image
        self.origin = origin
        self.title = title

    def show(self) -> dict[str, int] | None:
        x, y, w, h = cv2.selectROI(
            self.title,
            self.image,
            showCrosshair=True,
            fromCenter=False,
        )
        cv2.destroyWindow(self.title)
        if w <= 0 or h <= 0:
            return None
        return {
            "left": int(self.origin[0] + x),
            "top": int(self.origin[1] + y),
            "width": int(w),
            "height": int(h),
        }
