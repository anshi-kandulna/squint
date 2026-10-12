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

SUCCESS_TEXTS = ["thank you for your purchase", "order confirmed",
                 "order placed", "order complete"]


def _b64(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()


def run_agent(url: str, task: str, server: str = "http://localhost:9000",
              max_steps: int = 20, headless: bool = False, on_step=None):
    history: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            page = browser.new_page(viewport={"width": W, "height": H})

            # Browser alert()s are invisible in screenshots, so capture them
            # and feed them back to the model through the history.
            dialogs: list[str] = []

            def on_dialog(d):
                dialogs.append(d.message)
                d.accept()

            page.on("dialog", on_dialog)

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                print("goto slow, continuing:", e)
            page.wait_for_timeout(2000)

            for step in range(max_steps):
                raw, hints = snapshot(page, f"step{step}_raw.png")
                out, boxes, public, t = run(raw, f"step{step}_redacted.png", hints=hints)
                targets = find_targets(page, boxes)
                print("targets:", [(tg.id, tg.label) for tg in targets])
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

                note = execute(page, resp, boxes, public, targets)
                page.wait_for_timeout(1500)
                if dialogs:
                    note += f" | page alert: {'; '.join(dialogs)}"
                    dialogs.clear()
                history.append(note)

                # Deterministic stop conditions: don't trust the model to say "done".
                try:
                    body = page.inner_text("body").lower()
                except Exception:
                    body = ""
                if any(s in body for s in SUCCESS_TEXTS):
                    print("success text detected, stopping")
                    page.wait_for_timeout(1000)   # let the popup animation finish
                    raw, hints = snapshot(page, "final_raw.png")
                    out, boxes, _, _ = run(raw, "final_redacted.png", hints=hints)
                    print("final frame boxes:", [(b.label, b.source) for b in boxes])
                    page.wait_for_timeout(5000)   # keep the popup on screen for the recording
                    break
                if len(history) >= 3 and len(set(history[-3:])) == 1:
                    print("same action 3 times in a row, stopping")
                    break
        finally:
            browser.close()


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "Place my order"
    url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000/checkout.html"
    run_agent(url, task)