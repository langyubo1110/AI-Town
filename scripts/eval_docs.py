"""文档 RAG 检索评测：纯向量 / 纯 BM25 / 混合（RRF）三路消融。

用法：
    python -m scripts.ingest_docs     # 先把 docs/kb 灌进库
    python -m scripts.eval_docs

指标：
    Hit@1 / Hit@3  期望文档是否出现在第 1 / 前 3 条
    MRR            期望文档名次的倒数均值（越接近 1 越好）

为什么要做消融：只说"我用了混合检索"没有说服力，
得能拿出"混合比纯向量高多少"的数字 —— 否则面试官会问"你怎么知道它更好"。
"""

import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.config import get_settings
from app.infra.db import build_engine, build_session_factory
from app.rag.search import search

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "eval" / "docs.json"

TOP_K = 3

# 每条：问题 + 期望命中的文档（source 文件名）
#
# 设计原则：**干扰文档之间要有词汇重叠**，否则评测没有区分度
# （第一版只有 3 篇文档时，三路策略全是 1.000，等于没测）。
CASES: list[dict] = [
    # ---- 研发规范（和"值班告警"共享"线上/发布"词汇）----
    {"q": "发布窗口是什么时候？", "want": "研发规范.md"},
    {"q": "工号是怎么编的？", "want": "研发规范.md"},
    {"q": "代码评审需要几个人同意？", "want": "研发规范.md"},
    {"q": "线上出故障了能紧急发布吗？", "want": "研发规范.md"},
    # ---- 产品需求流程 ----
    {"q": "需求评审会什么时候开？", "want": "产品需求流程.md"},
    {"q": "迭代周期多久，什么时候冻结需求？", "want": "产品需求流程.md"},
    {"q": "PRD 模板要写哪几段？", "want": "产品需求流程.md"},
    {"q": "新功能上线要灰度吗？", "want": "产品需求流程.md"},
    # ---- 新人指南 ----
    {"q": "新人第一天要做什么？", "want": "新人入职指南.md"},
    {"q": "试用期多长时间？", "want": "新人入职指南.md"},
    {"q": "账号申请找谁，多久能开通？", "want": "新人入职指南.md"},
    {"q": "加班满几个小时可以调休？", "want": "新人入职指南.md"},
    # ---- 值班与告警（易与"研发规范"混）----
    {"q": "P0 告警多久内必须响应？", "want": "值班与告警处理.md"},
    {"q": "告警没人认领会升级给谁？", "want": "值班与告警处理.md"},
    {"q": "故障复盘要写哪几部分？", "want": "值班与告警处理.md"},
    # ---- 绩效与晋升 ----
    {"q": "绩效等级分几档？", "want": "绩效与技术晋升.md"},
    {"q": "晋升答辩一年几次，在几月？", "want": "绩效与技术晋升.md"},
    {"q": "晋升答辩需要哪些材料？", "want": "绩效与技术晋升.md"},
    # ---- 数据安全（易与"账号申请/审批"混）----
    {"q": "L3 的数据能用邮件导出吗？", "want": "数据安全与权限.md"},
    {"q": "导出敏感数据需要谁审批？", "want": "数据安全与权限.md"},
    {"q": "把代码发到自己 GitHub 上可以吗？", "want": "数据安全与权限.md"},
    {"q": "测试环境用生产数据要不要脱敏？", "want": "数据安全与权限.md"},
    # ---- 行政与报销（易与"新人指南"的调休/报销混）----
    {"q": "报销几号之前提交？", "want": "行政与报销.md"},
    {"q": "一线城市住宿标准是多少？", "want": "行政与报销.md"},
    # ---- 下面是"制造差异"的两组：用来验证两种召回各自的长处 ----
    # A 组：纯同义改写，几乎没有字面重叠 —— 向量应该更强
    {"q": "改完的东西要几个人过目才能合进去？", "want": "研发规范.md"},
    {"q": "写的东西能不能放到公司外面去？", "want": "数据安全与权限.md"},
    {"q": "半夜系统挂了谁负责盯着？", "want": "值班与告警处理.md"},
    {"q": "我干得好会有什么变化？", "want": "绩效与技术晋升.md"},
    # B 组：含稀有 token / 精确短语 —— BM25 应该更强
    {"q": "P0 告警的响应时限是多久？", "want": "值班与告警处理.md"},
    {"q": "L4 的数据能导出吗？", "want": "数据安全与权限.md"},
    {"q": "绩效 S 档和 A 档差在哪？", "want": "绩效与技术晋升.md"},
    {"q": "PRD 里「不做什么」那段有什么用？", "want": "产品需求流程.md"},
]

STRATEGIES = ("vector", "bm25", "hybrid_equal", "hybrid")


async def run_strategy(session, strategy: str) -> dict:
    hits_at_1 = 0
    hits_at_k = 0
    reciprocal = 0.0
    details: list[dict] = []

    for case in CASES:
        hits = await search(session, case["q"], top_k=TOP_K, strategy=strategy)
        sources = [hit.source for hit in hits]
        want = case["want"]

        rank = sources.index(want) + 1 if want in sources else 0
        if rank == 1:
            hits_at_1 += 1
        if rank:
            hits_at_k += 1
            reciprocal += 1.0 / rank

        details.append({"q": case["q"], "want": want, "rank": rank, "got": sources})

    total = len(CASES)
    return {
        "strategy": strategy,
        "cases": total,
        "hit@1": round(hits_at_1 / total, 3),
        f"hit@{TOP_K}": round(hits_at_k / total, 3),
        "mrr": round(reciprocal / total, 3),
        "details": details,
    }


async def main() -> None:
    settings = get_settings()
    engine = build_engine(settings.postgres_dsn, echo=False, pool_size=2)
    factory = build_session_factory(engine)

    results: list[dict] = []
    try:
        async with factory() as session:
            # 先确认知识库非空，否则所有指标都是 0，容易误判成"检索不行"
            from sqlalchemy import func, select

            from app.models import DocumentChunk

            chunks = await session.scalar(select(func.count()).select_from(DocumentChunk))
            if not chunks:
                print("知识库是空的，先跑：python -m scripts.ingest_docs")
                return

            print(f"知识库共 {chunks} 块，评测 {len(CASES)} 条问题\n")

            for strategy in STRATEGIES:
                results.append(await run_strategy(session, strategy))
    finally:
        await engine.dispose()

    # ---- 打印对比表 ----
    header = f"{'策略':<10}{'Hit@1':>8}{f'Hit@{TOP_K}':>10}{'MRR':>8}"
    print(header)
    print("-" * len(header))
    for item in results:
        print(
            f"{item['strategy']:<10}{item['hit@1']:>8.3f}"
            f"{item[f'hit@{TOP_K}']:>10.3f}{item['mrr']:>8.3f}"
        )

    base = next(r for r in results if r["strategy"] == "vector")
    hybrid = next(r for r in results if r["strategy"] == "hybrid")
    print(
        f"\n混合 vs 纯向量：MRR {base['mrr']:.3f} → {hybrid['mrr']:.3f}"
        f"（{'+' if hybrid['mrr'] >= base['mrr'] else ''}{hybrid['mrr'] - base['mrr']:+.3f}）"
    )

    # ---- 未命中的 case，便于调优 ----
    print("\n混合策略下未命中的问题：")
    missed = [d for d in hybrid["details"] if not d["rank"]]
    if not missed:
        print("  （没有）")
    for item in missed:
        print(f"  ✗ {item['q']}  → 期望 {item['want']}，实际 {item['got']}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"top_k": TOP_K, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n结果已写入 {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())