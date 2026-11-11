"""玩家 × NPC 的好感度。"""

from sqlalchemy import BigInteger, CheckConstraint, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Affinity(Base, TimestampMixin):
    __tablename__ = "affinities"
    __table_args__ = (
        UniqueConstraint("player_id", "npc_id", name="uq_affinities_player_npc"),
        CheckConstraint("score >= 0 AND score <= 100", name="score_range"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    npc_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("npcs.id", ondelete="CASCADE"), nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)