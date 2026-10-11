"""Run the pixel-only pipeline over bench/data and score it.

    uv run python bench/run_eval.py --tag baseline
    uv run python bench/run_eval.py --tag scale1 --ocr-scale 1.0
    uv run python bench/run_eval.py --tag tile128 --face-tile 128
"""
import argparse
import json
from pathlib import Path

from metrics import evaluate, print_report, timing_summary
from squint.local.pipeline import run

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RESULTS = ROOT / "results"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="baseline")
    ap.add_argument("--ocr-scale", type=float, default=2.0)
    ap.add_argument("--face-tile", type=int, default=192)
    ap.add_argument("--limit", type=int, default=0, help="only the first N images (quick test)")
    args = ap.parse_args()

    labels = json.loads((DATA / "labels.json").read_text())
    names = sorted(labels)[: args.limit or None]
    labels = {n: labels[n] for n in names}
    RESULTS.mkdir(exist_ok=True)
    tmp = str(RESULTS / "_tmp_redacted.png")

    # warm-up: loads models, not timed
    run(str(DATA / names[0]), tmp, ocr_scale=args.ocr_scale, face_tile=args.face_tile)

    results = {}
    for i, n in enumerate(names, 1):
        out, boxes, public, t = run(str(DATA / n), tmp, ocr_scale=args.ocr_scale,
                                    face_tile=args.face_tile, hints=None)
        results[n] = dict(
            dets=[dict(label=b.label, confidence=b.confidence, source=b.source,
                       x=b.x, y=b.y, w=b.w, h=b.h) for b in boxes],
            padded=[dict(label=p.label, x=p.x, y=p.y, w=p.w, h=p.h) for p in public],
            timing=t)
        if i % 20 == 0 or i == len(names):
            print(f"  {i}/{len(names)}")

    (RESULTS / f"{args.tag}.json").write_text(json.dumps(results))
    print_report(evaluate(labels, results), timing_summary(results),
                 title=f"{args.tag} (ocr_scale={args.ocr_scale}, face_tile={args.face_tile}, "
                       f"{len(names)} images)")


if __name__ == "__main__":
    main()