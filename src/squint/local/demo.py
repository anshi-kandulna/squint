import threading
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from squint.local.agent import run_agent

UI = Path(__file__).resolve().parents[3] / "ui" / "index.html"

app = FastAPI(title="squint demo (local)")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
state = {"status": "idle", "error": None, "steps": []}


class RunReq(BaseModel):
    task: str = "Place my order"
    url: str = "http://localhost:8000/checkout.html"


def _work(req: RunReq):
    try:
        run_agent(req.url, req.task, on_step=lambda s: state["steps"].append(s))
        state["status"] = "done"
    except Exception as e:
        state["status"], state["error"] = "error", str(e)


@app.post("/run")
def start(req: RunReq):
    if state["status"] == "running":
        return {"ok": False, "msg": "already running"}
    state.update(status="running", error=None, steps=[])
    threading.Thread(target=_work, args=(req,), daemon=True).start()
    return {"ok": True}


@app.get("/state")
def get_state():
    steps = state["steps"]
    return {
        "status": state["status"],
        "error": state["error"],
        "latest": steps[-1] if steps else None,
        "log": [{"step": s["step"], "action": s["action"], "reasoning": s["reasoning"],
                 "ms": s["timings_ms"].get("total")} for s in steps],
    }


@app.get("/")
def index():
    return FileResponse(UI)