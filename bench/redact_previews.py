"""Redact the screenshots that have a copy in bench/data/preview/, side by side with the original.

    uv run python bench/redact_previews.py
    uv run python bench/redact_previews.py --all          # every image in bench/data/
"""
import argparse
from pathlib import Path

import cv2
import numpy as np

from squint.local.pipeline import run

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "results" / "redacted"


def banner(img, text):
    pad = np.full((34, img.shape[1], 3), 245, dtype=np.uint8)
    cv2.putText(pad, text, (10, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (30, 30, 30), 1, cv2.LINE_AA)
    return np.vstack([pad, img])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="every image in bench/data, not just the previews")
    ap.add_argument("--ocr-scale", type=float, default=2.0)
    ap.add_argument("--face-tile", type=int, default=192)
    args = ap.parse_args()

    if args.all:
        names = sorted(p.name for p in DATA.glob("*.png"))
    else:
        names = sorted(p.name for p in (DATA / "preview").glob("*.png"))
    if not names:
        raise SystemExit("no images found. Run bench/generate.py with --preview N first.")

    OUT.mkdir(parents=True, exist_ok=True)
    for n in names:
        redacted_path = str(OUT / f"redacted_{n}")
        _, boxes, _, t = run(str(DATA / n), redacted_path,
                             ocr_scale=args.ocr_scale, face_tile=args.face_tile, hints=None)
        before, after = cv2.imread(str(DATA / n)), cv2.imread(redacted_path)
        both = np.hstack([banner(before, "original (stays on device)"),
                          banner(after, f"redacted ({len(boxes)} regions, {t['total'] * 1000:.0f} ms)")])
        cv2.imwrite(str(OUT / f"compare_{n}"), both)
        print(f"{n}: {len(boxes)} regions -> {sorted({b.label for b in boxes})}")

    print(f"\nwrote {len(names)} before/after images to {OUT}")


if __name__ == "__main__":
    main()