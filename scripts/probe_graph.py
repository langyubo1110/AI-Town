"""进程内探针：直接调图，看 Memory 到底有没有进入 session。

绕开 HTTP / uvicorn / --reload，杜绝"跑的是旧代码"这类干扰。
"""

import asyncio
import sys

from sqlalchemy import func, select

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.agents.graph import get_chat_graph
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.infra.cache import build_redis
from app.infra.db import build_engine, build_session_factory
from app.models import Memory


async def count(session) -> int:
    return await session.scalar(select(func.count()).select_from(Memory))


async def main() -> None:
    setup_logging("DEBUG", json_output=False)      # 让节点的 log 打出来

    settings = get_settings()
    print(f"DSN = {settings.postgres_dsn}")          # ← 先确认连的是哪个库
    print(f"EMBED = {settings.embed_model} / {settings.embed_base_url}\n")

    engine = build_engine(settings.postgres_dsn, echo=False, pool_size=2)
    factory = build_session_factory(engine)
    redis = build_redis(settings.redis_url)

    async with factory() as session:
        print(f"[1] 调用图之前 memories = {await count(session)}")

        final = await get_chat_graph().ainvoke(
            {
                "player_name": "小明",
                "npc_name": "张三",
                "message": "我叫小明，我是前端工程师，最近在学 Rust",
                # "session": session,
                # "redis": redis,
            }
            ,config={"configurable": {"session": session, "redis": redis}},
        )

        print(f"\n[2] reply      = {final['reply'][:60]}")
        print(f"[3] facts      = {final.get('facts')}")
        print(f"[4] importance = {final.get('importance')}")
        print(f"[5] delta      = {final.get('delta')}")

        # ★ 最关键的一行：Memory 对象到底有没有被 add 进 session
        print(f"\n[6] session.new 里的对象数 = {len(session.new)}")
        for obj in session.new:
            content = getattr(obj, "content", "")
            print(f"      + {type(obj).__name__}: {content[:45]}")

        # 同 session 内可见（autoflush 会真的发 INSERT）
        print(f"[7] commit 之前，本 session 内 memories = {await count(session)}")

        await session.commit()                       # 模拟 persist

    async with factory() as session:
        print(f"[8] commit 之后，新 session 里 memories = {await count(session)}")

    await redis.aclose()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())