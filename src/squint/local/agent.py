import base64
import sys
import httpx
from playwright.sync_api import sync_playwright
from squint.schemas import ActionRequest, ActionResponse
from squint.local.capture import snapshot, find_targets
from squint.local.pipeline import run
from squint.local.redact import draw_targets
from squint.local.executor import execute

W, H = 1280, 900


def run_agent(url: str, task: str, server: str = "http://localhost:9000",
              max_steps: int = 6, headless: bool = False):
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
            b64 = base64.b64encode(open(out, "rb").read()).decode()

            req = ActionRequest(task=task, image_b64=b64, boxes=public, targets=targets,
                                width=W, height=H, history=history)
            r = httpx.post(f"{server}/act", json=req.model_dump(), timeout=60)
            if r.status_code != 200:
                print("SERVER ERROR:", r.status_code, r.text)
                break
            resp = ActionResponse(**r.json())
            print(f"step {step}: {resp.action}  element=E{resp.element_id}  "
                  f"box={resp.target_box_id}  | {resp.reasoning}")
            print(f"        local: { {k: f'{v*1000:.0f}ms' for k, v in t.items()} }")

            if resp.action == "done":
                break
            history.append(execute(page, resp, boxes, public, targets))
            page.wait_for_timeout(600)
        browser.close()


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "Place my order"
    run_agent("http://localhost:8000/checkout.html", task)