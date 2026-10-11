import sys
import cv2
from squint.local.detect.ocr import run_ocr
from squint.local.detect.patterns import find_pii

COLORS = {  # BGR
    "email": (255, 0, 0), "card": (0, 0, 255), "aadhaar": (0, 140, 255),
    "phone": (0, 200, 0), "face": (255, 0, 255), "other": (150, 150, 150),
}


def draw(image_path, boxes, out="debug.png"):
    img = cv2.imread(image_path)
    for b in boxes:
        c = COLORS.get(b.label, COLORS["other"])
        cv2.rectangle(img, (b.x, b.y), (b.x + b.w, b.y + b.h), c, 2)
        cv2.putText(img, b.label, (b.x, b.y - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, c, 1)
    cv2.imwrite(out, img)
    return out


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "shot.png"
    words = run_ocr(path)
    hits = find_pii(words)
    for b in hits:
        print(f"{b.label:8} {b.confidence:.2f}  ({b.x},{b.y},{b.w},{b.h})  {b.text}")
    print("wrote", draw(path, hits))