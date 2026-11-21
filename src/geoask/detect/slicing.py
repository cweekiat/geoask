"""SAHI-style sliced inference (Akyon et al., "Slicing Aided Hyper Inference", ICIP 2022).

Small objects in large images are found by running the detector on overlapping slices, shifting
each slice's boxes back to full-image coordinates, and merging duplicates where slices overlap.
This module re-implements that loop for any :class:`Detector` (numpy only). If the ``sahi``
package is installed, :func:`sahi_detector` also wraps any detector SAHI supports (Ultralytics,
torchvision, Hugging Face, MMDetection…) as a GeoAsk ``Detector``.
"""

from __future__ import annotations

import numpy as np

from .base import Box, Detector


def slice_windows(h: int, w: int, size: int = 512, overlap: float = 0.2) -> list[tuple[int, int, int, int]]:
    """(y0, x0, y1, x1) slices covering an h × w image; the last row/column is pulled back so
    every slice is full size (when the image is at least that big)."""
    step = max(1, int(size * (1 - overlap)))

    def starts(n: int) -> list[int]:
        if n <= size:
            return [0]
        s = list(range(0, n - size, step))
        return s + [n - size]

    return [(y, x, min(y + size, h), min(x + size, w)) for y in starts(h) for x in starts(w)]


def _iou_ios(a: Box, b: Box) -> tuple[float, float]:
    ix = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
    iy = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
    inter = ix * iy
    union = a.area + b.area - inter
    smaller = min(a.area, b.area)
    return (inter / union if union else 0.0, inter / smaller if smaller else 0.0)


def merge_boxes(boxes: list[Box], match: float = 0.5, metric: str = "ios") -> list[Box]:
    """Greedy non-maximum *merging* (SAHI's default "GREEDYNMM"): the highest-scoring box absorbs
    every same-label box overlapping it by ≥ ``match`` (intersection over the smaller box by
    default, so a ship cut in two by a slice edge becomes one box again)."""
    out: list[Box] = []
    used = [False] * len(boxes)
    order = sorted(range(len(boxes)), key=lambda i: -boxes[i].score)
    for oi, i in enumerate(order):
        if used[i]:
            continue
        keep = boxes[i]
        used[i] = True
        for j in order[oi + 1:]:
            if used[j] or boxes[j].label != keep.label:
                continue
            iou, ios = _iou_ios(keep, boxes[j])
            if (ios if metric == "ios" else iou) >= match:
                b = boxes[j]
                keep = Box(min(keep.x0, b.x0), min(keep.y0, b.y0), max(keep.x1, b.x1),
                           max(keep.y1, b.y1), keep.score, keep.label)
                used[j] = True
        out.append(keep)
    return out


def sliced_detect(image: dict[str, np.ndarray], detector: Detector, size: int = 512,
                  overlap: float = 0.2, full_image: bool = False, match: float = 0.5) -> list[Box]:
    """Run ``detector`` on overlapping slices of ``image`` and merge. ``full_image`` also runs
    it once on the whole image (SAHI's "standard prediction"), which helps with large objects."""
    h, w = next(iter(image.values())).shape
    boxes: list[Box] = []
    for y0, x0, y1, x1 in slice_windows(h, w, size, overlap):
        chip = {k: v[y0:y1, x0:x1] for k, v in image.items()}
        boxes += [b.shifted(x0, y0) for b in detector.detect(chip)]
    if full_image and (h > size or w > size):
        boxes += detector.detect(image)
    return merge_boxes(boxes, match)


def sahi_detector(model_type: str, model_path: str, bands: tuple[str, str, str] = ("red", "green", "blue"),
                  confidence: float = 0.3, device: str = "cpu", stretch: float = 0.25) -> Detector:
    """Wrap any SAHI-supported model (``pip install sahi`` plus its framework) as a Detector.

    Imagery is reflectance, so the three ``bands`` are stretched to 8-bit RGB (0–``stretch``)
    the way those models were trained. Example: ``sahi_detector("ultralytics", "yolo11n.pt")``.
    Note each model's own licence (e.g. Ultralytics models are AGPL-3.0).
    """
    try:
        from sahi import AutoDetectionModel
    except ImportError as e:  # optional dependency
        raise ImportError("pip install sahi (and the model's framework) to use SAHI models") from e
    model = AutoDetectionModel.from_pretrained(model_type=model_type, model_path=model_path,
                                               confidence_threshold=confidence, device=device)

    class _Sahi:
        id = f"sahi:{model_type}:{model_path}"
        labels = tuple(str(v) for v in (getattr(model, "category_mapping", None) or {}).values())
        min_object_px = 8

        def detect(self, chip: dict[str, np.ndarray]) -> list[Box]:
            rgb = np.stack([np.clip(np.nan_to_num(chip[b]) / stretch, 0, 1) for b in bands], -1)
            model.perform_inference((rgb * 255).astype(np.uint8))
            model.convert_original_predictions()
            return [Box(*p.bbox.to_xyxy(), float(p.score.value), p.category.name)
                    for p in model.object_prediction_list]

    return _Sahi()
