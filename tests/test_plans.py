"""日计划纯规则的单元测试（不需要数据库、不需要 Redis、不需要 LLM）。"""

from datetime import date, datetime

import pytest

from app.domain import plans as rules


def _step(at: str, status: str = "pending", goal: str = "写代码", room: str = "工位区"):
    return {"at": at, "goal": goal, "room": room, "status": status}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("09:30", "09:30"),
        ("9:5", "09:05"),
        (" 14:00 ", "14:00"),
        ("9点", None),
        ("", None),
        ("25:00", None),
        ("12:70", None),
        ("abc", None),
    ],
)
def test_parse_hhmm(text, expected):
    parsed = rules.parse_hhmm(text)
    assert (parsed.strftime("%H:%M") if parsed else None) == expected


def test_normalize_step_drops_bad_time():
    assert rules.normalize_step({"at": "晚上", "goal": "写代码", "room": "工位区"}) is None


def test_normalize_step_drops_empty_goal():
    assert rules.normalize_step({"at": "09:00", "goal": "   ", "room": "工位区"}) is None


def test_normalize_step_falls_back_to_default_room():
    step = rules.normalize_step({"at": "09:00", "goal": "发呆", "room": "天台"})
    assert step is not None
    assert step["room"] == rules.DEFAULT_ROOM
    assert step["status"] == "pending"


def test_normalize_steps_sorts_by_time():
    steps = rules.normalize_steps(
        [
            {"at": "15:00", "goal": "调界面", "room": "工位区"},
            {"at": "09:30", "goal": "写代码", "room": "工位区"},
            {"at": "12:00", "goal": "吃饭", "room": "休息区"},
        ]
    )
    assert [s["at"] for s in steps] == ["09:30", "12:00", "15:00"]


def test_due_step_returns_oldest_unfinished():
    """注意语义：返回【最早】那个没做完的，不是最近那个。

    因为服务可能停过一段，按时间顺序补做才不会乱。
    过期太久的那些由 expire_stale 提前标成 missed，轮不到这里。
    """
    steps = [_step("09:00"), _step("14:00"), _step("17:00")]
    assert rules.due_step(steps, datetime(2026, 11, 10, 14, 30)) == 0


def test_expire_stale_marks_old_pending():
    steps = [_step("09:00"), _step("14:00")]
    updated, expired = rules.expire_stale(steps, datetime(2026, 11, 10, 16, 0))
    assert expired == 1
    assert updated[0]["status"] == "missed"
    assert updated[1]["status"] == "pending"


def test_expire_stale_keeps_recent_step():
    steps = [_step("15:00")]
    updated, expired = rules.expire_stale(steps, datetime(2026, 11, 10, 16, 0))
    assert expired == 0
    assert updated[0]["status"] == "pending"


def test_expire_stale_ignores_done():
    steps = [_step("09:00", status="done")]
    _, expired = rules.expire_stale(steps, datetime(2026, 11, 10, 16, 0))
    assert expired == 0


def test_due_step_skips_done():
    steps = [_step("09:00", status="done"), _step("10:00")]
    assert rules.due_step(steps, datetime(2026, 11, 10, 11, 0)) == 1


def test_due_step_none_before_time():
    steps = [_step("14:00")]
    assert rules.due_step(steps, datetime(2026, 11, 10, 9, 0)) is None


def test_due_step_after_day_end_returns_last_pending():
    steps = [_step("09:00", status="done"), _step("17:00")]
    assert rules.due_step(steps, datetime(2026, 11, 10, 23, 59)) == 1


def test_mark_done_does_not_mutate_original():
    steps = [_step("09:00")]
    updated = rules.mark_done(steps, 0)
    assert steps[0]["status"] == "pending"
    assert updated[0]["status"] == "done"


def test_mark_done_out_of_range_is_safe():
    steps = [_step("09:00")]
    assert rules.mark_done(steps, 5)[0]["status"] == "pending"


def test_plan_key_contains_date():
    key = rules.plan_key(3, date(2026, 11, 10))
    assert "2026-11-10" in key
    assert "3" in key


def test_progress_counts_done():
    steps = [_step("09:00", status="done"), _step("14:00")]
    assert rules.progress(steps) == (1, 2)


# ==================== 排程窗口 ====================


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # 还没上班：排一整天
        (datetime(2026, 11, 10, 8, 0), ("09:00", "18:00")),
        # 刚好 09:00：起点还是往后推 10 分钟，不能排"现在"
        (datetime(2026, 11, 10, 9, 0), ("09:10", "18:00")),
        # ★ 这个用例就是修掉的那个 bug：下午 15:00 才启动，不该再排 09:30
        (datetime(2026, 11, 10, 15, 0), ("15:10", "18:00")),
        # 起点对齐到 5 分钟：15:07 + 10 = 15:17 → 15:20
        (datetime(2026, 11, 10, 15, 7), ("15:20", "18:00")),
        # 17:55 + 10 已经过了下班点 → 退到傍晚窗口
        (datetime(2026, 11, 10, 17, 55), ("18:05", "22:00")),
        # 深夜启动：给 1 小时兜底窗口，绝不返回空区间
        (datetime(2026, 11, 10, 22, 30), ("22:40", "23:40")),
    ],
)
def test_plan_window(now, expected):
    assert rules.plan_window(now) == expected


def test_plan_window_always_forward_and_ordered():
    """扫一天里每 7 分钟，窗口必须满足：起点 > 现在、起点 <= 终点。"""
    for minute in range(0, 24 * 60, 7):
        now = datetime(2026, 11, 10, minute // 60, minute % 60)
        start, end = rules.plan_window(now)

        begin, finish = rules.parse_hhmm(start), rules.parse_hhmm(end)
        assert begin is not None and finish is not None
        assert (begin.hour * 60 + begin.minute) <= (finish.hour * 60 + finish.minute)
        # 只有当"现在已过 22:00"时起点才可能等于/早于当前时刻之外的情况
        if minute < 22 * 60:
            assert (begin.hour * 60 + begin.minute) > minute


def test_window_minutes():
    assert rules.window_minutes("09:00", "18:00") == 540
    assert rules.window_minutes("15:10", "18:00") == 170
    assert rules.window_minutes("坏了", "18:00") == 0


def test_suggested_steps_shrinks_with_window():
    """整天的窗口能排 4 步；只剩 1 小时就只能排 1 步。"""
    assert rules.suggested_steps("09:00", "18:00") == 4
    assert rules.suggested_steps("17:00", "18:00") == 1


def test_suggested_steps_always_between_1_and_max():
    for start, end in [("09:00", "09:05"), ("09:00", "23:00"), ("22:00", "22:00")]:
        count = rules.suggested_steps(start, end)
        assert 1 <= count <= rules.MAX_STEPS


def test_clip_to_window_drops_past_steps():
    steps = [_step("09:30"), _step("15:30"), _step("16:00")]
    kept = rules.clip_to_window(steps, start="15:10", end="18:00")
    assert [s["at"] for s in kept] == ["15:30", "16:00"]


def test_clip_to_window_does_not_mutate_original():
    steps = [_step("09:30")]
    rules.clip_to_window(steps, start="15:10", end="18:00")
    assert steps[0]["status"] == "pending"
    assert len(steps) == 1


def test_fallback_step_is_valid():
    step = rules.fallback_step(at="15:10", room="天台")
    assert step["room"] == rules.DEFAULT_ROOM  # 非法房间落到默认
    assert step["at"] == "15:10"
    assert step["status"] == "pending"
    assert step["goal"]


def test_fallback_step_keeps_valid_room():
    assert rules.fallback_step(at="15:10", room="会议室")["room"] == "会议室"


# ==================== 重排（redistribute） ====================


def test_redistribute_spreads_over_window():
    """3 步铺进 13:00~18:00（300 分钟）：每步隔 100 分钟。"""
    steps = [_step("09:00", status="missed"), _step("10:00", status="missed"), _step("11:00")]
    out = rules.redistribute(steps, start="13:00", end="18:00")
    assert [s["at"] for s in out] == ["13:00", "14:40", "16:20"]


def test_redistribute_resets_status_to_pending():
    """过期的步骤被重新安排后，必须重新变成"待办"。"""
    out = rules.redistribute([_step("09:00", status="missed")], start="13:00", end="18:00")
    assert out[0]["status"] == "pending"


def test_redistribute_does_not_mutate_input():
    steps = [_step("09:00", status="missed")]
    rules.redistribute(steps, start="13:00", end="18:00")
    assert steps[0]["at"] == "09:00"
    assert steps[0]["status"] == "missed"


def test_redistribute_empty_returns_empty():
    assert rules.redistribute([], start="13:00", end="18:00") == []


def test_redistribute_never_leaves_the_window():
    """10 步塞进 1 小时：结果仍必须全部落在窗口内。"""
    steps = [_step("09:00") for _ in range(10)]
    out = rules.redistribute(steps, start="13:00", end="14:00")
    assert all("13:00" <= s["at"] <= "14:00" for s in out)


def test_redistribute_keeps_goal_and_room():
    out = rules.redistribute(
        [_step("09:00", goal="写代码", room="会议室")], start="13:00", end="18:00"
    )
    assert out[0]["goal"] == "写代码"
    assert out[0]["room"] == "会议室"