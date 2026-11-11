"""Redis Stream 消费者：后台 worker 的主循环。"""

import asyncio
import os
import socket

from redis.asyncio import Redis

from app.core.logging import get_logger
from app.infra.broadcast import publish_event
from app.worker.handlers import Broadcast, handle_npc_chat
from app.worker.streams import GROUP, STREAM, decode, ensure_group

log = get_logger(__name__)

# consumer 标识"一个 worker 身份"，不是"一次进程启动"。
#需要保证名字变化不大，这样在pending阶段的未完成任务才能被领走
CONSUMER = os.getenv("WORKER_NAME") or f"worker-{socket.gethostname()}"

BLOCK_MS = 5000      # 最长阻塞 5 秒，保证能响应退出信号
BATCH = 10


async def handle(session, *, event: str, payload: dict, msg_id: str) -> list[Broadcast]:
    """按事件类型分发。返回「提交之后要广播」的事件列表。"""
    if event == "npc_chat_requested":
        return await handle_npc_chat(session, payload=payload, msg_id=msg_id)

    # 未知事件：记一笔就 ACK 掉，不要让它永远卡在 pending
    log.warning("unknown_event", evt=event, msg_id=msg_id)
    return []


async def _process(redis: Redis, session_factory, msg_id: str, fields: dict[str, str]) -> None:
    """处理一条消息：一个 session = 一个事务。"""
    event, payload = decode(fields)
    broadcasts: list[Broadcast] = []

    try:
        async with session_factory() as session:
            broadcasts = await handle(session, event=event, payload=payload, msg_id=msg_id)
            await session.commit()          # ← 先落库
    except Exception as exc:
        # 不 ACK → 留在 pending 等重试
        log.error(
            "message_failed",
            msg_id=msg_id,
            evt=event,
            error=type(exc).__name__,
            detail=str(exc)[:300],
        )
        return

    # ← 提交成功后才广播：先落库、再推送、最后 ACK
    for item in broadcasts:
        await publish_event(redis, player_id=item.player_id, event=item.event)

    await redis.xack(STREAM, GROUP, msg_id)
    log.debug("message_acked", msg_id=msg_id)


async def _recover_pending(redis: Redis, session_factory) -> int:
    """启动时先处理自己上次遗留的 pending（至少一次语义的关键）。"""
    resp = await redis.xreadgroup(
        #0：读自己 PEL 里的旧消息
        GROUP, CONSUMER, {STREAM: "0"}, count=100, block=None
    )
    count = 0
    for _stream, messages in resp or []:
        for msg_id, fields in messages:
            log.info("recovering_pending", msg_id=msg_id)
            await _process(redis, session_factory, msg_id, fields)
            count += 1
    return count


async def run(redis: Redis, session_factory) -> None:
    await ensure_group(redis)
    log.info("worker_started", consumer=CONSUMER, stream=STREAM, group=GROUP)

    recovered = await _recover_pending(redis, session_factory)
    if recovered:
        log.info("pending_recovered", count=recovered)

    while True:
        try:
            resp = await redis.xreadgroup(
                GROUP, CONSUMER, {STREAM: ">"}, count=BATCH, block=BLOCK_MS
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("xreadgroup_failed", error=type(exc).__name__, detail=str(exc)[:200])
            await asyncio.sleep(1)
            continue

        if not resp:
            continue

        for _stream, messages in resp:
            for msg_id, fields in messages:
                try:
                    await _process(redis, session_factory, msg_id, fields)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    # 兜底：连"错误处理"都出错时，worker 也不能死
                    log.error(
                        "process_crashed",
                        msg_id=msg_id,
                        error=type(exc).__name__,
                        detail=str(exc)[:300],
                    )