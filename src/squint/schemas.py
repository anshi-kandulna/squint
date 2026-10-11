"""Shared request, response, detection, and bounding-box schemas."""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel

PIIType = Literal["face", "email", "phone", "card", "aadhaar", "name", "address", "other"]
Source = Literal["face", "ocr", "regex", "dom", "classifier"]


class Box(BaseModel):
    x: int
    y: int
    w: int
    h: int
    label: PIIType = "other"
    confidence: float = 1.0
    source: Source = "ocr"
    text: Optional[str] = None  # stays local, never sent to the server

    def iou(self, other: "Box") -> float:
        x1, y1 = max(self.x, other.x), max(self.y, other.y)
        x2 = min(self.x + self.w, other.x + other.w)
        y2 = min(self.y + self.h, other.y + other.h)
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        union = self.w * self.h + other.w * other.h - inter
        return inter / union if union else 0.0


class RedactedBox(BaseModel):
    """What the server is allowed to know about a redaction: no text."""
    id: int
    x: int
    y: int
    w: int
    h: int
    label: PIIType


class ActionRequest(BaseModel):
    task: str
    image_b64: str          # redacted screenshot, PNG
    boxes: list[RedactedBox]
    width: int
    height: int


class ActionResponse(BaseModel):
    action: Literal["click", "type", "scroll", "done"]
    x: Optional[int] = None
    y: Optional[int] = None
    target_box_id: Optional[int] = None   # if it points at a redacted region
    text: Optional[str] = None            # may contain placeholders like {{card}}
    reasoning: Optional[str] = None