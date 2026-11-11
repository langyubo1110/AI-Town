"""对话质量评测（LLM-as-judge）+ 端到端延迟。

用法：
    python -m scripts.eval_dialogue

注意：评测期间建议停掉 worker —— 它会在后台写记忆，影响可复现性。
"""

import asyncio
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pydantic import BaseModel, Field

from app.agents.graph import get_chat_graph
from app.agents.runtime import build_config
from app.core.config import get_settings
from app.infra.cache import build_redis
from app.infra.db import build_engine, build_session_factory
from app.infra.llm import get_chat_model
from app.repos import npc_repo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "eval" / "dialogue.json"

PLAYER = "评测玩家"

SCENARIOS = [
    {"npc": "张三", "message": "你好，最近在忙什么？", "hint": "技术宅，应该聊代码或项目"},
    {"npc": "张三", "message": "你昨天说的那个 bug 修好了吗？", "hint": "承接上下文，技术口吻"},
    {"npc": "张三", "message": "我今天心情很差，想辞职", "hint": "先共情，不要立刻讲道理"},
    {"npc": "张三", "message": "1+1 等于几？", "hint": "不崩人设，别变成计算器"},
    {"npc": "李四", "message": "你觉得我们产品下一步该做什么？", "hint": "产品经理视角"},
    {"npc": "李四", "message": "帮我讲讲这个功能怎么用？", "hint": "友好、爱用比喻"},
    {"npc": "李四", "message": "谢谢你昨天帮我改需求", "hint": "热情回应，关系拉近"},
    {"npc": "王五", "message": "这个界面的颜色你觉得怎么样？", "hint": "设计师视角，谈审美"},
    {"npc": "王五", "message": "我最近在学 Rust，你觉得有用吗？", "hint": "从审美/设计角度回应，不必懂技术"},
    {"npc": "王五", "message": "我想画一只会说话的鲸鱼，你觉得怎么样？", "hint": "委婉表达审美判断"},
]


class JudgeScore(BaseModel):
    """评审输出（强制结构化）。"""

    persona: int = Field(..., ge=1, le=5, description="人设一致性")
    natural: int = Field(..., ge=1, le=5, description="承接自然度")
    brevity: int = Field(..., ge=1, le=5, description="简洁度（≤60 字为佳）")
    reason: str = Field(default="", description="一句话理由")


def build_judge_prompt(*, persona: str, message: str, reply: str) -> str:
    return f"""你是对话质量评审，给一个角色扮演 NPC 的回复打分。

【NPC 人设】{persona}
【玩家说】{message}
【NPC 回复】{reply}

【评分标准】每项 1~5 分

1) persona（人设一致性）
   5 = 口吻、职业视角完全符合人设
   3 = 基本符合，但比较泛泛
   1 = 出戏：自称 AI / 助手 / 模型，或完全不像这个人

2) natural（承接自然度）
   5 = 直接回应玩家这句话，有来有回
   3 = 沾边但不痛不痒
   1 = 答非所问

3) brevity（简洁度）
   5 = 不超过 60 字，不啰嗦
   3 = 略长但仍可读
   1 = 长篇大论

只输出 persona / natural / brevity / reason 四个字段。
"""


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(p * (len(ordered) - 1)))))
    return ordered[index]


async def main() -> None:
    settings = get_settings()
    engine = build_engine(settings.postgres_dsn, echo=False, pool_size=2)
    factory = build_session_factory(engine)
    redis = build_redis(settings.redis_url)
    graph = get_chat_graph()
    judge = get_chat_model().with_structured_output(JudgeScore, method="function_calling")

    records: list[dict] = []

    try:
        async with factory() as session:
            for index, scenario in enumerate(SCENARIOS, 1):
                npc = await npc_repo.get_by_name(session, scenario["npc"])
                if npc is None:
                    print(f"跳过（NPC 不存在）：{scenario['npc']}")
                    continue

                persona = (
                    f"{npc.name}（{npc.title}）：{npc.personality}；"
                    f"擅长 {npc.expertise}；说话风格：{npc.style}"
                )

                config = build_config(
                    session=session,
                    redis=redis,
                    thread_id=f"eval:{index}:{npc.name}",
                )

                started = time.perf_counter()
                final = await graph.ainvoke(
                    {
                        "player_name": PLAYER,
                        "npc_name": npc.name,
                        "message": scenario["message"],
                    },
                    config=config,
                )
                latency_ms = (time.perf_counter() - started) * 1000
                reply = str(final["reply"])

                try:
                    judged = await judge.ainvoke(
                        build_judge_prompt(
                            persona=persona,
                            message=scenario["message"],
                            reply=reply,
                        )
                    )
                    scores = {
                        "persona": judged.persona,
                        "natural": judged.natural,
                        "brevity": judged.brevity,
                    }
                    reason = judged.reason
                except Exception as exc:
                    scores = {"persona": 0, "natural": 0, "brevity": 0}
                    reason = f"judge 失败：{type(exc).__name__}"

                records.append(
                    {
                        "npc": npc.name,
                        "message": scenario["message"],
                        "reply": reply,
                        "hint": scenario.get("hint", ""),
                        "scores": scores,
                        "reason": reason,
                        "latency_ms": round(latency_ms),
                    }
                )

                print(
                    f"[{index}/{len(SCENARIOS)}] {npc.name} "
                    f"{latency_ms:.0f}ms  {scores['persona']}/{scores['natural']}/{scores['brevity']}"
                )

        dimensions = ["persona", "natural", "brevity"]
        summary = {}
        for dim in dimensions:
            values = [r["scores"][dim] for r in records]
            summary[dim] = {
                "mean": round(statistics.fmean(values), 3) if values else 0.0,
                "bad": sum(1 for v in values if v < 3),
            }

        latencies = [r["latency_ms"] for r in records]
        performance = {
            "runs": len(latencies),
            "p50_ms": round(statistics.median(latencies)) if latencies else 0,
            "p95_ms": round(percentile(latencies, 0.95)) if latencies else 0,
            "mean_ms": round(statistics.fmean(latencies)) if latencies else 0,
            "max_ms": max(latencies) if latencies else 0,
        }

        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(UTC).isoformat(),
                    "player": PLAYER,
                    "scenario_count": len(records),
                    "summary": summary,
                    "performance": performance,
                    "records": records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print("\n维度均分：")
        for dim in dimensions:
            print(f"  {dim:<10} {summary[dim]['mean']:.2f}  (不合格 {summary[dim]['bad']})")
        print(
            f"\n延迟：P50 {performance['p50_ms']}ms · P95 {performance['p95_ms']}ms "
            f"· 均值 {performance['mean_ms']}ms"
        )
        print(f"\n结果已写入 {OUT}")
    finally:
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())