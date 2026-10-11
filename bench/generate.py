"""Generate benchmark screenshots and ground truth."""
"""Synthetic benchmark: fake-PII pages -> screenshots + free ground truth.

Run:  uv run python bench/generate.py -n 200 --seed 0 --preview 4
"""
import argparse
import base64
import json
import random
from datetime import date, timedelta
from pathlib import Path

import cv2
from faker import Faker
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
FACES_DIR = ROOT / "faces"
FALLBACK_FACE = ROOT.parent / "mock_site" / "static" / "face.jpg"

FONTS = ["Arial, sans-serif", "Helvetica, Arial, sans-serif", "Verdana, sans-serif",
         "'Trebuchet MS', sans-serif", "Georgia, serif", "'Times New Roman', serif",
         "'Courier New', monospace", "system-ui, sans-serif"]
TEMPLATES = ["checkout", "receipt"]
PRODUCTS = ["Wireless Mouse", "USB-C Cable", "Notebook Pack", "Desk Lamp", "Water Bottle",
            "Phone Stand", "Headphones", "Backpack", "Keyboard", "Webcam"]

fake = Faker("en_IN")


def digits(rng, n):
    return "".join(str(rng.randint(0, 9)) for _ in range(n))


def group(s, size, sep):
    return sep.join(s[i:i + size] for i in range(0, len(s), size))


def make_card(rng):
    for _ in range(20):
        num = fake.credit_card_number(card_type=rng.choice(["visa16", "mastercard"]))
        if len(num) == 16 and num.isdigit():
            return group(num, 4, rng.choice([" ", " ", "-"]))
    return group(digits(rng, 16), 4, " ")


def make_phone(rng):
    core = rng.choice("6789") + digits(rng, 9)
    style = rng.choice(["+91 {a} {b}", "+91-{a}{b}", "{a} {b}", "+91 {a}{b}"])
    return style.format(a=core[:5], b=core[5:])


def make_person(rng):
    return dict(
        name=fake.name(),
        email=fake.safe_email(),
        phone=make_phone(rng),
        card=make_card(rng),
        aadhaar=group(rng.choice("23456789") + digits(rng, 11), 4, " "),
        address=f"{rng.randint(1, 250)}, {fake.street_name()}, {fake.city()} {fake.postcode()}",
    )


def pick_face(rng):
    files = sorted(p for p in FACES_DIR.iterdir()
                   if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".avif"))
    if not files:
        files = sorted(p for p in FALLBACK_FACE.parent.iterdir()
                       if p.stem == "face" and p.suffix.lower() in (".jpg", ".jpeg", ".png")) \
                if FALLBACK_FACE.parent.exists() else []
    if not files:
        return None
    path = rng.choice(files)
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def build_context(kind, rng):
    p = make_person(rng)
    ctx = dict(
        p=p,
        theme=rng.choice(["light", "dark"]),
        font=rng.choice(FONTS),
        root_px=rng.choice([13, 14, 16, 18, 20]),   # acts as the "zoom" knob
        wrap_rem=rng.choice([42, 48, 56]),
        show_email=rng.random() < 0.85,
        face=pick_face(rng) if rng.random() < 0.8 else None,
        face_px=rng.choice([56, 72, 96, 120]),
    )
    if kind == "checkout":
        fields = [
            dict(label="Shipping address", value=p["address"], pii="address"),
            dict(label="Card number", value=p["card"], pii="card"),
            dict(label="Expiry", value=f"{rng.randint(1, 12):02d}/{rng.randint(27, 32)}", pii=None),
            dict(label="Order reference", value=f"ORD-{digits(rng, 8)}", pii=None),
        ]
        if rng.random() < 0.7:
            fields.append(dict(label="Aadhaar (for KYC)", value=p["aadhaar"], pii="aadhaar"))
        rng.shuffle(fields)
        qty, unit = rng.randint(1, 4), rng.randint(199, 4999)
        ctx.update(fields=fields, qty=qty, product=rng.choice(PRODUCTS), price=f"{qty * unit:,}")
    else:
        items = []
        for name in rng.sample(PRODUCTS, rng.randint(2, 5)):
            qty, price = rng.randint(1, 3), rng.randint(99, 3999)
            items.append(dict(name=name, qty=qty, price=f"{price:,}", total=f"{qty * price:,}"))
        grand = sum(int(i["total"].replace(",", "")) for i in items)
        d = date(2026, 1, 1) + timedelta(days=rng.randint(0, 280))
        ctx.update(items=items, grand=f"{grand:,}", store=fake.company(),
                   inv=digits(rng, 6), date=d.strftime("%d %b %Y"))
    return ctx


GET_BOXES = """() => [...document.querySelectorAll('[data-pii]')].map(e => {
  const r = e.getBoundingClientRect();
  return {label: e.dataset.pii, text: e.tagName === 'IMG' ? null : e.innerText.trim(),
          x: r.left, y: r.top, w: r.width, h: r.height};
})"""


def draw_preview(img_path, boxes, out_path):
    img = cv2.imread(str(img_path))
    for b in boxes:
        cv2.rectangle(img, (b["x"], b["y"]), (b["x"] + b["w"], b["y"] + b["h"]), (0, 200, 0), 2)
        cv2.putText(img, b["label"], (b["x"], max(12, b["y"] - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 0), 1, cv2.LINE_AA)
    cv2.imwrite(str(out_path), img)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--preview", type=int, default=0, help="also write N images with GT boxes drawn")
    args = ap.parse_args()

    DATA.mkdir(exist_ok=True)
    (DATA / "preview").mkdir(exist_ok=True)
    env = Environment(loader=FileSystemLoader(ROOT / "templates"))
    labels, counts = {}, {}

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for i in range(args.n):
            rng = random.Random(args.seed * 100_000 + i)
            fake.seed_instance(args.seed * 100_000 + i)
            kind = TEMPLATES[i % len(TEMPLATES)]
            ctx = build_context(kind, rng)
            html = env.get_template(f"{kind}.html.j2").render(**ctx)

            width = rng.choice([1024, 1280, 1366, 1440])
            page = browser.new_page(viewport={"width": width, "height": 800})
            page.set_content(html, wait_until="load")
            page.evaluate("document.fonts.ready")
            height = min(max(page.evaluate("document.documentElement.scrollHeight"), 500), 2400)
            page.set_viewport_size({"width": width, "height": height})

            name = f"{kind}_{i:04d}.png"
            page.screenshot(path=str(DATA / name))
            boxes = []
            for b in page.evaluate(GET_BOXES):
                if b["w"] < 2 or b["h"] < 2:
                    continue
                boxes.append(dict(label=b["label"], text=b["text"], x=round(b["x"]), y=round(b["y"]),
                                  w=round(b["w"]), h=round(b["h"])))
                counts[b["label"]] = counts.get(b["label"], 0) + 1
            page.close()

            labels[name] = dict(
                meta=dict(template=kind, theme=ctx["theme"], font=ctx["font"],
                          root_px=ctx["root_px"], width=width, height=height),
                boxes=boxes)
            if i < args.preview:
                draw_preview(DATA / name, boxes, DATA / "preview" / name)
        browser.close()

    (DATA / "labels.json").write_text(json.dumps(labels, indent=1))
    print(f"wrote {args.n} screenshots + labels.json to {DATA}")
    print("ground-truth boxes by type:", counts)


if __name__ == "__main__":
    main()