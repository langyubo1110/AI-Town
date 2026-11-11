"""对话接口的请求/响应模型。"""

from pydantic import BaseModel, ConfigDict, Field

#请求体
class ChatIn(BaseModel):
    player_name: str = Field(..., min_length=1, max_length=64, description="玩家名")
    npc_name: str = Field(..., min_length=1, max_length=32, description="NPC 名")
    message: str = Field(..., min_length=1, max_length=500, description="玩家说的话")


# 一次工具调用的摘要（只给前端展示"NPC 查了什么"，不带完整结果，避免响应体膨胀）
class ToolUsed(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)


#请求结果
class ChatOut(BaseModel):
    player_id: int
    npc_name: str
    npc_title: str
    reply: str
    affinity_score: float
    affinity_delta: float
    affinity_level: str
    tools: list[ToolUsed] = Field(default_factory=list, description="本轮调用过的工具")