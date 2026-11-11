from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    npc_id: int | None = None
    summary: str
    payload: dict
    created_at: datetime


class EventListOut(BaseModel):
    total: int
    items: list[EventOut]
    next_before_id: int | None = None   # 给前端翻下一页用