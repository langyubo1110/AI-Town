"""三因子重排：relevance / recency / importance 的加权和。"""

from dataclasses import dataclass

# 权重之和 = 1.0，保证 score 仍在 [0, 1]
#
# 这组数来自 scripts/eval_memory.py 的消融实验（22 条人工用例）：
#   0.50/0.30/0.20 → Hit@5 0.364（recency 完全盖过 relevance）
#   1.00/0.00/0.00 → Hit@5 1.000 / MRR 0.901（纯向量基线）
#   0.85/0.05/0.10 → Hit@5 1.000 / MRR 0.947（最优）
# 结论：长期事实记忆不该按"小时"衰减，recency 只配当同等相关度时的轻微偏好。

W_RELEVANCE = 0.85      #这条记忆和当前话题有多像
W_RECENCY = 0.05        #"这条记忆有多新/多常被想起
W_IMPORTANCE = 0.10     #这条记忆本身有多重要

# 记忆新鲜度每 138 小时（约 5.8 天）减半
HALF_LIFE_HOURS = 138.0

#frozen=True 表示不可变，排序过程中不会被意外修改
@dataclass(frozen=True)
class Candidate:
    """一条候选记忆（已从数据库取出的纯数据，不含 ORM 对象）。"""

    id: int
    content: str
    relevance: float      # 0~1
    importance: float     # 0~1
    age_hours: float      # 距上次被想起/创建，多少小时


#把向量检索返回的余弦距离转成相似度。
def relevance_from_distance(distance: float) -> float:
    """余弦距离 → 相似度。距离可能为负（向量反向），剪到 [0,1]。"""
    return min(1.0, max(0.0, 1.0 - distance))


#把“年龄（小时）”转成 0~1 的新近性分，用指数衰减。
def recency_from_age(age_hours: float) -> float:
    """指数衰减：刚发生 = 1.0，越久越接近 0。"""
    return 0.5 ** (max(0.0, age_hours) / HALF_LIFE_HOURS)

# 用指定权重组打分：评测里的消融实验靠它（不改全局常量，天然可并行）
def score_with(
    c: Candidate,
    *,
    w_relevance: float,
    w_recency: float,
    w_importance: float,
) -> float:
    return (
        w_relevance * c.relevance
        + w_recency * recency_from_age(c.age_hours)
        + w_importance * c.importance
    )


#打分（线上路径用的默认权重）
def score(c: Candidate) -> float:
    return score_with(
        c,
        w_relevance=W_RELEVANCE,
        w_recency=W_RECENCY,
        w_importance=W_IMPORTANCE,
    )

#
def rank(candidates: list[Candidate], *, top_k: int) -> list[Candidate]:
    """按三因子分降序取前 top_k 条。"""
    return sorted(candidates, key=score, reverse=True)[:top_k]