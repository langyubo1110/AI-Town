"""独立验证长期记忆的写入与召回。"""

import asyncio
from app.core.config import get_settings
from app.infra.db import build_engine, build_session_factory
from app.memory import episodic


async def main() -> None:
    settings = get_settings()
    engine = build_engine(settings.postgres_dsn, echo=False, pool_size=2)
    factory = build_session_factory(engine)

    async with factory() as session:
        # 1. 写入
        await episodic.remember(
            session,
            npc_id=1,
            player_id=1,
            turn_text="玩家说「我在学 Rust，本职是前端」，我回答「那挺互补的」",
            facts=["玩家是前端工程师，正在学 Rust"],
            importance=0.8,
        )
        await session.commit()
        print("✅ 写入完成")

        # 2. 召回（query 和原文措辞不同，考语义而不是字面）
        results = await episodic.recall(
            session, npc_id=1, player_id=1, query="我之前跟你说过我在学什么技术？"
        )
        for c in results:
            print(f"  score={c.relevance:.3f}/{c.importance:.2f}/{c.age_hours:.4f}h  {c.content}")

    await engine.dispose()


asyncio.run(main())