"""Agent 可调用的工具（Tool Use / Function Calling）。

三个设计决定：

1. **闭包注入依赖**：工具需要 session / npc_id / player_id，用法是
   `build_tools(session, npc_id=..., player_id=...)` 现造一批，
   不在模块级建全局对象 —— 每次请求天然隔离，也不会串台。

2. **docstring 是写给模型看的说明书**：模型靠 `description` 判断"要不要调我"。
   所以每条都写清「什么时候该用」，而不是「这个函数干什么」。

3. **返回值必须是 str**：`ToolMessage.content` 只接受字符串，
   并且要截断 —— 一条工具结果不该把 prompt 撑爆。
"""

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import local_now
from app.core.logging import get_logger
from app.domain import affinity_rules
from app.memory import episodic
from app.models import NPC, Affinity

log = get_logger(__name__)

WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")

# 工具结果进 prompt，必须限长：宁可截断，也不要让一次查询吃掉半屏上下文
MAX_RESULT_CHARS = 800

# 一轮对话里最多允许几轮「调工具 → 拿结果 → 再判断」。
# 达到上限后 agent_step 不再给模型工具，强制它开口 —— 防死循环的最后一道闸。
MAX_TOOL_ITERATIONS = 3


def _clip(text: str) -> str:
    """超过上限就截断，避免把 prompt 撑爆。"""
    if len(text) <= MAX_RESULT_CHARS:
        return text
    return text[:MAX_RESULT_CHARS] + "…（内容过长已截断）"


def _period_of_day(hour: int) -> str:
    """把小时映射成"一天中的哪一段"，让 NPC 的措辞更自然。"""
    if hour < 6:
        return "凌晨"
    if hour < 9:
        return "清晨"
    if hour < 12:
        return "上午"
    if hour < 14:
        return "中午"
    if hour < 18:
        return "下午"
    if hour < 22:
        return "晚上"
    return "深夜"


def build_tools(session: AsyncSession, *, npc_id: int, player_id: int) -> list:
    """构造本次对话可用的工具集。

    `npc_id` / `player_id` 来自 state（由 load_context 节点写入），
    工具靠它们把"查谁的记忆""和谁的关系"限定在当前这一对身上。
    """

    @tool
    async def get_time() -> str:
        """查询当前的真实时间和星期。

        当玩家问到现在几点、今天周几、是不是该下班了、外面天黑了没有这类话题时使用。
        闲聊、情绪表达、和具体时间无关的问题不要调用。
        """
        now = local_now()
        weekday = WEEKDAYS[now.weekday()]
        period = _period_of_day(now.hour)
        return _clip(f"{now:%Y-%m-%d %H:%M} {weekday}，现在是{period}")

    @tool
    async def get_town_status(npc_name: str = "") -> str:
        """查询小镇里各个 NPC 现在在哪个房间，以及他们和当前玩家关系到什么程度。

        当玩家问到某人在哪、某人在忙什么、谁跟谁熟、我们的关系怎么样时使用。
        npc_name 留空表示查询全部 NPC；给了名字则只查那一个。
        纯情绪聊天、安慰玩家时不要调用。
        """
        stmt = select(NPC).where(NPC.is_active.is_(True)).order_by(NPC.id)
        npcs = list(await session.scalars(stmt))
        if not npcs:
            return "小镇里现在一个人都没有。"

        target = npc_name.strip()
        if target:
            # 双向包含：玩家说"李四"能匹配"李四"，说"四哥"匹配不到就算找不到
            matched = [n for n in npcs if target in n.name or n.name in target]
            if not matched:
                names = "、".join(n.name for n in npcs)
                return f"小镇里没有叫「{target}」的人。现在在场的是：{names}"
            npcs = matched

        # 一次性把当前玩家和这些 NPC 的关系捞出来，避免 N+1 查询
        affinity_stmt = select(Affinity).where(
            Affinity.player_id == player_id,
            Affinity.npc_id.in_([n.id for n in npcs]),
        )
        scores = {
            row.npc_id: row.score for row in await session.scalars(affinity_stmt)
        }

        lines: list[str] = []
        for npc in npcs:
            line = f"· {npc.name}（{npc.title}）现在在{npc.location}"
            score = scores.get(npc.id)
            if score is not None:
                level = affinity_rules.level_from_score(score)
                line += f"，和你关系：{level}（{score:.0f} 分）"
            lines.append(line)

        return _clip("\n".join(lines))

    @tool
    async def search_memories(query: str) -> str:
        """检索你过去和这个玩家有关的记忆。

        当玩家提到"之前说过""上次""你还记得""我是不是跟你说过"这类旧事时使用。
        query 用玩家问题的关键词，不要照抄整句。
        和旧事无关的闲聊不要调用。
        """
        keyword = query.strip()
        if not keyword:
            return "检索内容为空，没有查到记忆。"

        hits = await episodic.recall(
            session,
            npc_id=npc_id,
            player_id=player_id,
            query=keyword,
            top_k=3,
        )
        if not hits:
            return "没有检索到相关的记忆。"

        # 只给内容，不给分数：分数是内部指标，对模型没有意义，只会干扰措辞
        return _clip("\n".join(f"- {item.content}" for item in hits))

    return [get_time, get_town_status, search_memories]