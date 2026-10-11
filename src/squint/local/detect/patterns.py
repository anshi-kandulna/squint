"""Regex-based detection for common sensitive patterns."""
import re
from squint.schemas import Box
from squint.local.detect.merge import group_lines, union

# Order = priority. Card is checked before Aadhaar so a 16-digit number
# isn't claimed as a 12-digit one.
PATTERNS = [
    ("email",   re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), 1.0),
    ("card",    re.compile(r"(?<!\d)(?:\d{4}[ -]?){3}\d{4}(?!\d)"), 1.0),
    ("aadhaar", re.compile(r"(?<!\d)\d{4}[ -]?\d{4}[ -]?\d{4}(?!\d)"), 1.0),
    ("phone",   re.compile(r"(?<!\d)(?:\+91[ -]?)?[6-9]\d{4}[ -]?\d{5}(?!\d)"), 1.0),
    # Fallback: four number groups of 3-5 digits on one line = probably a card the OCR
    # misread. Redacted anyway (recall over precision), flagged with lower confidence.
    ("card",    re.compile(r"(?<!\d)(?:\d{3,5}[ -]?){3}\d{3,5}(?!\d)"), 0.5),
    ("address", re.compile(r"(?<!\d)\d{1,4},\s[^,\n]+(?:,\s[^,\n]+){1,3}?\s\d{6}(?!\d)"), 0.8),
]


def luhn(s: str) -> bool:
    d = [int(c) for c in s if c.isdigit()][::-1]
    return (sum(d[0::2]) + sum(sum(divmod(2 * x, 10)) for x in d[1::2])) % 10 == 0


def find_pii(words: list[Box]) -> list[Box]:
    out: list[Box] = []
    for run in group_lines(words):
        text, spans = "", []
        for w in run:
            if text:
                text += " "
            spans.append((len(text), len(text) + len(w.text), w))
            text += w.text

        claimed: list[tuple[int, int]] = []
        for label, rx, penalty in PATTERNS:
            for m in rx.finditer(text):
                s, e = m.span()
                if any(s < ce and cs < e for cs, ce in claimed):
                    continue
                claimed.append((s, e))
                hit = [w for ws, we, w in spans if ws < e and s < we]
                conf = min(w.confidence for w in hit)*penalty
                if label == "card" and not luhn(m.group()):
                    conf *= 0.6   # still redacted, but lower confidence
                out.append(union(hit, label=label, source="regex",
                                 text=m.group(), confidence=conf))
    return out