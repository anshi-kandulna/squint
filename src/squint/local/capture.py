"""Playwright screenshot capture and DOM hints."""

import re
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from squint.schemas import Box, Target
from squint.local.profile import PROFILE

# Only inputs that have a value, are sized, and are actually on top (not hidden
# behind a modal or overlay).
GUESS_JS = """() => [...document.querySelectorAll('input, textarea')].filter(e => {
  const r = e.getBoundingClientRect();
  if (!(e.value && e.value.trim() && r.width > 0 && r.height > 0)) return false;
  if (e.hasAttribute('data-pii')) return false;
  if (['hidden','checkbox','radio','submit','button'].includes(e.type)) return false;
  const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return !!top && (top === e || e.contains(top));
}).map(e => { const r = e.getBoundingClientRect();
  return {x:r.left, y:r.top, w:r.width, h:r.height, value:e.value, type:e.type, id:e.id,
          name:e.name, placeholder:e.placeholder, autocomplete:e.autocomplete,
          aria:e.getAttribute('aria-label') || ''}; })"""

ON_TOP_JS = """e => {
  const r = e.getBoundingClientRect();
  const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return !!t && (t === e || e.contains(t));
}"""

# Finds rendered text that matches a known local value (e.g. the profile name
# inside a confirmation popup) and returns its exact on-screen rectangles.
KNOWN_JS = r"""(pairs) => {
  const out = [];
  const skip = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEXTAREA', 'INPUT']);
  const esc = s => s.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+');
  const res = pairs.map(([k, v]) => [k, new RegExp(esc(v), 'gi')]);
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    const p = node.parentElement;
    if (!p || skip.has(p.tagName)) continue;
    const text = node.nodeValue;
    if (!text || !text.trim()) continue;
    for (const [k, re] of res) {
      re.lastIndex = 0;
      let m;
      while ((m = re.exec(text)) !== null) {
        if (!m[0]) { re.lastIndex++; continue; }
        const range = document.createRange();
        range.setStart(node, m.index);
        range.setEnd(node, m.index + m[0].length);
        for (const r of range.getClientRects()) {
          if (r.width <= 0 || r.height <= 0) continue;
          if (r.bottom <= 0 || r.top >= innerHeight || r.right <= 0 || r.left >= innerWidth) continue;
          const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          if (!top || !p.contains(top)) continue;
          out.push({key: k, x: r.left, y: r.top, w: r.width, h: r.height, value: m[0]});
        }
      }
    }
  }
  return out;
}"""

# Profile fields that count as PII when they appear as plain page text.
KNOWN_KEYS = ("name", "email", "phone", "card", "address")

KEYS = [
    ("card", r"card|cc-?num|credit|cvv|cvc"),
    ("email", r"e-?mail"),
    ("phone", r"phone|mobile|\btel\b|contact.?number"),
    ("aadhaar", r"aadhaar|aadhar"),
    ("address", r"address|street|\baddr|city|zip|postal|pin.?code|country|state"),
    ("name", r"(^|[^a-z])(full.?name|first.?name|last.?name|name)([^a-z]|$)"),
]


def guess_label(g: dict):
    """Guess the PII type of a filled input from its attributes."""
    t, ac = (g.get("type") or "").lower(), (g.get("autocomplete") or "").lower()
    if t == "password" or "password" in ac:
        return "password"
    if t == "email" or "email" in ac:
        return "email"
    if t == "tel" or ac.startswith("tel"):
        return "phone"
    if "cc-" in ac:
        return "card"
    blob = " ".join(str(g.get(k) or "") for k in ("id", "name", "placeholder", "aria")).lower()
    for label, rx in KEYS:
        if re.search(rx, blob):
            return label
    return None


def _settle(page: Page):
    """Wait for the page to settle without relying on 'networkidle'."""
    try:
        page.wait_for_load_state("load", timeout=5000)
    except Exception:
        pass
    try:
        page.wait_for_function(
            "() => [...document.images].every(i => i.complete)", timeout=5000)
    except Exception:
        pass
    page.wait_for_timeout(500)


def snapshot(page: Page, out: str = "shot.png"):
    """Screenshot + one Box per PII element (tagged, guessed, or known value). Real text stays local."""
    _settle(page)
    page.screenshot(path=out)
    hints: list[Box] = []

    for el in page.query_selector_all("[data-pii]"):
        bb = el.bounding_box()
        if not bb or bb["width"] <= 0 or bb["height"] <= 0:
            continue
        if not el.evaluate(ON_TOP_JS):
            continue
        tag = el.evaluate("e => e.tagName")
        text = el.input_value() if tag in ("INPUT", "TEXTAREA") else el.inner_text()
        hints.append(Box(
            x=round(bb["x"]), y=round(bb["y"]), w=round(bb["width"]), h=round(bb["height"]),
            label=el.get_attribute("data-pii"), confidence=1.0, source="dom",
            text=text or None))

    for g in page.evaluate(GUESS_JS):
        label = guess_label(g)
        if label:
            hints.append(Box(
                x=round(g["x"]), y=round(g["y"]), w=round(g["w"]), h=round(g["h"]),
                label=label, confidence=1.0, source="dom", text=g["value"]))

    # Redact anything on screen that equals a value the device itself holds.
    pairs = [[k, PROFILE[k]] for k in KNOWN_KEYS if PROFILE.get(k)]
    for k in page.evaluate(KNOWN_JS, pairs):
        hints.append(Box(
            x=round(k["x"]), y=round(k["y"]), w=round(k["w"]), h=round(k["h"]),
            label=k["key"], confidence=1.0, source="dom", text=k["value"]))

    return str(Path(out).resolve()), hints


def capture_page(url: str, out: str = "shot.png", width: int = 1280, height: int = 900):
    """Standalone: screenshot + one Box per [data-pii] element (exact DOM geometry)."""
    hints: list[Box] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print("goto slow, continuing:", e)
            _settle(page)
            page.screenshot(path=out)
            for el in page.query_selector_all("[data-pii]"):
                bb = el.bounding_box()
                if bb and bb["width"] > 0 and bb["height"] > 0:
                    hints.append(Box(
                        x=round(bb["x"]), y=round(bb["y"]),
                        w=round(bb["width"]), h=round(bb["height"]),
                        label=el.get_attribute("data-pii"),
                        confidence=1.0, source="dom"))
        finally:
            browser.close()
    return str(Path(out).resolve()), hints


def capture(url: str, out: str = "shot.png", width: int = 1280, height: int = 900) -> str:
    return capture_page(url, out, width, height)[0]


def _overlap(t: Target, b: Box) -> float:
    x1, y1 = max(t.x, b.x), max(t.y, b.y)
    x2, y2 = min(t.x + t.w, b.x + b.w), min(t.y + t.h, b.y + b.h)
    return max(0, x2 - x1) * max(0, y2 - y1) / max(1, t.w * t.h)


def find_targets(page: Page, avoid: list[Box]) -> list[Target]:
    """Visible, on-screen, on-top clickable elements, minus anything touching a redacted region."""
    sel = ("button, a[href], input[type=submit], input[type=button], [role=button], "
           "select, input:not([data-pii]), textarea:not([data-pii])")
    vh = (page.viewport_size or {"height": 900})["height"]
    out: list[Target] = []
    for el in page.query_selector_all(sel):
        if not el.is_visible():
            continue
        bb = el.bounding_box()
        if not bb or bb["width"] < 4 or bb["height"] < 4:
            continue
        if bb["y"] < 0 or bb["y"] + bb["height"] / 2 > vh:
            continue
        if not el.evaluate(ON_TOP_JS):
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