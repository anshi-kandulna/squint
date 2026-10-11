"""FastAPI application entry point."""
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from squint.schemas import ActionRequest, ActionResponse
from squint.server.vlm import decide

app = FastAPI(title="squint server")
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_last: dict = {}


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/act", response_model=ActionResponse)
def act(req: ActionRequest):
    _last.update(task=req.task, boxes=[b.model_dump() for b in req.boxes],
                 width=req.width, height=req.height,
                 image_b64=req.image_b64, history=req.history)
    try:
        return decide(req)
    except Exception as e:
        raise HTTPException(502, f"VLM call failed: {e}")


@app.get("/last")
def last():
    """Exactly what the server received on the most recent call (for the demo panel)."""
    return _last