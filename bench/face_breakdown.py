"""Face recall and redaction coverage by photo size, from saved eval results.

    uv run python bench/face_breakdown.py tile256 tile192
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from metrics import covered_frac, match

ROOT = Path(__file__).resolve().parent
labels = json.loads((ROOT / "data" / "labels.json").read_text())

for tag in sys.argv[1:]:
    res = json.loads((ROOT / "results" / f"{tag}.json").read_text())
    rows = defaultdict(lambda: dict(n=0, found=0, cov=0.0))
    for name, r in res.items():
        gt = [b for b in labels[name]["boxes"] if b["label"] == "face"]
        if not gt:
            continue
        _, used_g, _ = match(gt, r["dets"])
        for gi, g in enumerate(gt):
            row = rows[g["w"]]
            row["n"] += 1
            row["found"] += gi in used_g
            row["cov"] += covered_frac(g, r["padded"])
    print(f"\n{tag}")
    print(f"{'photo px':>9} {'n':>3} {'found':>6} {'mean area covered':>18}")
    for size in sorted(rows):
        v = rows[size]
        print(f"{size:>9} {v['n']:>3} {v['found'] / v['n'] * 100:5.0f}% {v['cov'] / v['n'] * 100:17.0f}%")