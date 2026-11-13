"""情景记忆：pgvector 长期存储与检索。"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

# ==================== 反思（reflection） ====================
# 反思和记忆的差别：
#   记忆是流水账 —— "11:17 我 code review 了队友的 PR"
#   反思是结论   —— "我最近总在给别人擦屁股，自己的模块反而没时间推进"
# 流水账检索得到但用不上；结论才能改变下一步行为。

REFLECTION_IMPORTANCE = 0.85  # 比事实记忆（0.7）更高：结论比细节值得记


#写入反思
async def remember_reflection(
    session: AsyncSession,
    *,
    npc_id: int,
    player_id: int,
    #记录的洞察列表
    insights: list[str],
) -> int:
    """把几条洞察写进长期记忆，返回写入条数。

    注意 player_id 只是外键要求（反思没有真实玩家），
    消费方是"生成计划时按 npc_id 查"，不依赖 player_id 过滤。
    """
    if not insights:
        return 0
    #向量化洞察
    vectors = await get_embedding_model().aembed_documents(insights)
    for text, vec in zip(insights, vectors, strict=True):
        #提交到数据库但不执行
        session.add(
            Memory(
                npc_id=npc_id,
                player_id=player_id,
                content=text,
                embedding=vec,
                importance=REFLECTION_IMPORTANCE,
                memory_type="reflection",
            )
        )
    # 不 commit，交给调用方
    return len(insights)

#读取反思供生成计划用
async def load_reflections(
    session: AsyncSession,
    *,
    npc_id: int,
    limit: int = 2,
    days: int = 7,
) -> list[str]:
    """取最近的反思，用于注入计划生成的 prompt。

    为什么按时间倒序而不是按相关度：反思是"我最近在想什么"，
    天然是时间性的，不需要向量检索。
    """
    since = datetime.now(UTC) - timedelta(days=days)
    stmt = (
        select(Memory.content)
        .where(
            Memory.npc_id == npc_id,
            Memory.memory_type == "reflection",
            Memory.created_at >= since,
        )
        .order_by(Memory.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)

#"反思的原料
async def recent_contents(
    session: AsyncSession,
    *,
    npc_id: int,
    limit: int = 8,
) -> list[str]:
    """取最近的记忆，作为反思的原料。

    先取最近 20 条，再按 importance 取前 limit 条 —— 只看 importance
    会把三个月前一件小事捞上来，只看时间又会全是废话。
    """
    stmt = (
        select(Memory.content, Memory.importance)
        .where(Memory.npc_id == npc_id)
        # 反思不再喂给反思，否则会越滚越抽象
        .where(Memory.memory_type != "reflection")
        .order_by(Memory.created_at.desc())
        .limit(20)
    )
    rows = (await session.execute(stmt)).all()
    rows.sort(key=lambda row: row[1], reverse=True)
    return [row[0] for row in rows[:limit]]