"""NPC表。"""

from sqlalchemy import BigInteger, String,Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

class NPC(Base,TimestampMixin):
    __tablename__ = 'npcs'

    id:Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name:Mapped[str]=mapped_column(String(32),unique=True,nullable=False,index=True)
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    personality: Mapped[str] = mapped_column(Text,nullable=False)
    expertise: Mapped[str] = mapped_column(Text,nullable=False)
    style: Mapped[str] = mapped_column(Text,nullable=False)
    location: Mapped[str] = mapped_column(String(64), nullable=False, default="办公室")
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)