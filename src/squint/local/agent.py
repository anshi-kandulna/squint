import base64
import sys
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright
from squint.schemas import ActionRequest, ActionResponse
from squint.local.capture import snapshot, find_targets
from squint.local.pipeline import run
from squint.local.redact import draw_targets
from squint.local.executor import execute

W, H = 1280, 900


def _b64(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()


def run_agent(url: str, task: str, server: str = "http://localhost:9000",
              max_steps: int = 6, headless: bool = False, on_step=None):
    history: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page(viewport={"width": W, "height": H})
        page.goto(url)
        page.wait_for_load_state("networkidle")

        for step in range(max_steps):
            raw, hints = snapshot(page, f"step{step}_raw.png")
            out, boxes, public, t = run(raw, f"step{step}_redacted.png", hints=hints)
            targets = find_targets(page, boxes)
            draw_targets(out, targets)
            b64 = _b64(out)

            req = ActionRequest(task=task, image_b64=b64, boxes=public, targets=targets,
                                width=W, height=H, history=history)
            r = httpx.post(f"{server}/act", json=req.model_dump(), timeout=60)
            if r.status_code != 200:
                raise RuntimeError(f"server {r.status_code}: {r.text}")
            resp = ActionResponse(**r.json())
            print(f"step {step}: {resp.action}  element=E{resp.element_id}  | {resp.reasoning}")

            if on_step:
                on_step({
                    "step": step,
                    "raw_b64": _b64(raw),
                    "redacted_b64": b64,
                    "boxes": [{"label": b.label, "source": b.source, "text": b.text} for b in boxes],
                    "action": resp.action,
                    "element_id": resp.element_id,
                    "reasoning": resp.reasoning,
                    "timings_ms": {k: round(v * 1000) for k, v in t.items()},
                })

            if resp.action == "done":
                break
            history.append(execute(page, resp, boxes, public, targets))
            page.wait_for_timeout(600)
        browser.close()


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "Place my order"
    run_agent("http://localhost:8000/checkout.html", task)