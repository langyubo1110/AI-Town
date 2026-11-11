"""
NPC 接口的响应模型。
DTO
Pydantic 响应模型
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict


#单个npc返回结构
class NPCOut(BaseModel):
    #允许从"任意对象属性"读取数据，而不只是字典
    #让 FastAPI 能把数据库对象直接转成 JSON 响应。
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    title: str
    personality: str
    expertise: str
    style: str
    location: str
    is_active: bool
    created_at: datetime

#npc列表返回结构
class NPCListOut(BaseModel):
    total: int
    items: list[NPCOut]