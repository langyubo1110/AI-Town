"""事件台账（append-only：只增不改）。"""

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Event(Base, TimestampMixin):
    """一条发生过的事。"""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False
    )
    # 系统事件可能没有具体 NPC，所以允许 NULL
    npc_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("npcs.id", ondelete="CASCADE"), nullable=True
    )

    event_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # 人可读摘要：日志和前端直接用
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # 结构化细节：程序消费
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # 索引要匹配查询模式：WHERE player_id=? ORDER BY id DESC
    __table_args__ = (
        Index("ix_events_player_id_id", "player_id", "id"),
    )