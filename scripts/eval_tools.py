"""工具选择评测：模型该调工具时调了没有？不该调的时候有没有乱调？

用法：
    python -m scripts.eval_tools

三个指标（只在"明确用例"上统计，边界用例单独看）：
    调用准确率 = 期望与实际完全一致的比例
    漏调率     = 该调却没调
    误调率     = 不该调却调了   ← 最伤体验的那个

输出：docs/eval/tools.json，并打印表格。
"""

import asyncio
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.agents.graph import get_chat_graph
from app.agents.runtime import build_config
from app.core.config import get_settings
from app.infra.cache import build_redis
from app.infra.db import build_engine, build_session_factory

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "eval" / "tools.json"

PLAYER = "工具评测"
NPC = "张三"

TOOL_NAMES = ("get_time", "get_town_status", "search_memories")

# kind:
#   should_call      明确应该调（expect 只有一个）
#   should_not_call  明确不该调（expect == ["none"]）
#   boundary         两种都算合理（expect 是允许集合）
CASES: list[dict] = [
    # ---- 明确该调：时间 ----
    {"msg": "现在几点了？", "expect": ["get_time"], "kind": "should_call"},
    {"msg": "今天周几来着？", "expect": ["get_time"], "kind": "should_call"},
    # ---- 明确该调：小镇状态 ----
    {"msg": "李四现在在哪？", "expect": ["get_town_status"], "kind": "should_call"},
    {"msg": "王五在忙什么呢？", "expect": ["get_town_status"], "kind": "should_call"},
    # ---- 明确该调：旧事 ----
    {"msg": "你还记得我不吃什么吗？", "expect": ["search_memories"], "kind": "should_call"},
    {"msg": "我上次跟你说的那个副业项目叫什么？", "expect": ["search_memories"], "kind": "should_call"},
    # ---- 明确不该调：闲聊 / 情绪 / 常识 / 征求意见 ----
    {"msg": "今天好累啊", "expect": ["none"], "kind": "should_not_call"},
    {"msg": "哈哈哈你好搞笑", "expect": ["none"], "kind": "should_not_call"},
    {"msg": "谢谢你啊", "expect": ["none"], "kind": "should_not_call"},
    {"msg": "你觉得我该不该辞职？", "expect": ["none"], "kind": "should_not_call"},
    {"msg": "1+1 等于几？", "expect": ["none"], "kind": "should_not_call"},
    {"msg": "你是什么性格的人？", "expect": ["none"], "kind": "should_not_call"},
    {"msg": "中午吃点什么好呢", "expect": ["none"], "kind": "should_not_call"},
    {"msg": "我好烦，不想上班了", "expect": ["none"], "kind": "should_not_call"},
    # ---- 边界：两种都合理 ----
    {"msg": "这个点你还在公司？", "expect": ["get_time", "none"], "kind": "boundary"},
    {"msg": "大家现在都在忙什么？", "expect": ["get_town_status", "none"], "kind": "boundary"},
    {"msg": "你还记得我们第一次见面吗？", "expect": ["search_memories", "none"], "kind": "boundary"},
]


def signature(trace: list[dict]) -> str:
    """把工具轨迹压成一个可比较的字符串：none / get_time / multi:a,b"""
    names = [str(step["call"].get("name")) for step in trace]
    if not names:
        return "none"
    if len(names) == 1:
        return names[0]
    return "multi:" + ",".join(names)


def leaks_tool_name(reply: str) -> bool:
    """回复里出现工具名或"根据工具"这类词，就算出戏。"""
    if "根据工具" in reply or "工具返回" in reply:
        return True
    return any(name in reply for name in TOOL_NAMES)


async def main() -> None:
    settings = get_settings()
    engine = build_engine(settings.postgres_dsn, echo=False, pool_size=2)
    factory = build_session_factory(engine)
    redis = build_redis(settings.redis_url)
    graph = get_chat_graph()

    records: list[dict] = []

    try:
        for index, case in enumerate(CASES, 1):
            async with factory() as session:
                config = build_config(
                    session=session,
                    redis=redis,
                    thread_id=f"eval-tool:{index}",
                    user_id=PLAYER,
                )
                started = time.perf_counter()
                try:
                    final = await graph.ainvoke(
                        {"player_name": PLAYER, "npc_name": NPC, "message": case["msg"]},
                        config=config,
                    )
                except Exception as exc:
                    print(f"[{index:02d}] {case['msg']}  -> 执行失败 {type(exc).__name__}")
                    records.append(
                        {
                            "message": case["msg"],
                            "kind": case["kind"],
                            "expect": case["expect"],
                            "actual": "error",
                            "calls": [],
                            "ok": False,
                            "reply": "",
                            "leak": False,
                            "latency_ms": 0,
                        }
                    )
                    continue
                latency_ms = (time.perf_counter() - started) * 1000

            trace = final.get("tool_trace") or []
            actual = signature(trace)
            reply = str(final.get("reply") or "")
            calls = [
                {"name": step["call"].get("name"), "args": step["call"].get("args")}
                for step in trace
            ]

            is_strict = case["kind"] != "boundary"
            ok = actual in case["expect"]

            records.append(
                {
                    "message": case["msg"],
                    "kind": case["kind"],
                    "expect": case["expect"],
                    "actual": actual,
                    "calls": calls,
                    "ok": ok,
                    "reply": reply,
                    "leak": leaks_tool_name(reply),
                    "latency_ms": round(latency_ms),
                }
            )

            mark = "✅" if ok else ("⚠️" if not is_strict else "❌")
            print(f"[{index:02d}] {mark} {case['msg']}")
            print(f"      期望 {case['expect']} → 实际 {actual}  ({latency_ms:.0f}ms)")

        strict = [r for r in records if r["kind"] != "boundary"]
        boundary = [r for r in records if r["kind"] == "boundary"]

        should_call = [r for r in strict if r["kind"] == "should_call"]
        should_not = [r for r in strict if r["kind"] == "should_not_call"]

        accuracy = sum(1 for r in strict if r["ok"]) / len(strict) if strict else 0.0
        miss = sum(1 for r in should_call if r["actual"] == "none")
        miss_rate = miss / len(should_call) if should_call else 0.0
        false_call = sum(1 for r in should_not if r["actual"] != "none")
        false_rate = false_call / len(should_not) if should_not else 0.0

        multi = sum(1 for r in records if r["actual"].startswith("multi:"))
        leaks = sum(1 for r in records if r["leak"])
        latencies = [r["latency_ms"] for r in records if r["latency_ms"]]

        summary = {
            "strict_cases": len(strict),
            "boundary_cases": len(boundary),
            "accuracy": round(accuracy, 4),
            "miss_count": miss,
            "miss_rate": round(miss_rate, 4),
            "false_call_count": false_call,
            "false_call_rate": round(false_rate, 4),
            "boundary_ok": sum(1 for r in boundary if r["ok"]),
            "multi_tool_turns": multi,
            "reply_leaks": leaks,
            "latency_p50_ms": round(statistics.median(latencies)) if latencies else 0,
            "latency_max_ms": max(latencies) if latencies else 0,
        }

        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(UTC).isoformat(),
                    "npc": NPC,
                    "player": PLAYER,
                    "summary": summary,
                    "records": records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print("\n" + "=" * 46)
        print(f"明确用例 {len(strict)} 条 | 边界用例 {len(boundary)} 条")
        print(f"  调用准确率 : {accuracy:.1%}")
        print(f"  漏调率     : {miss_rate:.1%}  ({miss}/{len(should_call)})")
        print(f"  误调率     : {false_rate:.1%}  ({false_call}/{len(should_not)})")
        print(f"  多工具轮次 : {multi}")
        print(f"  回复漏工具名: {leaks}")
        print(f"  延迟 P50   : {summary['latency_p50_ms']} ms")
        print(f"  边界可接受 : {summary['boundary_ok']}/{len(boundary)}")
        print(f"\n结果已写入 {OUT}")
    finally:
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())