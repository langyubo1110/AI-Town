"""好感度领域规则（纯函数，不依赖数据库）。"""

MIN_SCORE = 0.0
MAX_SCORE = 100.0
DEFAULT_SCORE = 50.0

# 关系等级：(上界, 名称)，左闭右开；按顺序匹配
LEVELS: tuple[tuple[float, str], ...] = (
    (20.0, "陌生"),
    (40.0, "熟悉"),
    (60.0, "友好"),
    (80.0, "亲密"),
    (100.0, "挚友"),
)


def clamp_score(score: float) -> float:
    """把分数限制在 [0, 100]。"""
    return max(MIN_SCORE, min(MAX_SCORE, score))


def apply_delta(score: float, delta: float) -> tuple[float, float]:
    """返回 (新分数, 实际变化量)。"""
    new_score = clamp_score(score + delta)
    return new_score, new_score - score


def level_from_score(score: float) -> str:
    """由分数推出关系等级。"""
    current = clamp_score(score)
    for upper, name in LEVELS:
        if current < upper:
            return name
    return LEVELS[-1][1]