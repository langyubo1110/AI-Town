from pydantic import BaseModel, Field


class NpcChatIn(BaseModel):
    player_id: int = Field(..., ge=1)
    npc_a: str = Field(..., min_length=1, max_length=32)
    npc_b: str = Field(..., min_length=1, max_length=32)
    topic: str = Field("", max_length=100)
    turns: int = Field(2, ge=1, le=3, description="每人说几轮")


class NpcChatAccepted(BaseModel):
    task_id: str = Field(..., description="Redis Stream 的消息 id，可用来追踪")
    status: str = "accepted"


# ---- 今日计划 ----
class PlanStepOut(BaseModel):
    at: str = Field(..., description="HH:MM")
    goal: str
    room: str
    status: str = Field(..., description="pending / done")


class NpcPlanOut(BaseModel):
    npc_id: int
    npc_name: str
    done: int
    total: int
    steps: list[PlanStepOut]


class PlanListOut(BaseModel):
    date: str
    items: list[NpcPlanOut]