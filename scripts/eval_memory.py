"""检索质量评测：三因子 vs 纯向量的消融实验。

用法：
    python -m scripts.eval_seed_memories   # 先灌固定的记忆集合（含时间跨度）
    python -m scripts.eval_memory

设计要点：
- 一次粗排（top-20 候选集与权重无关），多种权重复用同一批候选 → 公平对比
- 每个 case 之后 rollback，撤销 access_count 变化，保证 case 之间互不影响
- 支持自定义半衰期，用来验证"recency 到底该衰减多快"
"""

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import get_settings
from app.infra.db import build_engine, build_session_factory
from app.memory import episodic, ranking
from app.repos import npc_repo, player_repo

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "data" / "eval" / "memory_cases.json"
OUT = ROOT / "docs" / "eval" / "memory.json"

TOP_K = 5

# name, relevance, recency, importance, 半衰期(小时)
CONFIGS: list[dict] = [
    {"name": "pure_vector", "w": (1.0, 0.0, 0.0)},
    {"name": "with_recency", "w": (0.6, 0.4, 0.0)},
    {"name": "with_importance", "w": (0.6, 0.0, 0.4)},
    {"name": "full_138h", "w": (0.5, 0.3, 0.2)},
    {"name": "importance_heavy", "w": (0.3, 0.3, 0.4)},
    # 下面两个是"调参后"的候选：把 recency 变成软信号
    {"name": "gentle_recency", "w": (0.85, 0.05, 0.10)},
    {"name": "long_half_life", "w": (0.5, 0.3, 0.2), "half_life": 720.0},
]


def rank_with(candidates, config: dict):
    w_rel, w_rec, w_imp = config["w"]
    half_life = float(config.get("half_life", ranking.HALF_LIFE_HOURS))

    previous = ranking.HALF_LIFE_HOURS
    ranking.HALF_LIFE_HOURS = half_life
    try:
        ordered = sorted(
            candidates,
            key=lambda c: ranking.score_with(
                c, w_relevance=w_rel, w_recency=w_rec, w_importance=w_imp
            ),
            reverse=True,
        )
    finally:
        ranking.HALF_LIFE_HOURS = previous

    return ordered[:TOP_K]


async def main() -> None:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    settings = get_settings()
    engine = build_engine(settings.postgres_dsn, echo=False, pool_size=2)
    factory = build_session_factory(engine)

    stats = {c["name"]: {"hits": 0, "rr": 0.0, "misses": []} for c in CONFIGS}
    total = 0

    try:
        async with factory() as session:
            npc = await npc_repo.get_by_name(session, spec["npc_name"])
            if npc is None:
                raise SystemExit(f"NPC {spec['npc_name']} 不存在")
            player = await player_repo.get_or_create_by_name(session, spec["player_name"])
            await session.commit()
            npc_id, player_id = npc.id, player.id

            for case in spec["cases"]:
                total += 1
                candidates = await episodic.recall(
                    session,
                    npc_id=npc_id,
                    player_id=player_id,
                    query=case["query"],
                    top_k=episodic.RECALL_K,
                )
                # 撤销本次 recall 对 access_count / last_access_at 的改动
                await session.rollback()

                for config in CONFIGS:
                    name = config["name"]
                    if not candidates:
                        stats[name]["misses"].append(
                            {"query": case["query"], "expect": case["expect"], "why": "无候选"}
                        )
                        continue

                    ranked = rank_with(candidates, config)
                    position = next(
                        (
                            i + 1
                            for i, item in enumerate(ranked)
                            if case["expect"] in item.content
                        ),
                        0,
                    )
                    if position:
                        stats[name]["hits"] += 1
                        stats[name]["rr"] += 1.0 / position
                    else:
                        stats[name]["misses"].append(
                            {
                                "query": case["query"],
                                "expect": case["expect"],
                                "kind": case.get("kind", ""),
                            }
                        )

        results = []
        for config in CONFIGS:
            name = config["name"]
            data = stats[name]
            w_rel, w_rec, w_imp = config["w"]
            results.append(
                {
                    "name": name,
                    "weights": {"relevance": w_rel, "recency": w_rec, "importance": w_imp},
                    "half_life_hours": float(
                        config.get("half_life", ranking.HALF_LIFE_HOURS)
                    ),
                    "hit_at_5": round(data["hits"] / total, 4) if total else 0.0,
                    "mrr": round(data["rr"] / total, 4) if total else 0.0,
                    "misses": data["misses"],
                }
            )

        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(UTC).isoformat(),
                    "case_count": total,
                    "top_k": TOP_K,
                    "configs": results,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(f"\n测试集 {total} 条 · Top-{TOP_K}\n")
        print(f"{'配置':<20}{'Hit@5':>8}{'MRR':>8}{'半衰期':>10}")
        print("-" * 48)
        for item in results:
            print(
                f"{item['name']:<20}{item['hit_at_5']:>8.3f}"
                f"{item['mrr']:>8.3f}{item['half_life_hours']:>9.0f}h"
            )
        print(f"\n结果已写入 {OUT}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())