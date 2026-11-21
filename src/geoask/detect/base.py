"""Detector contract. Any model (a CFAR rule, a torchvision / Hugging Face / YOLO model wrapped by
SAHI, a GFM-based head) plugs in by implementing ``detect`` on one chip."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class Box:
    """Pixel box in the coordinates of the array handed to the detector (x right, y down)."""

    x0: float
    y0: float
    x1: float
    y1: float
    score: float
    label: str = "object"

    @property
    def area(self) -> float:
        return max(self.x1 - self.x0, 0) * max(self.y1 - self.y0, 0)

    def shifted(self, dx: float, dy: float) -> Box:
        return Box(self.x0 + dx, self.y0 + dy, self.x1 + dx, self.y1 + dy, self.score, self.label)


class Detector(Protocol):
    id: str
    labels: tuple[str, ...]
    min_object_px: int  # smallest object it can find, in pixels at its input resolution

    def detect(self, chip: dict[str, np.ndarray]) -> list[Box]:
        """``chip`` maps band names (e.g. "vv", "red") to 2-D arrays of the same shape."""
        ...
