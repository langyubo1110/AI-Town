"""事件台账（append-only：只增不改）。"""

from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, text
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

    # 幂等键：同一条消息被重复投递时，靠它挡住第二次写入。
    # Redis Stream 是"至少一次"语义 —— worker 崩了会把 pending 的消息重投，
    # 没有这个键就会写两条一模一样的事件（用户看到两条"张三和李四聊了聊"）。
    dedupe_key: Mapped[str | None] = mapped_column(String(96), nullable=True)

    # 索引要匹配查询模式：WHERE player_id=? ORDER BY id DESC
    __table_args__ = (
        Index("ix_events_player_id_id", "player_id", "id"),
        # 部分唯一索引：只约束"有幂等键"的行，历史数据（NULL）不受影响
        Index(
            "uq_events_dedupe_key",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
    )