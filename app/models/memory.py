"""NPC 记忆（情景记忆，带向量）。"""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

# 向量维度必须与 embedding 模型一致（text-embedding-v3 = 1024）
EMBED_DIM = 1024


class Memory(Base, TimestampMixin):
    """一条记忆。

    三因子检索需要的字段都在这里：
    - relevance     → embedding（向量检索算出来）
    - recency       → created_at / last_access_at
    - importance    → importance（由 LLM 打分，P5-3 实现）
    """

    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    npc_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("npcs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM), nullable=False)

    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    memory_type: Mapped[str] = mapped_column(String(16), nullable=False, default="episodic")

    #用于强化记忆
    access_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_access_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )