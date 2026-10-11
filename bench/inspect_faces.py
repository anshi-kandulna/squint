import json
from pathlib import Path
import cv2

ROOT = Path(__file__).resolve().parent
labels = json.loads((ROOT / "data" / "labels.json").read_text())
res = json.loads((ROOT / "results" / "quick.json").read_text())

shown = 0
for name, lab in sorted(labels.items()):
    gt = [b for b in lab["boxes"] if b["label"] == "face"]
    if not gt or name not in res:
        continue
    det = [d for d in res[name]["dets"] if d["label"] == "face"]
    print(name)
    print("  GT :", [(b["x"], b["y"], b["w"], b["h"]) for b in gt])
    print("  DET:", [(d["x"], d["y"], d["w"], d["h"], round(d["confidence"], 2)) for d in det])
    img = cv2.imread(str(ROOT / "data" / name))
    for b in gt:
        cv2.rectangle(img, (b["x"], b["y"]), (b["x"] + b["w"], b["y"] + b["h"]), (0, 200, 0), 2)
    for d in det:
        cv2.rectangle(img, (d["x"], d["y"]), (d["x"] + d["w"], d["y"] + d["h"]), (0, 0, 255), 2)
    cv2.imwrite(str(ROOT / "results" / f"face_{name}"), img)
    shown += 1
    if shown == 4:
        break
print("overlays in bench/results/  (green = ground truth, red = detected)")