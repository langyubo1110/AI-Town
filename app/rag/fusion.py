"""RRF（Reciprocal Rank Fusion）—— 把多路排名合成一路。

为什么用它，而不是"把两边的分数加权平均"：
    BM25 的分数是 0~30 的无界值，余弦相似度是 0~1。
    两者量纲不同，加权平均要先归一化，而归一化依赖当前这批数据 ——
    换一批文档，权重就得重调。RRF 只用**名次**，不用分数，天然免疫这个问题。

公式（对每个候选）：score = Σ 1 / (k + rank)
    k=60 是论文里的经验值，作用是压低头部优势，让"两个榜单都靠前"
    的文档胜出，而不是"某一个榜单第一"通吃。
"""

DEFAULT_K = 60


def rrf(ranked_lists: list[list[int]], *, k: int = DEFAULT_K) -> list[tuple[int, float]]:
    """把若干个「已排序的 id 列表」融合成一个带分的列表。

    参数：
        ranked_lists  例如 [[3, 1, 7], [7, 3, 9]] —— 两路检索的结果
        k             平滑常数，越大越扁平

    返回：[(id, score), ...]，按分数从高到低。
    """
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)

    return sorted(scores.items(), key=lambda item: item[1], reverse=True)