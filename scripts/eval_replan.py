"""重规划评测：replan() 产出的计划合不合法、是否真的"排得下"。

用法：
    python -m scripts.eval_replan

为什么需要这个评测：
    重规划是"LLM 建议 + 系统校验 + 确定性兜底"三层结构。
    单测只能验证兜底算法（redistribute）正确，验证不了 LLM 那条路 ——
    而 LLM 才是真正在做调度的那一层。

检查四项（任何一项不过就算失败）：
    1. 数量一致        重排后步骤数必须和原来相同（不能悄悄丢掉事情）
    2. 落在窗口内      每个时间都在 [现在+10min, 下班] 之间
    3. 单调不减        按顺序时间不能倒退
    4. 状态重置        status 必须回到 pending
"""

import asyncio
import json
import sys
from datetime import datetime
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.agents import plans as plan_agent
from app.domain import plans as plan_rules

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "eval" / "replan.json"

NPC = SimpleNamespace(name="张三", title="Python工程师")

# (now, 未完成的 goal 列表)
CASES: list[dict] = [
    {"now": datetime(2026, 11, 15, 9, 5), "goals": ["整理需求文档", "重构调度器"]},
    {"now": datetime(2026, 11, 15, 10, 30), "goals": ["code review PR", "写单测", "对齐接口"]},
    {"now": datetime(2026, 11, 15, 11, 40), "goals": ["吃午饭", "复盘昨天的故障"]},
    {
        "now": datetime(2026, 11, 15, 14, 0),
        "goals": ["评审新版原型", "更新排期", "和测试对齐用例"],
    },
    {"now": datetime(2026, 11, 15, 15, 30), "goals": ["精修登录页视觉稿"]},
    {"now": datetime(2026, 11, 15, 16, 20), "goals": ["发版本", "写发布说明"]},
    {"now": datetime(2026, 11, 15, 17, 40), "goals": ["收尾", "整理明天的待办"]},
    {
        "now": datetime(2026, 11, 15, 19, 10),
        "goals": ["补看今天的告警", "喝杯咖啡"],
    },
    {
        "now": datetime(2026, 11, 15, 9, 0),
        "goals": ["a", "b", "c", "d", "e"],
    },
    {
        "now": datetime(2026, 11, 15, 12, 50),
        "goals": ["把多智能体调度模块的消息队列换成 Stream", "补调度器的超时重试"],
    },
]


def validate(result: list[dict], *, start: str, end: str, count: int) -> list[str]:
    """返回问题列表；空列表表示合格。"""
    problems: list[str] = []
    if len(result) != count:
        problems.append(f"数量 {len(result)}≠{count}")

    times = [step.get("at", "") for step in result]
    for at in times:
        if not (start <= at <= end):
            problems.append(f"{at} 不在 {start}~{end}")
            break

    if times != sorted(times):
        problems.append("时间不单调")

    if any(step.get("status") != "pending" for step in result):
        problems.append("status 未重置")

    return problems


def min_gap_minutes(times: list[str]) -> int:
    """相邻两步的最小间隔（分钟）。用来判断"是不是全塞在同一分钟"。"""
    if len(times) < 2:
        return -1
    minutes = []
    for at in times:
        moment = plan_rules.parse_hhmm(at)
        if moment is None:
            return -1
        minutes.append(moment.hour * 60 + moment.minute)
    # 注意不能加 strict=True：两个序列长度本来就差 1
    return min(b - a for a, b in pairwise(minutes))


async def main() -> None:
    rows: list[dict] = []
    passed = 0

    print(f"{'现在':<7}{'步数':>4}  {'窗口':<12}{'结果':>6}{'最小间隔':>9}  说明")
    print("-" * 72)

    for case in CASES:
        now: datetime = case["now"]
        goals: list[str] = case["goals"]
        steps = [
            {"at": "09:00", "goal": goal, "room": "工位区", "status": "missed"}
            for goal in goals
        ]

        window_start, window_end = plan_rules.plan_window(now)
        result = await plan_agent.replan(npc=NPC, steps=steps, now=now)
        problems = validate(
            result, start=window_start, end=window_end, count=len(goals)
        )

        times = [step["at"] for step in result]
        gap = min_gap_minutes(times)

        # 和"纯均分"对比：完全一致说明 LLM 那路没生效（走了兜底）
        fallback = plan_rules.redistribute(steps, start=window_start, end=window_end)
        used_fallback = times == [step["at"] for step in fallback]

        ok = not problems
        passed += 1 if ok else 0

        note = "兜底" if used_fallback else "LLM"
        if problems:
            note = "；".join(problems)

        print(
            f"{now:%H:%M}  {len(goals):>4}  {window_start}~{window_end:<6}"
            f"{'✓' if ok else '✗':>4}{gap:>9}  {note}"
        )
        rows.append(
            {
                "now": now.strftime("%H:%M"),
                "goals": goals,
                "window": f"{window_start}~{window_end}",
                "result": times,
                "problems": problems,
                "used_fallback": used_fallback,
                "min_gap_minutes": gap,
            }
        )

    total = len(CASES)
    fallbacks = sum(1 for row in rows if row["used_fallback"])
    print()
    print(f"合法率：{passed}/{total} = {passed / total:.0%}")
    print(f"LLM 建议采纳：{total - fallbacks}/{total}，兜底 {fallbacks} 次")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "cases": total,
                "valid_rate": round(passed / total, 3),
                "llm_used": total - fallbacks,
                "fallback_used": fallbacks,
                "details": rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"结果已写入 {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())