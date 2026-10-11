"""Playwright screenshot capture and optional DOM hints."""

from pathlib import Path
from playwright.sync_api import sync_playwright
from squint.schemas import Box


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


if __name__ == "__main__":
    print(capture("http://localhost:8000/checkout.html"))