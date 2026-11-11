"""用 LLM 给 NPC 生成"今日计划"，并负责在 Redis 里存取。

分工：
    domain/plans.py  纯规则（清洗、排序、判断到点）—— 可单测
    本文件            LLM 生成 + Redis 存取 —— 需要外部依赖

为什么计划存 Redis 而不是新建一张表：
    计划的生命周期是"一天"，第二天就该重新生成。给它建表 + 迁移，
    收益（可查询历史计划）远小于成本。真要看历史，做完的事都写进 events 了。
"""

import json
from datetime import date, datetime

from pydantic import BaseModel, Field
from redis.asyncio import Redis

from app.core.logging import get_logger
from app.domain import plans as plan_rules
from app.infra.llm import get_chat_model

log = get_logger(__name__)


class PlanStepDraft(BaseModel):
    """LLM 输出的一步（结构化输出的 schema）。"""

    at: str = Field(..., description="开始时间，24 小时制 HH:MM，例如 09:30")
    goal: str = Field(..., description="要做的事，20 字以内，要有具体动作")
    room: str = Field(..., description="在哪个房间：工位区 / 会议室 / 休息区")

class DailyPlanDraft(BaseModel):
    """一天的完整计划。"""

    steps: list[PlanStepDraft] = Field(
        ..., description="3~4 步，按时间从早到晚排列"
    )

def build_plan_prompt(
    *,
    name: str,
    title: str,
    personality: str,
    expertise: str,
    location: str,
    today: str,
) -> str:
    return f"""你是{name}，一名{title}。

【人设】{personality}
【专长】{expertise}
【平时待的地方】{location}

今天是 {today}。请给自己安排**今天**的 3~4 件事。

【要求】
1. 时间在 09:00 ~ 18:00 之间，按时间从早到晚排
2. 每件事 20 字以内，要有具体动作（"重构登录模块""找李四对齐需求"），
   不要写"认真工作"这种空话
3. 必须体现你的职业视角（{title}）：工程师写代码和 code review，
   产品经理开会对需求，设计师调界面
4. room 只能从这三个里选：工位区 / 会议室 / 休息区
5. 至少留一件在「休息区」的事（喝咖啡、散步、发会儿呆），别把自己排满
"""

#生成任务
async def generate_plan(*, npc, today: str) -> list[dict]:
    """调一次 LLM 生成计划，清洗后返回。失败返回空列表（不抛）。"""
    prompt = build_plan_prompt(
        name=npc.name,
        title=npc.title,
        personality=npc.personality,
        expertise=npc.expertise,
        location=npc.location,
        today=today,
    )
    try:
        llm = get_chat_model().with_structured_output(
            #用 OpenAI 的 function calling 机制来实现结构化输出
            DailyPlanDraft, method="function_calling"
        )
        draft = await llm.ainvoke(prompt)
        #清洗任务
        steps = plan_rules.normalize_steps([s.model_dump() for s in draft.steps])
        log.info("plan_generated", npc=npc.name, steps=len(steps))
        return steps
    except Exception as exc:
        log.warning(
            "plan_generate_failed",
            npc=npc.name,
            error=type(exc).__name__,
            detail=str(exc)[:200],
        )
        return []

async def load_plan(redis: Redis, *, npc_id: int, day: date) -> list[dict]:
    """读今天的计划；没有就返回空列表。"""
    raw = await redis.get(plan_rules.plan_key(npc_id, day))
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("plan_decode_failed", npc_id=npc_id, day=day.isoformat())
        return []
    return data if isinstance(data, list) else []

#保存计划
async def save_plan(redis: Redis, *, npc_id: int, day: date, steps: list[dict]) -> None:
    await redis.set(
        plan_rules.plan_key(npc_id, day),
        json.dumps(steps, ensure_ascii=False),
        ex=plan_rules.PLAN_TTL_SECONDS,
    )

async def ensure_plan(redis: Redis, *, npc, now: datetime) -> list[dict]:
    """保证今天有计划：有就读出来，没有就生成一份并落 Redis。

    懒生成：不靠"每天 00:00 定时任务"，而是"第一次需要时才生成"。
    好处是服务重启/停机都不会漏 —— 下一个 tick 自然补上。
    """
    day = now.date()
    steps = await load_plan(redis, npc_id=npc.id, day=day)
    if steps:
        return steps

    steps = await generate_plan(npc=npc, today=now.strftime("%Y-%m-%d"))
    if steps:
        await save_plan(redis, npc_id=npc.id, day=day, steps=steps)
    return steps