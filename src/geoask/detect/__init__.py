"""Object detection on imagery of any size: a detector interface, SAHI-style slicing, and
built-in detectors that need no downloaded weights."""

from .base import Box, Detector
from .slicing import merge_boxes, slice_windows, sliced_detect

__all__ = ["Box", "Detector", "merge_boxes", "slice_windows", "sliced_detect"]
