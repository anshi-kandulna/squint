import pytesseract
from PIL import Image
from squint.schemas import Box


def run_ocr(image_path: str, min_conf: float = 0.0, scale: float = 2.0) -> list[Box]:
    """Word-level OCR. `scale` upsamples first; boxes are mapped back to original pixels."""
    img = Image.open(image_path).convert("RGB")
    if scale != 1.0:
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    boxes = []
    for i, txt in enumerate(data["text"]):
        txt = txt.strip()
        conf = float(data["conf"][i])
        if not txt or conf < 0 or conf / 100 < min_conf:
            continue
        boxes.append(Box(
            x=round(data["left"][i] / scale), y=round(data["top"][i] / scale),
            w=round(data["width"][i] / scale), h=round(data["height"][i] / scale),
            label="other", confidence=conf / 100, source="ocr", text=txt,
        ))
    return boxes