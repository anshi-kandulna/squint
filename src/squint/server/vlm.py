"""VLM API integration."""
import json
import os
import re
from groq import Groq
from squint.schemas import ActionRequest, ActionResponse
from squint.server.prompts import SYSTEM, build_user_text

MODEL = os.getenv("SQUINT_MODEL", "qwen/qwen3.8-27b")

TOOL = {
    "type": "function",
    "function": {
        "name": "perform_action",
        "description": "Perform the next single browser action.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["click", "type", "scroll", "done"]},
                "element_id": {"type": "integer"},
                "target_box_id": {"type": "integer"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "text": {"type": "string"},
                "reasoning": {"type": "string"},
            },
            "required": ["action", "reasoning"],
        },
    },
}

_client = None


def _parse_json_fallback(content: str) -> dict:
    """If the model answers in plain text instead of a tool call, pull out the JSON object."""
    m = re.search(r"\{.*\}", content or "", re.S)
    if not m:
        raise RuntimeError(f"model returned no action: {content!r}")
    return json.loads(m.group())


def decide(req: ActionRequest) -> ActionResponse:
    global _client
    if _client is None:
        _client = Groq()                     # reads GROQ_API_KEY
    resp = _client.chat.completions.create(
        model=MODEL,
        max_tokens=500,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": build_user_text(req)},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{req.image_b64}"}},
            ]},
        ],
        tools=[TOOL],
        tool_choice={"type": "function", "function": {"name": "perform_action"}},
    )
    msg = resp.choices[0].message
    if msg.tool_calls:
        args = json.loads(msg.tool_calls[0].function.arguments)
    else:
        args = _parse_json_fallback(msg.content)
    return ActionResponse(**args)