"""Playwright screenshot capture and optional DOM hints."""

from matplotlib.dviread import Page
from squint.schemas import Box, Target, Target
from pathlib import Path
from playwright.sync_api import Page, sync_playwright
from squint.schemas import Box

def snapshot(page: Page, out: str = "shot.png"):
    """Screenshot + one Box per [data-pii] element, with its real text kept local."""
    page.screenshot(path=out)
    hints: list[Box] = []
    for el in page.query_selector_all("[data-pii]"):
        bb = el.bounding_box()
        if not bb or bb["width"] <= 0 or bb["height"] <= 0:
            continue
        tag = el.evaluate("e => e.tagName")
        text = el.input_value() if tag in ("INPUT", "TEXTAREA") else el.inner_text()
        hints.append(Box(
            x=round(bb["x"]), y=round(bb["y"]), w=round(bb["width"]), h=round(bb["height"]),
            label=el.get_attribute("data-pii"), confidence=1.0, source="dom",
            text=text or None))
    return str(Path(out).resolve()), hints


def capture_page(url: str, out: str = "shot.png", width: int = 1280, height: int = 900):
    """Screenshot + one Box per [data-pii] element (exact DOM geometry)."""
    hints: list[Box] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(url)
        page.wait_for_load_state("networkidle")   # make sure images have loaded
        page.screenshot(path=out)
        for el in page.query_selector_all("[data-pii]"):
            bb = el.bounding_box()
            if bb and bb["width"] > 0 and bb["height"] > 0:
                hints.append(Box(
                    x=round(bb["x"]), y=round(bb["y"]),
                    w=round(bb["width"]), h=round(bb["height"]),
                    label=el.get_attribute("data-pii"),
                    confidence=1.0, source="dom"))
        browser.close()
    return str(Path(out).resolve()), hints


def capture(url: str, out: str = "shot.png", width: int = 1280, height: int = 900) -> str:
    return capture_page(url, out, width, height)[0]


def _overlap(t: Target, b: Box) -> float:
    x1, y1 = max(t.x, b.x), max(t.y, b.y)
    x2, y2 = min(t.x + t.w, b.x + b.w), min(t.y + t.h, b.y + b.h)
    return max(0, x2 - x1) * max(0, y2 - y1) / max(1, t.w * t.h)


def find_targets(page: Page, avoid: list[Box]) -> list[Target]:
    """Visible clickable elements, minus anything touching a redacted region."""
    sel = ("button, a[href], input[type=submit], input[type=button], [role=button], "
           "select, input:not([data-pii]), textarea:not([data-pii])")
    out: list[Target] = []
    for el in page.query_selector_all(sel):
        if not el.is_visible():
            continue
        bb = el.bounding_box()
        if not bb or bb["width"] < 4 or bb["height"] < 4:
            continue
        label = (el.inner_text() or el.get_attribute("aria-label")
                 or el.get_attribute("placeholder") or el.get_attribute("value") or "")
        t = Target(id=len(out) + 1,
                   kind=el.evaluate("e => (e.getAttribute('role') || e.tagName).toLowerCase()"),
                   label=label.strip()[:60] or None,
                   x=round(bb["x"]), y=round(bb["y"]),
                   w=round(bb["width"]), h=round(bb["height"]))
        if any(_overlap(t, a) > 0.2 for a in avoid):
            continue
        out.append(t)
    return out


if __name__ == "__main__":
    print(capture("http://localhost:8000/checkout.html"))