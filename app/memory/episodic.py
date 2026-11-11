"""情景记忆：pgvector 长期存储与检索。"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.core.logging import get_logger
from app.infra.embedding import get_embedding_model
from app.memory import ranking
from app.models import Memory

log = get_logger(__name__)

RECALL_K = 20        # 向量粗筛条数
TOP_K = 5            # 重排后注入提示词的条数
MIN_RELEVANCE = 0.2  # 粗筛下限，过滤掉纯噪声


#写入记忆
async def remember(
    session: AsyncSession,
    *,
    npc_id: int,
    player_id: int,
    turn_text: str,
    facts: list[str],
    importance: float,
) -> None:
    """写入一轮对话 + 若干事实。一次 batch embedding 搞定。"""
    texts = [turn_text, *facts]

    # aembed_documents 批量：1 次 API 调用算 N 条向量
    vectors = await get_embedding_model().aembed_documents(texts)

    session.add(
        #加入memory表
        Memory(
            npc_id=npc_id,
            player_id=player_id,
            content=turn_text,
            embedding=vectors[0],
            importance=max(0.0, min(1.0, importance)),
            memory_type="episodic",
        )
    )
    #循环写入事实记忆
    for fact, vec in zip(facts, vectors[1:], strict=True):
        session.add(
            Memory(
                npc_id=npc_id,
                player_id=player_id,
                content=fact,
                embedding=vec,
                # 事实比流水账更值得记住
                importance=max(0.0, min(1.0, importance + 0.2)),
                memory_type="fact",
            )
        )

    # 不 commit，交给图的 persist 节点统一提交

#召回
async def recall(
    session: AsyncSession,
    *,
    npc_id: int,
    player_id: int,
    query: str,
    top_k: int = TOP_K,
) -> list[ranking.Candidate]:
    """向量粗筛 → 三因子精排 → 更新访问计数。"""
    #向量化query
    qvec = await get_embedding_model().aembed_query(query)
    #向量粗筛（SQL 层）
    distance = Memory.embedding.cosine_distance(qvec)
    stmt = (
        #同时查找两个
        select(Memory, distance.label("distance"))
        .where(Memory.npc_id == npc_id, Memory.player_id == player_id)
        .order_by(distance)
        .limit(RECALL_K)
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        return []

    now = datetime.now(UTC)
    candidates: list[ranking.Candidate] = []
    for mem, dist in rows:
        #把余弦距离转成 0~1 相似度
        rel = ranking.relevance_from_distance(float(dist))
        #粗筛下限，相关性太低的直接不进精排
        if rel < MIN_RELEVANCE:
            continue
        # 复习效应：最近被想起过，也算"新"
        anchor = mem.last_access_at or mem.created_at               #上次被召回/想起的时间
        age_hours = max(0.0, (now - anchor).total_seconds() / 3600)
        candidates.append(
            ranking.Candidate(
                id=mem.id,
                content=mem.content,
                relevance=rel,
                importance=mem.importance,
                age_hours=age_hours,
            )
        )

    top = ranking.rank(candidates, top_k=top_k)

    # 被召回的记忆：计数 +1，刷新 last_access_at（强化）
    hit_ids = {c.id for c in top}
    for mem, _ in rows:
        if mem.id in hit_ids:
            mem.access_count += 1
            mem.last_access_at = now
    #写入日志
    log.info(
        "memory_recalled",
        npc_id=npc_id,
        player_id=player_id,
        candidates=len(candidates),
        top=[(c.id, round(ranking.score(c), 3)) for c in top],
    )
    return top