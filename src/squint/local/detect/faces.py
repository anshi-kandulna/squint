"""MediaPipe face detection."""
import urllib.request
from pathlib import Path

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

from squint.schemas import Box

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_detector/"
             "blaze_face_short_range/float16/1/blaze_face_short_range.tflite")
MODEL_PATH = Path(__file__).resolve().parents[4] / "models" / "blaze_face_short_range.tflite"

_detector = None


def _get_detector(min_conf: float):
    # The detector is created once, so the first min_conf wins for the whole run.
    global _detector
    if _detector is None:
        if not MODEL_PATH.exists():
            MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            print("downloading face model ->", MODEL_PATH)
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        opts = vision.FaceDetectorOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(MODEL_PATH)),
            min_detection_confidence=min_conf,
        )
        _detector = vision.FaceDetector.create_from_options(opts)
    return _detector


def _contained(a: Box, b: Box, thr: float = 0.6) -> bool:
    """True if the overlap covers most of the smaller box (handles partial faces cut by tile edges)."""
    x1, y1 = max(a.x, b.x), max(a.y, b.y)
    x2, y2 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    return inter / max(1, min(a.w * a.h, b.w * b.h)) > thr


def _starts(length: int, tile: int, stride: int) -> list[int]:
    if length <= tile:
        return [0]
    s = list(range(0, length - tile + 1, stride))
    if s[-1] != length - tile:
        s.append(length - tile)   # make sure the far edge is covered
    return s


def detect_faces(image_path: str, min_conf: float = 0.6,
                 tile: int = 256, stride: int = 128) -> list[Box]:
    bgr = cv2.imread(image_path)
    h, w = bgr.shape[:2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    det = _get_detector(min_conf)

    found: list[Box] = []
    for y0 in _starts(h, tile, stride):
        for x0 in _starts(w, tile, stride):
            crop = np.ascontiguousarray(rgb[y0:y0 + tile, x0:x0 + tile])
            res = det.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=crop))
            for d in res.detections:
                bb = d.bounding_box
                found.append(Box(
                    x=x0 + max(0, bb.origin_x), y=y0 + max(0, bb.origin_y),
                    w=bb.width, h=bb.height, label="face",
                    confidence=float(d.categories[0].score), source="face"))

    # Merge duplicates from overlapping tiles, after ALL tiles have been scanned.
    found.sort(key=lambda b: b.confidence, reverse=True)
    kept: list[Box] = []
    for b in found:
        for i, k in enumerate(kept):
            if _contained(b, k):
                x1, y1 = min(b.x, k.x), min(b.y, k.y)
                x2, y2 = max(b.x + b.w, k.x + k.w), max(b.y + b.h, k.y + k.h)
                kept[i] = Box(x=x1, y=y1, w=x2 - x1, h=y2 - y1, label="face",
                              confidence=max(b.confidence, k.confidence), source="face")
                break
        else:
            kept.append(b)
    return kept