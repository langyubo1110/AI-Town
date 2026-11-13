"""混合检索：向量召回 + BM25 召回 → RRF 融合。

一次检索走三步：
    ① 向量召回 top 40        —— 管"意思相近"
    ② BM25 召回 top 40       —— 管"字面对得上"
    ③ RRF 融合 → 取 top_k    —— 两路都靠前的胜出

为什么不是"向量检索完再拿 BM25 微调"：
    那样 BM25 只能在向量召回的那 40 条里挑，向量没召回的条目永远进不来。
    两路各自独立召回，才有互补的意义。
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.infra.embedding import get_embedding_model
from app.models import DocumentChunk
from app.rag.bm25 import BM25, tokenize
from app.rag.fusion import rrf

log = get_logger(__name__)

VECTOR_TOP = 40
BM25_TOP = 40
DEFAULT_TOP_K = 3


@dataclass
class Hit:
    """一条命中的文档块。source/title 用来给回答加引用。"""

    id: int
    source: str
    title: str
    content: str
    score: float


async def search(
    session: AsyncSession,
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
) -> list[Hit]:
    """混合检索。知识库为空时返回空列表（不抛）。"""
    text = (query or "").strip()
    if not text:
        return []

    # 一次把所有块读进内存：知识库只有几十条，比查两次库简单得多
    rows = (
        await session.execute(
            select(
                DocumentChunk.id,
                DocumentChunk.source,
                DocumentChunk.title,
                DocumentChunk.content,
            )
        )
    ).all()
    if not rows:
        return []

    meta = {row.id: row for row in rows}

    # ---- ① 向量召回 ----
    qvec = await get_embedding_model().aembed_query(text)
    distance = DocumentChunk.embedding.cosine_distance(qvec)
    ordered = await session.execute(
        select(DocumentChunk.id).order_by(distance).limit(VECTOR_TOP)
    )
    vector_ids = [row[0] for row in ordered]

    # ---- ② BM25 召回（用全部块，不受向量结果限制）----
    corpus = [tokenize(row.content) for row in rows]
    bm25 = BM25(corpus)
    scores = bm25.scores(tokenize(text))
    bm25_ids = [
        doc_id
        for score, doc_id in sorted(
            ((score, row.id) for score, row in zip(scores, rows, strict=True)),
            reverse=True,
        )
        if score > 0
    ][:BM25_TOP]

    # ---- ③ RRF 融合 ----
    fused = rrf([vector_ids, bm25_ids])[:top_k]

    hits = [
        Hit(
            id=doc_id,
            source=meta[doc_id].source,
            title=meta[doc_id].title,
            content=meta[doc_id].content,
            score=round(score, 5),
        )
        for doc_id, score in fused
        if doc_id in meta
    ]
    log.info(
        "docs_searched",
        query=text[:40],
        vector=len(vector_ids),
        bm25=len(bm25_ids),
        fused=len(hits),
    )
    return hits