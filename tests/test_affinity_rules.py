"""好感度规则的单元测试（不需要数据库、不需要启动服务）。"""

import pytest

from app.domain import affinity_rules as rules

'''
一个函数跑 10 组数据。比写 10 个 def test_xxx 简洁十倍，而且失败时会明确告诉你是哪组数据挂了：
'''
@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, "陌生"),
        (19.9, "陌生"),
        (20, "熟悉"),        # 边界：20 属于下一档
        (39.9, "熟悉"),
        (40, "友好"),
        (59.9, "友好"),
        (60, "亲密"),
        (79.9, "亲密"),
        (80, "挚友"),        # 边界：80 属于挚友
        (100, "挚友"),
    ],
)
def test_level_from_score(score: float, expected: str) -> None:
    assert rules.level_from_score(score) == expected


def test_clamp_score_hits_bounds() -> None:
    assert rules.clamp_score(-10) == 0
    assert rules.clamp_score(120) == 100
    assert rules.clamp_score(55) == 55


def test_apply_delta_normal() -> None:
    new_score, actual = rules.apply_delta(50, 3)
    assert new_score == 53
    assert actual == 3


def test_apply_delta_clamped_reports_real_change() -> None:
    """关键：99 + 5 只应该加 1，且返回的变化量是 1 不是 5。"""
    new_score, actual = rules.apply_delta(99, 5)
    assert new_score == 100
    assert actual == 1


def test_apply_delta_at_max_is_noop() -> None:
    new_score, actual = rules.apply_delta(100, 1)
    assert new_score == 100
    assert actual == 0