"""NPC 自主行为：定时让小镇自己动起来。

两层行为：
1. ★ 计划驱动（本次新增）：每个 NPC 每天有一份 3~4 步的计划，
   到点就执行一步 —— 换个房间、写一条事件、推给前端。这是"有目的的自主"。
2. 自由活动（原有）：没有到点的计划时，随机找两个 NPC 聊两句。

设计要点：
- 生产者/消费者分离：ticker 只改世界状态和投递任务，LLM 对话交给 worker 消费循环
- Redis 分布式锁：多 worker 下同一时刻只有一个人在 tick
- 背压检查：pending 太多就不再生新任务
- 每次 tick 最多推进一件事：避免同一秒里全小镇一起动
"""

import asyncio
import random
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select

from app.agents import plans
from app.core.clock import local_now
from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain import plans as plan_rules
from app.infra.broadcast import publish_event
from app.models import Event, Player
from app.repos import event_repo, npc_repo
from app.worker.streams import GROUP, STREAM, publish

log = get_logger(__name__)

LOCK_KEY = "aitown:lock:npc_tick"

# 计划之外的自由闲聊话题
TOPICS = [
    "最近小镇里有什么新鲜事",
    "多智能体系统到底该怎么设计",
    "前端和后端哪个更累",
    "新人第一天上班该注意什么",
    "怎么才能少写 bug",
    "周末去哪儿放松一下",
]

# 计划执行产生的事件类型（前端可以据此加图标）
PLAN_EVENT = "plan_step"


async def _observer_player_id(session) -> int | None:
    """找一个"在场"的玩家，当作事件归属者。

    events.player_id 是 NOT NULL + 外键，而 NPC 自己活动时没有真实玩家。
    这里借"最近有事件的玩家"（最可能还开着页面），退而求其次取第一个活跃玩家。
    """
    player_id = await session.scalar(
        select(Event.player_id).order_by(Event.id.desc()).limit(1)
    )
    if player_id is not None:
        return int(player_id)

    player_id = await session.scalar(
        select(Player.id)
        .where(Player.is_active.is_(True))
        .order_by(Player.id)
        .limit(1)
    )
    return int(player_id) if player_id is not None else None


async def _pick_participants(session_factory) -> tuple[str, str, int] | None:
    """挑两个 NPC + 一个观察者玩家。数据不够就返回 None。"""
    async with session_factory() as session:
        npcs = await npc_repo.list_active(session)
        if len(npcs) < 2:
            return None
        npc_a, npc_b = random.sample(npcs, 2)

        player_id = await _observer_player_id(session)
        if player_id is None:
            return None
        return npc_a.name, npc_b.name, player_id


async def _advance_one_plan(redis: Redis, session_factory, now: datetime) -> bool:
    """推进"最早到点"的那一步计划。返回是否真的推进了。"""
    async with session_factory() as session:
        npcs = await npc_repo.list_active(session)
        if not npcs:
            return False

        player_id = await _observer_player_id(session)

        for npc in npcs:
            try:
                steps = await plans.ensure_plan(redis, npc=npc, now=now)
            except Exception as exc:
                log.warning(
                    "plan_ensure_failed",
                    npc=npc.name,
                    error=type(exc).__name__,
                    detail=str(exc)[:200],
                )
                continue

            # 先清理"过期太久"的步骤：worker 停了一上午，16:00 启动时
            # 不该去补做 09:30 的事，否则事件时间线会错乱
            steps, expired = plan_rules.expire_stale(steps, now)
            #存在过期的任务
            if expired:
                await plans.save_plan(
                    redis, npc_id=npc.id, day=now.date(), steps=steps
                )
                log.info("plan_steps_expired", npc=npc.name, count=expired)

            index = plan_rules.due_step(steps, now)
            if index is None:
                continue

            step = steps[index]

            # ★ 真的把 NPC 挪到计划里的房间（前端 setNpcs 按 location 摆位置）
            npc.location = step["room"]

            created = None
            if player_id is not None:
                created = await event_repo.create(
                    session,
                    player_id=player_id,
                    npc_id=npc.id,
                    event_type=PLAN_EVENT,
                    summary=f"{npc.name}去{step['room']}{step['goal']}",
                    payload={
                        "npc_name": npc.name,
                        "at": step["at"],
                        "goal": step["goal"],
                        "room": step["room"],
                        "trigger": "plan",
                    },
                )
                await session.flush()
            else:
                # 没有玩家就没有事件归属者（events.player_id 是 NOT NULL），
                # 但位置和计划照常推进 —— 页面靠 /api/town/plans 轮询也能看到。
                # 这个分支在"首次部署、还没人打开过页面"时一定会走到。
                log.warning(
                    "plan_step_without_player",
                    npc=npc.name,
                    hint="库里还没有玩家，先跑 python -m scripts.seed",
                )

            # 先落库，再更新计划里的状态，保存到对应的redis里面
            await plans.save_plan(
                redis,
                npc_id=npc.id,
                day=now.date(),
                steps=plan_rules.mark_done(steps, index),
            )
            await session.commit()

            # commit 之后才推（和 worker 里同一条规矩：推出去的库里一定查得到）
            if created is not None:
                await publish_event(
                    redis,
                    player_id=player_id,
                    event={
                        "id": created.id,
                        "event_type": created.event_type,
                        "npc_id": created.npc_id,
                        "summary": created.summary,
                        "payload": created.payload,
                        "created_at": datetime.now(UTC).isoformat(),
                    },
                )
            log.info(
                "plan_step_done",
                npc=npc.name,
                at=step["at"],
                goal=step["goal"],
                room=step["room"],
                event_id=created.id if created is not None else None,
            )
            return True

    return False


async def tick_once(redis: Redis, session_factory) -> None:
    """一轮 tick：加锁 → 背压 → 优先推进计划 → 否则自由闲聊。"""
    settings = get_settings()
    now = local_now()

    # 1) 分布式锁：同一时刻只允许一个 worker 触发
    #    TTL 略小于 tick 间隔，保证下一轮一定能拿到
    acquired = await redis.set(
        LOCK_KEY, "1", nx=True, ex=max(5, settings.npc_tick_seconds - 5)
    )
    if not acquired:
        log.debug("tick_skipped", reason="lock")
        return

    # 2) 背压：pending 太多说明处理不过来，这一轮就不再生
    #下游忙不过来时，上游主动减速 这是流控的基本手段
    info = await redis.xpending(STREAM, GROUP)
    if isinstance(info, dict):
        backlog = int(info.get("pending") or 0)
    else:
        # 兼容：某些版本/参数组合下返回的是列表
        backlog = int(info[0]) if info else 0
    if backlog > settings.npc_tick_max_backlog:
        log.warning("tick_skipped", reason="backlog", pending=backlog)
        return

    # 3) ★ 优先推进计划：有人的计划到点了就做那件事，本轮不再闲聊
    if await _advance_one_plan(redis, session_factory, now):
        return

    # 4) 没有到点的计划 → 自由活动（原有的随机闲聊）
    picked = await _pick_participants(session_factory)
    if picked is None:
        # 这条原来是 debug，结果"首次部署后小镇一动不动"完全不可见。提到 info。
        log.info(
            "tick_skipped",
            reason="not_enough_data",
            hint="需要 2 个以上 NPC 和 1 个玩家（python -m scripts.seed）",
        )
        return
    npc_a, npc_b, player_id = picked
    topic = random.choice(TOPICS)


    msg_id = await publish(
        redis,
        event="npc_chat_requested",
        payload={
            "player_id": player_id,
            "npc_a": npc_a,
            "npc_b": npc_b,
            "topic": topic,
            "turns": 2,
            "trigger": "auto",
        },
    )
    log.info(
        "tick_fired",
        npc_a=npc_a,
        npc_b=npc_b,
        topic=topic,
        msg_id=msg_id,
        pending=backlog,
    )


async def run_ticker(redis: Redis, session_factory) -> None:
    """常驻循环。由 worker 以 asyncio.Task 方式启动。"""
    settings = get_settings()
    if not settings.npc_tick_enabled:
        log.info("ticker_disabled")
        return

    interval = max(10, settings.npc_tick_seconds)
    log.info("ticker_started", interval=interval)

    while True:
        # 抖动：避免多实例在同一毫秒触发
        await asyncio.sleep(interval + random.uniform(0, 3))
        try:
            await tick_once(redis, session_factory)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception(
                "tick_failed",
                error=type(exc).__name__,
                detail=repr(exc)[:300],
            )