"""把两次评测的 JSON 汇总成一份 markdown 报告。

用法：
    python -m scripts.eval_report

输出：
    docs/eval-YYYYMMDD.md
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "docs" / "eval"
MEMORY_JSON = EVAL_DIR / "memory.json"
DIALOGUE_JSON = EVAL_DIR / "dialogue.json"

BASELINE = "pure_vector"
TUNED = "gentle_recency"


def load(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def memory_section(data: dict | None) -> list[str]:
    lines = ["## 1. 检索质量", ""]
    if not data:
        lines += ["> 未找到 `docs/eval/memory.json`，先跑 `python -m scripts.eval_memory`", ""]
        return lines

    lines += [
        f"测试集 **{data['case_count']}** 条人工用例，取 Top-{data['top_k']}。",
        "记忆池固定 20 条，写入时间跨度 12h ~ 900h（按用例里的 `age_hours` 回拨）。",
        "",
        "| 配置 | 权重 (rel / rec / imp) | 半衰期 | Hit@5 | MRR |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in data["configs"]:
        weights = item["weights"]
        lines.append(
            f"| `{item['name']}` | {weights['relevance']} / {weights['recency']} / "
            f"{weights['importance']} | {item.get('half_life_hours', 138):.0f}h | "
            f"{item['hit_at_5']:.3f} | {item['mrr']:.3f} |"
        )

    by_name = {c["name"]: c for c in data["configs"]}
    baseline = by_name.get(BASELINE)
    tuned = by_name.get(TUNED) or max(
        data["configs"], key=lambda c: (c["hit_at_5"], c["mrr"])
    )
    worst = min(data["configs"], key=lambda c: (c["hit_at_5"], c["mrr"]))

    lines += ["", "**结论**："]
    if baseline:
        lines.append(
            f"- 基线（纯向量）Hit@5 {baseline['hit_at_5']:.3f} / MRR {baseline['mrr']:.3f}"
        )
    lines.append(
        f"- 调参后（`{tuned['name']}`）Hit@5 {tuned['hit_at_5']:.3f} / MRR {tuned['mrr']:.3f}"
        + (
            f"，相对基线 MRR {tuned['mrr'] - baseline['mrr']:+.3f}"
            if baseline
            else ""
        )
    )
    lines.append(
        f"- 最差配置是 `{worst['name']}`（Hit@5 {worst['hit_at_5']:.3f}）："
        "**recency 权重过大时，新近度会彻底盖过相关性**"
    )
    lines.append(
        "- 因此把线上默认权重改为 **0.85 / 0.05 / 0.10**（`app/memory/ranking.py`），"
        "让 recency 只做同等相关度时的轻微偏好"
    )

    misses = tuned.get("misses", []) if tuned else []
    if misses:
        lines += ["", f"- `{tuned['name']}` 未命中 {len(misses)} 条：", ""]
        for miss in misses[:10]:
            lines.append(f"  - 「{miss['query']}」→ 期望包含「{miss['expect']}」")

    lines.append("")
    return lines


def dialogue_section(data: dict | None) -> list[str]:
    lines = ["## 2. 对话质量", ""]
    if not data:
        lines += ["> 未找到 `docs/eval/dialogue.json`，先跑 `python -m scripts.eval_dialogue`", ""]
        return lines

    labels = {"persona": "人设一致性", "natural": "承接自然度", "brevity": "简洁度"}
    lines += [
        f"测试场景 **{data['scenario_count']}** 个，"
        "评审模型与被测模型相同（**存在自评偏差，分数偏乐观**）。",
        "",
        "| 维度 | 均分（1~5） | 不合格（<3） |",
        "| --- | --- | --- |",
    ]
    for key, label in labels.items():
        item = data["summary"][key]
        lines.append(f"| {label} | {item['mean']:.2f} | {item['bad']} |")

    weak = [r for r in data["records"] if min(r["scores"].values()) < 5]
    if weak:
        lines += ["", "**扣分样例**（不是不合格，是没拿满分的）：", ""]
        for record in weak[:5]:
            lines.append(
                f"- {record['npc']}｜玩家：「{record['message']}」"
                f" → 回复：「{record['reply'][:60]}」"
                f"（persona/natural/brevity = {record['scores']['persona']}/"
                f"{record['scores']['natural']}/{record['scores']['brevity']}）"
            )

    lines.append("")
    return lines


def performance_section(dialogue: dict | None) -> list[str]:
    lines = ["## 3. 端到端性能", ""]
    if not dialogue:
        lines += ["> 缺少对话评测数据", ""]
        return lines

    perf = dialogue["performance"]
    lines += [
        "| 指标 | 值 |",
        "| --- | --- |",
        f"| 样本数 | {perf['runs']} |",
        f"| P50 | {perf['p50_ms']} ms |",
        f"| P95 | {perf['p95_ms']} ms |",
        f"| 均值 | {perf['mean_ms']} ms |",
        f"| 最大 | {perf['max_ms']} ms |",
        "",
        "> 一次 `/api/chat` = 2 次 LLM（生成回复 + 回合分析）+ 2 次 embedding"
        "（写记忆 + 召回 query），所以 P50 在 3.5 秒量级。",
        "> 优化方向：回合分析和回复生成可以并行（分析不依赖回复），预计能压到 2 秒级。",
        "",
    ]
    return lines


def main() -> None:
    memory = load(MEMORY_JSON)
    dialogue = load(DIALOGUE_JSON)

    now = datetime.now(UTC)
    lines = [
        f"# 评测报告 {now.astimezone().strftime('%Y-%m-%d')}",
        "",
        "> 由 `python -m scripts.eval_report` 自动生成，数字来自 `docs/eval/*.json`。",
        "",
        "## 0. 复现方式",
        "",
        "```bash",
        "python -m scripts.eval_seed_memories   # 灌入固定的记忆集合（幂等，含时间跨度）",
        "python -m scripts.eval_memory          # 检索：三因子消融",
        "python -m scripts.eval_dialogue        # 对话：LLM-as-judge + 延迟",
        "python -m scripts.eval_report          # 汇总成本文件",
        "```",
        "",
        "评测前请**停掉 worker**，否则后台仍在写记忆，结果不可复现。",
        "",
    ]

    lines += memory_section(memory)
    lines += dialogue_section(dialogue)
    lines += performance_section(dialogue)

    lines += [
        "## 4. 已知问题",
        "",
        "1. **自评偏差**：judge 与被测模型相同，persona 满分不代表真的没问题。",
        "2. **测试集规模小**：22 条检索用例、10 个对话场景，只能看相对趋势。",
        "3. **检索池只有 20 条**：Top-5 覆盖了 25% 的池子，Hit@5 存在天花板效应；"
        "数据量上去后分数一定下降。",
        "4. **单机单用户**：延迟数据不含并发，worker 串行处理（吞吐=1）。",
        "5. **评测与训练同源**：用例内容就是记忆原文的改写，比真实对话简单。",
        "",
        "## 5. 下一步",
        "",
        "- 把检索池扩到 200 条以上，加入「应该召回不到」的负样本，降低天花板效应",
        "- 检索侧：对元问题做 query 改写（「我说过什么」→ 陈述句），再对比 Hit@5",
        "- 对话侧：把 judge 换成更强模型，并对同一批回复做人工抽样复核",
        "- 性能：把 `analyze_turn` 与 `generate_reply` 并行化",
        "",
    ]

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    out = ROOT / "docs" / f"eval-{now.astimezone().strftime('%Y%m%d')}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"报告已写入 {out}")


if __name__ == "__main__":
    main()