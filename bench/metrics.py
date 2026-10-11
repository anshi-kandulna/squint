"""Benchmark matching and redaction metrics."""
"""Scoring: compare pipeline detections against ground-truth boxes."""

TYPES = ["face", "email", "phone", "card", "aadhaar", "name", "address"]


def iou(a, b):
    x1, y1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    x2 = min(a["x"] + a["w"], b["x"] + b["w"])
    y2 = min(a["y"] + a["h"], b["y"] + b["h"])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union else 0.0


def overlap_frac(a, b):
    """Fraction of box `a` that lies inside box `b`."""
    x1, y1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    x2 = min(a["x"] + a["w"], b["x"] + b["w"])
    y2 = min(a["y"] + a["h"], b["y"] + b["h"])
    return max(0, x2 - x1) * max(0, y2 - y1) / max(1, a["w"] * a["h"])


def covered_frac(g, boxes):
    """Fraction of ground-truth box g covered by the union of `boxes` (any label)."""
    import numpy as np
    gw, gh = max(1, g["w"]), max(1, g["h"])
    mask = np.zeros((gh, gw), dtype=bool)
    for b in boxes:
        x1, y1 = max(b["x"], g["x"]) - g["x"], max(b["y"], g["y"]) - g["y"]
        x2 = min(b["x"] + b["w"], g["x"] + g["w"]) - g["x"]
        y2 = min(b["y"] + b["h"], g["y"] + g["h"]) - g["y"]
        if x2 > x1 and y2 > y1:
            mask[y1:y2, x1:x2] = True
    return float(mask.mean())


def match(gt, dets, thr=0.5, face_thr=0.6):
    """Greedy one-to-one matching on the same label.
    Faces: the detector box (tight on facial features) must lie mostly inside the
    ground-truth photo frame. Everything else: IoU >= thr."""
    pairs = []
    for gi, g in enumerate(gt):
        for di, d in enumerate(dets):
            if g["label"] != d["label"]:
                continue
            if g["label"] == "face":
                s, need = overlap_frac(d, g), face_thr
            else:
                s, need = iou(g, d), thr
            if s >= need:
                pairs.append((s, gi, di))
    pairs.sort(reverse=True)
    used_g, used_d, matches = set(), set(), []
    for s, gi, di in pairs:
        if gi in used_g or di in used_d:
            continue
        used_g.add(gi)
        used_d.add(di)
        matches.append((gi, di))
    return matches, used_g, used_d


def evaluate(labels, results, min_conf=0.0, iou_thr=0.5, cover_thr=0.9):
    """labels: {img: {boxes: [...]}}   results: {img: {dets: [...], padded: [...], timing: {...}}}
    Detections below min_conf are ignored, so one run can be scored at many thresholds."""
    per = {t: dict(tp=0, fn=0, fp=0, covered=0, n=0) for t in TYPES}
    junk = 0          # detection boxes that touch no sensitive region at all
    total_dets = 0
    for img, lab in labels.items():
        r = results.get(img)
        if r is None:
            continue
        idx = [i for i, d in enumerate(r["dets"]) if d["confidence"] >= min_conf]
        dets = [r["dets"][i] for i in idx]
        padded = [r["padded"][i] for i in idx]
        gt = lab["boxes"]

        _, used_g, used_d = match(gt, dets, iou_thr)
        for gi, g in enumerate(gt):
            s = per.setdefault(g["label"], dict(tp=0, fn=0, fp=0, covered=0, n=0))
            s["n"] += 1
            s["tp" if gi in used_g else "fn"] += 1
            s["covered"] += covered_frac(g, padded) >= cover_thr
        for di, d in enumerate(dets):
            total_dets += 1
            if di not in used_d:
                per.setdefault(d["label"], dict(tp=0, fn=0, fp=0, covered=0, n=0))["fp"] += 1
            if not any(overlap_frac(d, g) > 0.1 for g in gt):
                junk += 1

    rows = {}
    for t, s in per.items():
        if s["n"] == 0 and s["fp"] == 0:
            continue
        rows[t] = dict(
            n=s["n"],
            recall=s["tp"] / s["n"] if s["n"] else None,
            precision=s["tp"] / (s["tp"] + s["fp"]) if (s["tp"] + s["fp"]) else None,
            covered=s["covered"] / s["n"] if s["n"] else None,
        )
    n_all = sum(s["n"] for s in per.values())
    return dict(
        per_type=rows,
        overall_covered=sum(s["covered"] for s in per.values()) / n_all if n_all else None,
        junk_box_rate=junk / total_dets if total_dets else 0.0,
        total_dets=total_dets,
    )


def timing_summary(results):
    import numpy as np
    stages = {}
    for r in results.values():
        for k, v in r["timing"].items():
            stages.setdefault(k, []).append(v * 1000)
    return {k: dict(mean=float(np.mean(v)), p95=float(np.percentile(v, 95))) for k, v in stages.items()}


def _pct(v):
    return "  n/a" if v is None else f"{v * 100:5.1f}"


def print_report(summary, timing=None, title=""):
    print(f"\n=== {title} ===")
    print(f"{'type':9}{'n':>5}  {'recall':>7} {'prec':>7} {'covered':>8}")
    for t, r in summary["per_type"].items():
        print(f"{t:9}{r['n']:>5}  {_pct(r['recall']):>7} {_pct(r['precision']):>7} {_pct(r['covered']):>8}")
    print(f"overall covered (>=90% of area redacted): {_pct(summary['overall_covered'])}%")
    print(f"junk boxes (redacted nothing sensitive): {summary['junk_box_rate'] * 100:.1f}% of {summary['total_dets']} boxes")
    if timing:
        print("latency ms (mean / p95): " + "  ".join(
            f"{k} {v['mean']:.0f}/{v['p95']:.0f}" for k, v in timing.items()))