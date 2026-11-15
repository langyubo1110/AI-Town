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


def rrf(
    ranked_lists: list[list[int]],
    *,
    k: int = DEFAULT_K,
    weights: list[float] | None = None,
) -> list[tuple[int, float]]:
    """把若干个「已排序的 id 列表」融合成一个带分的列表。

    参数：
        ranked_lists  例如 [[3, 1, 7], [7, 3, 9]] —— 两路检索的结果
        k             平滑常数，越大越扁平
        weights       每路的权重，默认全 1。

    为什么需要 weights：
        等权融合假设"两路一样可靠"。实测在中文语料上并不成立 ——
        问"半夜系统挂了谁负责盯着"，BM25 会排到第 3（字面几乎没有重叠），
        而向量排第 1。等权 RRF 会把这条坏排名抬进前 2，反而拖低整体。
        给向量更高权重（2:1）后，才真正实现"以向量为主、BM25 补刀"。

    返回：[(id, score), ...]，按分数从高到低。
    """
    if weights is None:
        weights = [1.0] * len(ranked_lists)

    scores: dict[int, float] = {}
    for ranked, weight in zip(ranked_lists, weights, strict=True):
        for rank, doc_id in enumerate(ranked):
            scores[doc_id] = scores.get(doc_id, 0.0) + weight / (k + rank + 1)

    return sorted(scores.items(), key=lambda item: item[1], reverse=True)