"""Pixel redaction and labelled-box generation."""
import cv2
from squint.schemas import Box, RedactedBox


def _padded(b: Box, w: int, h: int) -> tuple[int, int, int, int]:
    if b.source == "dom":
        pad = 2                          # DOM geometry is already exact
    elif b.label == "face":
        pad = int(1.4 * max(b.w, b.h))   # detector box is tight; cover the whole head
    else:
        pad = 3
    return (max(0, b.x - pad), max(0, b.y - pad),
            min(w, b.x + b.w + pad), min(h, b.y + b.h + pad))


def redact(image_path: str, boxes: list[Box], out_path: str = "redacted.png"):
    """Solid-fill redaction. Pixels are overwritten, not blurred, so there is
    nothing to deblur or reconstruct. Each region gets a numbered label burned
    in, so the VLM can refer to it ("click box 3")."""
    img = cv2.imread(image_path)
    h, w = img.shape[:2]
    public: list[RedactedBox] = []
    for i, b in enumerate(boxes, start=1):
        x1, y1, x2, y2 = _padded(b, w, h)
        cv2.rectangle(img, (x1, y1), (x2, y2), (30, 30, 30), -1)
        cv2.putText(img, f"[{i}:{b.label}]", (x1 + 4, y1 + max(12, (y2 - y1) // 2 + 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        public.append(RedactedBox(id=i, x=x1, y=y1, w=x2 - x1, h=y2 - y1, label=b.label))
    cv2.imwrite(out_path, img)
    return out_path, public


def draw_targets(path: str, targets) -> None:
    img = cv2.imread(path)
    for t in targets:
        cv2.rectangle(img, (t.x, t.y), (t.x + t.w, t.y + t.h), (255, 120, 0), 2)
        cv2.putText(img, f"E{t.id}", (t.x + 3, t.y - 5), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (255, 120, 0), 2, cv2.LINE_AA)
    cv2.imwrite(path, img)