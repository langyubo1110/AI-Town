"""知识库文档块 —— 文档 RAG 的存储。

为什么单独一张表，不复用 memories：
    memories 是"NPC 记得的事"，按 (npc_id, player_id) 归属，是私有的。
    文档是"小镇里所有人都能查的资料"，没有归属，是公共的。
    硬塞进同一张表，检索时就得靠 memory_type 区分，两个语义会互相污染。

为什么叫 chunk 而不是 document：
    一篇文档会被切成很多块。向量检索的最小单位是"块"，不是"篇"。
    表名跟着检索单位走，读代码时不容易搞混。
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.memory import EMBED_DIM


class DocumentChunk(Base, TimestampMixin):
    """一个文档块。

    source  + chunk_index 唯一确定"这是哪篇文档的第几段"，
    引用时把 source 一起返回给用户，用户才知道答案是从哪来的。
    """

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 文件名，例如 "研发规范.md" —— 直接当引用来源展示
    source: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # 这篇文档切出来的第几块，从 0 开始
    chunk_index: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # 文档标题（取文件名去掉后缀），用于展示
    title: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM), nullable=False)