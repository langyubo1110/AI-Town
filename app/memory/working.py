"""工作记忆：Redis 短期对话缓冲。"""

from redis.asyncio import Redis

from app.core.logging import get_logger

log = get_logger(__name__)

MAX_TURNS = 5              # 保留最近 5 轮
TTL_SECONDS = 2 * 3600     # 2 小时过期


def _key(npc_id: int, player_id: int) -> str:
    """命名空间化，避免和其他 key 冲突。"""
    return f"aitown:wm:{npc_id}:{player_id}"


async def append_turn(redis: Redis, *, npc_id: int, player_id: int, text: str) -> None:
    """追加一轮对话。"""
    #获取键名
    key = _key(npc_id, player_id)
    #创建管道
    pipe = redis.pipeline()
    pipe.lpush(key, text)               # 头插法
    pipe.ltrim(key, 0, MAX_TURNS - 1)   # 只保留前 5 条
    pipe.expire(key, TTL_SECONDS)       # 每次对话都续期
    await pipe.execute()                # 一次往返发 3 条命令


async def recent_turns(redis: Redis, *, npc_id: int, player_id: int) -> list[str]:
    """取最近几轮（按时间正序）。"""
    try:
        items = await redis.lrange(_key(npc_id, player_id), 0, MAX_TURNS - 1)
    except Exception as exc:
        log.warning(
            "working_memory_read_failed",
            error=type(exc).__name__,
            detail=str(exc)[:200],
        )
        return []
    return list(reversed(items))        # LPUSH 导致是倒序，翻回来