"""所有 ORM 模型集中导出。

Alembic 的 autogenerate 依赖这里的 import 来发现全部表。
漏掉一个模型 → 那条迁移会是空的。
"""

from app.models.affinity import Affinity
from app.models.base import Base, TimestampMixin
from app.models.document import DocumentChunk
from app.models.npc import NPC
from app.models.player import Player
from app.models.memory import Memory,EMBED_DIM
from app.models.event import Event

__all__ = [
    "Base",
    "TimestampMixin",
    "Player",
    "NPC",
    "Affinity",
    "Memory",
    "EMBED_DIM",
    "Event",
    "DocumentChunk",
]