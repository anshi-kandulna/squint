"""Merging and confidence handling for detection boxes."""
from squint.schemas import Box


def group_lines(words: list[Box], gap_factor: float = 1.5) -> list[list[Box]]:
    """Group word boxes into text runs: same visual line, small horizontal gaps.
    The gap check stops us joining text across form columns (card number | expiry)."""
    words = sorted(words, key=lambda b: b.y + b.h / 2)
    lines: list[list[Box]] = []
    for w in words:
        cy = w.y + w.h / 2
        for line in lines:
            ref = line[0]
            if abs((ref.y + ref.h / 2) - cy) < 0.5 * max(ref.h, w.h):
                line.append(w)
                break
        else:
            lines.append([w])

    runs: list[list[Box]] = []
    for line in lines:
        line.sort(key=lambda b: b.x)
        run = [line[0]]
        for prev, cur in zip(line, line[1:]):
            gap = cur.x - (prev.x + prev.w)
            if gap > gap_factor * max(prev.h, cur.h):
                runs.append(run)
                run = []
            run.append(cur)
        runs.append(run)
    return runs


def union(boxes: list[Box], **kw) -> Box:
    x1 = min(b.x for b in boxes)
    y1 = min(b.y for b in boxes)
    x2 = max(b.x + b.w for b in boxes)
    y2 = max(b.y + b.h for b in boxes)
    return Box(x=x1, y=y1, w=x2 - x1, h=y2 - y1, **kw)