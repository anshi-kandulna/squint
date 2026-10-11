"""Results tables + charts from saved eval runs.

    uv run python bench/report.py
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from metrics import evaluate, timing_summary

ROOT = Path(__file__).resolve().parent
RES = ROOT / "results"
labels = json.loads((ROOT / "data" / "labels.json").read_text())
PATTERN = ["email", "phone", "card", "aadhaar", "address"]


def load(tag):
    return json.loads((RES / f"{tag}.json").read_text())


def macro(summary, key, types=PATTERN):
    vals = [summary["per_type"][t][key] for t in types
            if t in summary["per_type"] and summary["per_type"][t][key] is not None]
    return 100 * sum(vals) / len(vals) if vals else float("nan")


out = []

# 1) OCR scale ablation
out += ["### OCR scale (200 images, pixel-only, face tile 192)", "",
        "| scale | recall* | precision* | overall covered | junk boxes | OCR ms | total ms |",
        "|---|---|---|---|---|---|---|"]
pts = []
for scale, tag in [(1.0, "full_s1"), (2.0, "full_s2"), (3.0, "full_s3")]:
    res = load(tag)
    s = evaluate(labels, res)
    t = timing_summary(res)
    rec, prec = macro(s, "recall"), macro(s, "precision")
    pts.append((scale, t["total"]["mean"], rec))
    out.append(f"| {scale} | {rec:.1f} | {prec:.1f} | {s['overall_covered'] * 100:.1f} | "
               f"{s['junk_box_rate'] * 100:.1f}% | {t['ocr']['mean']:.0f} | {t['total']['mean']:.0f} |")
out += ["", "*mean over email, phone, card, Aadhaar, address", ""]

# 2) per-type results at the chosen setting
res2 = load("full_s2")
s2 = evaluate(labels, res2)
out += ["### Per type at scale 2.0", "", "| type | n | recall | precision | area covered |", "|---|---|---|---|---|"]
for t, r in s2["per_type"].items():
    f = lambda v: "n/a" if v is None else f"{v * 100:.1f}"
    out.append(f"| {t} | {r['n']} | {f(r['recall'])} | {f(r['precision'])} | {f(r['covered'])} |")
out.append("")

# 3) confidence-threshold sweep on the chosen setting
out += ["### Confidence threshold sweep (scale 2.0)", "",
        "| min confidence | recall* | precision* | overall covered | junk boxes |", "|---|---|---|---|---|"]
sweep = []
for thr in [0.0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9]:
    s = evaluate(labels, res2, min_conf=thr)
    rec, prec = macro(s, "recall"), macro(s, "precision")
    sweep.append((thr, rec, prec))
    out.append(f"| {thr} | {rec:.1f} | {prec:.1f} | {s['overall_covered'] * 100:.1f} | "
               f"{s['junk_box_rate'] * 100:.1f}% |")

(RES / "table.md").write_text("\n".join(out))
print("\n".join(out))

# charts
fig, ax = plt.subplots(1, 2, figsize=(11, 4))
ax[0].plot([p[1] for p in pts], [p[2] for p in pts], "o-")
for sc, lat, rec in pts:
    ax[0].annotate(f"{sc}x", (lat, rec), textcoords="offset points", xytext=(6, -12))
ax[0].set(xlabel="mean latency per screenshot (ms)", ylabel="mean recall, pattern types (%)",
          title="OCR scale: recall vs latency")
ax[0].grid(alpha=0.3)
ax[1].plot([p[1] for p in sweep], [p[2] for p in sweep], "o-")
for thr, rec, prec in sweep:
    ax[1].annotate(f"{thr}", (rec, prec), textcoords="offset points", xytext=(5, 5), fontsize=8)
ax[1].set(xlabel="recall (%)", ylabel="precision (%)", title="Confidence threshold sweep")
ax[1].grid(alpha=0.3)
fig.tight_layout()
fig.savefig(RES / "recall_vs_latency.png", dpi=150)
print("\nwrote bench/results/table.md and recall_vs_latency.png")