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

# 融合权重（向量 : BM25）= 3 : 1。这个数是**扫出来的**，不是拍的：
#
#   策略              Hit@1   Hit@3   MRR
#   vector            0.969   1.000   0.984
#   hybrid 1:1        0.906   1.000   0.953   ← 等权最差
#   hybrid 2:1        0.938   1.000   0.969
#   hybrid 3:1        0.969   1.000   0.984   ← 与纯向量持平
#   hybrid 10:1       0.969   1.000   0.984
#
# 结论：在 32 条用例、13 个块的小语料上，中文同义改写会让 BM25 给出错误排名，
# 等权融合反而拖低 MRR。3:1 是"保留 BM25、但不让它捣乱"的临界点；
# BM25 的价值要等语料变大、出现大量稀有 token（编码、型号、人名）时才体现。
RRF_WEIGHTS = (3.0, 1.0)


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
    strategy: str = "hybrid",
) -> list[Hit]:
    """混合检索。知识库为空时返回空列表（不抛）。

    `strategy` 只给消融实验用（生产永远走 hybrid）：
        vector  只用向量召回
        bm25    只用关键词召回
        hybrid  两路召回后 RRF 融合
    """
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

    # ---- ③ 按策略取前 top_k ----
    if strategy == "vector":
        ordered_ids = [(doc_id, 1.0 / (rank + 1)) for rank, doc_id in enumerate(vector_ids[:top_k])]
    elif strategy == "bm25":
        ordered_ids = [(doc_id, 1.0 / (rank + 1)) for rank, doc_id in enumerate(bm25_ids[:top_k])]
    elif strategy == "hybrid_equal":
        # 消融用：等权融合，用来证明"调权重"不是拍脑袋
        ordered_ids = rrf([vector_ids, bm25_ids])[:top_k]
    else:
        ordered_ids = rrf(
            [vector_ids, bm25_ids], weights=list(RRF_WEIGHTS)
        )[:top_k]

    hits = [
        Hit(
            id=doc_id,
            source=meta[doc_id].source,
            title=meta[doc_id].title,
            content=meta[doc_id].content,
            score=round(score, 5),
        )
        for doc_id, score in ordered_ids
        if doc_id in meta
    ]
    log.info(
        "docs_searched",
        query=text[:40],
        strategy=strategy,
        vector=len(vector_ids),
        bm25=len(bm25_ids),
        fused=len(hits),
    )
    return hits