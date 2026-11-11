"""给评测玩家灌入固定的记忆集合（幂等）。

除了内容，还会按 `age_hours` 把 `created_at` 往前拨 ——
否则所有记忆的"年龄"完全一样，recency 因子就没有方差，评测也就测不出它。

用法：
    python -m scripts.eval_seed_memories
"""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.infra.db import build_engine, build_session_factory
from app.memory import episodic
from app.models import Memory
from app.repos import npc_repo, player_repo

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "data" / "eval" / "memory_cases.json"


async def main() -> None:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    settings = get_settings()
    engine = build_engine(settings.postgres_dsn, echo=False, pool_size=2)
    factory = build_session_factory(engine)

    try:
        async with factory() as session:
            npc = await npc_repo.get_by_name(session, spec["npc_name"])
            if npc is None:
                raise SystemExit(f"NPC {spec['npc_name']} 不存在，先跑 python -m scripts.seed")

            player = await player_repo.get_or_create_by_name(session, spec["player_name"])
            await session.flush()

            # 幂等：重复跑不会越积越多
            await session.execute(
                delete(Memory).where(
                    Memory.player_id == player.id,
                    Memory.npc_id == npc.id,
                )
            )
            await session.flush()

            for item in spec["memories"]:
                await episodic.remember(
                    session,
                    npc_id=npc.id,
                    player_id=player.id,
                    turn_text=item["content"],
                    facts=[],
                    importance=float(item["importance"]),
                )
            await session.flush()

            # 把时间往前拨，让 recency 有方差
            rows = (
                await session.scalars(
                    select(Memory).where(
                        Memory.player_id == player.id,
                        Memory.npc_id == npc.id,
                    )
                )
            ).all()
            by_content = {row.content: row for row in rows}
            now = datetime.now(UTC)

            for item in spec["memories"]:
                row = by_content.get(item["content"])
                if row is None:
                    continue
                age = float(item.get("age_hours", 1))
                row.created_at = now - timedelta(hours=age)
                row.last_access_at = None

            await session.commit()

            ages = [float(i.get("age_hours", 1)) for i in spec["memories"]]
            print(
                f"已为「{spec['player_name']}」×「{npc.name}」写入 {len(spec['memories'])} 条记忆，"
                f"年龄跨度 {min(ages):.0f}h ~ {max(ages):.0f}h"
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())