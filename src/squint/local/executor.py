import re
from playwright.sync_api import Page
from squint.local.profile import PROFILE
from squint.schemas import ActionResponse, Box, RedactedBox

PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def resolve(text: str, boxes: list[Box]) -> str:
    """Swap {{key}} for the real value, locally. Profile first, then on-screen values."""
    def sub(m):
        key = m.group(1).lower()
        if key in PROFILE:
            return PROFILE[key]
        for b in boxes:
            if b.label == key and b.text:
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


def _describe(resp: ActionResponse, public: list[RedactedBox], targets=()) -> str:
    """Readable name of what was acted on, for the history note. Uses only element
    labels and redacted-box types, which the server already sees in the request."""
    if resp.element_id is not None:
        for t in targets:
            if t.id == resp.element_id:
                return f"'{t.label}'" if t.label else t.kind
    if resp.target_box_id is not None:
        for rb in public:
            if rb.id == resp.target_box_id:
                return f"redacted {rb.label} field"
    return "a point on the page"


def execute(page: Page, resp: ActionResponse, boxes: list[Box],
            public: list[RedactedBox], targets=()) -> str:
    """Run one action. The returned string goes into the server-bound history,
    so it must never contain resolved values, only the placeholder text."""
    if resp.action == "click":
        pt = _point(resp, public, targets)
        if not pt:
            return "click failed: no target"
        page.mouse.click(*pt)
        return f"clicked {_describe(resp, public, targets)}"
    if resp.action == "type":
        pt = _point(resp, public, targets)
        if pt:
            page.mouse.click(*pt)
            page.keyboard.press("ControlOrMeta+A")
            where = _describe(resp, public, targets)
        else:
            where = "the focused field"
        page.keyboard.type(resolve(resp.text or "", boxes))
        return f"typed {resp.text!r} into {where}"
    if resp.action == "scroll":
        page.mouse.wheel(0, 400)
        return "scrolled down"
    return "done"