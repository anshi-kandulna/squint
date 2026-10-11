import re
from playwright.sync_api import Page
from squint.schemas import ActionResponse, Box, RedactedBox

PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def resolve(text: str, boxes: list[Box]) -> str:
    """Swap {{type}} for the real value, locally. Unknown placeholders are left as-is."""
    def sub(m):
        for b in boxes:
            if b.label == m.group(1) and b.text:
                return b.text
        return m.group(0)
    return PLACEHOLDER.sub(sub, text)


def _point(resp: ActionResponse, public: list[RedactedBox], targets=()):
    if resp.element_id is not None:
        for t in targets:
            if t.id == resp.element_id:
                return t.x + t.w // 2, t.y + t.h // 2
    if resp.target_box_id is not None:
        for rb in public:
            if rb.id == resp.target_box_id:
                return rb.x + rb.w // 2, rb.y + rb.h // 2
    if resp.x is not None and resp.y is not None:
        return resp.x, resp.y
    return None


def execute(page: Page, resp: ActionResponse, boxes: list[Box],
            public: list[RedactedBox], targets=()) -> str:
    """Run one action. The returned string goes into the server-bound history,
    so it must never contain resolved values, only the placeholder text."""
    if resp.action == "click":
        pt = _point(resp, public, targets)
        if not pt:
            return "click failed: no target"
        page.mouse.click(*pt)
        return f"clicked at {pt}"
    if resp.action == "type":
        pt = _point(resp, public, targets)
        if pt:
            page.mouse.click(*pt)
            page.keyboard.press("ControlOrMeta+A")
        page.keyboard.type(resolve(resp.text or "", boxes))
        return f"typed {resp.text!r}"
    if resp.action == "scroll":
        page.mouse.wheel(0, 400)
        return "scrolled down"
    return "done"