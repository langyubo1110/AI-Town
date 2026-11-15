"""反思质量评测：LLM 产出的洞察是"判断"还是"复述"。

用法：
    python -m scripts.eval_reflection

为什么普通单测算不出来：
    单测能验证 prompt 拼得对、条数截断得对，但验证不了"这两句话有没有价值"。
    这是主观判断，只能用规则 + LLM-as-judge 双路。

两条路：
    规则层  条数是否 2~3、是否第一人称、是否直接抄了目标原文（复述）
    裁判层  LLM 给三个维度打分 1~5：判断性、自我相关、具体性
"""

import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pydantic import BaseModel, Field

from app.agents.reflection import reflect
from app.infra.llm import get_chat_model

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "eval" / "reflection.json"

# 每条场景：像不像一天的收尾
CASES: list[dict] = [
    {
        "name": "张三",
        "title": "Python工程师",
        "done": ["code review 队友的 PR", "重构调度器消息队列", "修线上超时问题"],
        "missed": ["写自己的模块设计文档"],
        "memories": ["玩家说他在学 Rust", "李四找我改了三次需求", "凌晨两点被告警叫醒"],
    },
    {
        "name": "李四",
        "title": "产品经理",
        "done": ["主持需求评审会"],
        "missed": ["写 Q4 购物车改版文档", "和设计对齐交互稿"],
        "memories": ["研发说需求变来变去", "老板问进度", "用户反馈下单流程太绕"],
    },
    {
        "name": "王五",
        "title": "UI设计师",
        "done": ["调登录页配色", "输出三套视觉稿", "和前端对齐间距"],
        "missed": ["整理设计规范"],
        "memories": ["前端说实现不了毛玻璃", "评审被退了两次", "玩家夸小镇好看"],
    },
    {
        "name": "张三",
        "title": "Python工程师",
        "done": [],
        "missed": ["重构调度器", "写单测", "对齐接口"],
        "memories": ["一整天都在开会", "需求又变了", "头疼"],
    },
    {
        "name": "李四",
        "title": "产品经理",
        "done": ["对齐排期", "梳理用户反馈", "写竞品分析", "开周会"],
        "missed": [],
        "memories": ["一天开了五个会", "嗓子哑了", "晚上还有饭局"],
    },
    {
        "name": "王五",
        "title": "UI设计师",
        "done": ["改了一版按钮圆角"],
        "missed": ["没动视觉稿主体"],
        "memories": ["反复在细节上纠结", "被说审美不行", "想去看展"],
    },
    {
        "name": "张三",
        "title": "Python工程师",
        "done": ["部署新版本", "写发布说明"],
        "missed": ["补监控面板"],
        "memories": ["发布很顺利", "没人提意见", "有点不真实"],
    },
    {
        "name": "李四",
        "title": "产品经理",
        "done": ["和测试对齐用例"],
        "missed": ["评审原型", "更新排期"],
        "memories": ["测试说用例写不清", "研发在等排期", "自己也有点乱"],
    },
    {
        "name": "王五",
        "title": "UI设计师",
        "done": ["整理设计规范", "评审通过"],
        "missed": [],
        "memories": ["终于被认可了", "玩家说界面清楚", "想多做点这类事"],
    },
    {
        "name": "张三",
        "title": "Python工程师",
        "done": ["排查内存泄漏", "写复盘"],
        "missed": ["原计划的重构"],
        "memories": ["线上炸了一次", "排查花了一下午", "复盘会上被问得有点狠"],
    },
]


class JudgeOut(BaseModel):
    """裁判输出。"""

    judgement: int = Field(..., ge=1, le=5, description="是判断还是复述：5=明确判断")
    self_ref: int = Field(..., ge=1, le=5, description="是否关于自己：5=完全第一人称自省")
    specificity: int = Field(..., ge=1, le=5, description="具体程度：5=有细节不空泛")
    reason: str = Field(..., description="一句话说明扣分点")


JUDGE_PROMPT = """你在评估一个 AI 角色"反思"的质量。

角色的身份：{title}
它今天做成的事：{done}
没做成的事：{missed}
它产出的洞察：
{insights}

请按三个维度打分（1~5）：
1. judgement：是"对自己状态的判断"还是"对事情的复述"？
   复述示例："我今天 code review 了 PR"（拿 1~2 分）
   判断示例："我总在给别人兜底，自己的活反而没推进"（拿 4~5 分）
2. self_ref：是不是第一人称关于自己？全在讲别人/讲事情拿 1~2 分。
3. specificity：有没有具体依据？"我要更努力"这种空话拿 1~2 分。

只打分，不要客套。
"""


def rule_check(insights: list[str], goals: list[str]) -> dict:
    """规则层：条数、第一人称、复述。"""
    count_ok = 2 <= len(insights) <= 3
    first_person = sum(1 for text in insights if "我" in text) / max(1, len(insights))

    # 复述判定：洞察里直接出现某个目标的原文片段
    copied = 0
    for text in insights:
        for goal in goals:
            head = goal[:6]
            if head and head in text:
                copied += 1
                break

    return {
        "count_ok": count_ok,
        "first_person_rate": round(first_person, 2),
        "copied": copied,
        "copied_rate": round(copied / max(1, len(insights)), 2),
        "max_len": max((len(text) for text in insights), default=0),
    }


async def judge(case: dict, insights: list[str]) -> JudgeOut | None:
    prompt = JUDGE_PROMPT.format(
        title=case["title"],
        done="、".join(case["done"]) or "（无）",
        missed="、".join(case["missed"]) or "（无）",
        insights="\n".join(f"- {text}" for text in insights),
    )
    try:
        llm = get_chat_model().with_structured_output(
            JudgeOut, method="function_calling"
        )
        return await llm.ainvoke(prompt)
    except Exception as exc:  # noqa: BLE001 —— 裁判挂了不该让评测整体失败
        print(f"  裁判失败：{type(exc).__name__}")
        return None


async def main() -> None:
    rows: list[dict] = []
    scores: list[tuple[int, int, int]] = []

    print(f"{'角色':<6}{'条数':>4}{'第一人称':>8}{'复述':>6}{'判断':>6}{'自省':>6}{'具体':>6}")
    print("-" * 52)

    for case in CASES:
        insights = await reflect(
            name=case["name"],
            title=case["title"],
            done_goals=case["done"],
            missed_goals=case["missed"],
            memories=case["memories"],
        )
        stats = rule_check(insights, case["done"] + case["missed"])
        verdict = await judge(case, insights) if insights else None

        if verdict:
            scores.append((verdict.judgement, verdict.self_ref, verdict.specificity))

        print(
            f"{case['name']:<6}{len(insights):>4}{stats['first_person_rate']:>8.2f}"
            f"{stats['copied']:>6}"
            f"{(verdict.judgement if verdict else 0):>6}"
            f"{(verdict.self_ref if verdict else 0):>6}"
            f"{(verdict.specificity if verdict else 0):>6}"
        )

        rows.append(
            {
                "npc": case["name"],
                "insights": insights,
                "rule": stats,
                "judge": verdict.model_dump() if verdict else None,
            }
        )

    total = len(CASES)
    count_ok = sum(1 for row in rows if row["rule"]["count_ok"])
    first_person = sum(row["rule"]["first_person_rate"] for row in rows) / total
    copied = sum(row["rule"]["copied"] for row in rows)

    print()
    print(f"条数合规（2~3 条）：{count_ok}/{total}")
    print(f"第一人称比例：{first_person:.2f}")
    print(f"复述条数：{copied}（越低越好）")
    if scores:
        avg = [sum(col) / len(scores) for col in zip(*scores, strict=True)]
        print(
            f"裁判均分：判断 {avg[0]:.2f} / 自省 {avg[1]:.2f} / 具体 {avg[2]:.2f}（满分 5）"
        )
        # 诚实标注：裁判和生成用的是同一个模型，天然偏向自己写的答案
        print("⚠️  同模型自评分数偏高，只看趋势不看绝对值；结论以规则层三个客观指标为准")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "cases": total,
                "count_ok": count_ok,
                "first_person_rate": round(first_person, 2),
                "copied": copied,
                "judge_avg": [round(x, 2) for x in avg] if scores else None,
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