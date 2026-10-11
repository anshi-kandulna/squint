import sys
import time
from squint.schemas import Box
from squint.local.capture import capture_page
from squint.local.detect.ocr import run_ocr
from squint.local.detect.patterns import find_pii
from squint.local.detect.faces import detect_faces
from squint.local.redact import redact


def _mostly_inside(a: Box, b: Box, thr: float = 0.5) -> bool:
    x1, y1 = max(a.x, b.x), max(a.y, b.y)
    x2, y2 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    return inter / max(1, a.w * a.h) > thr


def merge_hints(detected: list[Box], hints: list[Box]) -> list[Box]:
    """DOM boxes win: drop pixel detections that fall inside one, then add the DOM boxes."""
    kept = [d for d in detected if not any(_mostly_inside(d, h) for h in hints)]
    return kept + hints


def run(image_path: str, out_path: str = "redacted.png",
        ocr_scale: float = 2.0, hints: list[Box] | None = None):
    t = {}
    t0 = time.perf_counter()
    words = run_ocr(image_path, scale=ocr_scale);   t["ocr"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    pii = find_pii(words);                          t["regex"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    faces = detect_faces(image_path);               t["faces"] = time.perf_counter() - t0
    boxes = pii + faces
    if hints:
        boxes = merge_hints(boxes, hints)
    t0 = time.perf_counter()
    out, public = redact(image_path, boxes, out_path); t["redact"] = time.perf_counter() - t0
    t["total"] = sum(t.values())
    return out, boxes, public, t


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "shot.png"
    url = sys.argv[2] if len(sys.argv) > 2 else None   # pass a URL to use DOM hints
    hints = None
    if url:
        path, hints = capture_page(url, path)
    out, boxes, public, t = run(path, hints=hints)
    for i, b in enumerate(boxes, 1):
        print(f"[{i}] {b.label:8} {b.source:6} {b.confidence:.2f}  ({b.x},{b.y},{b.w},{b.h})")
    print({k: f"{v*1000:.0f}ms" for k, v in t.items()})
    print("wrote", out)