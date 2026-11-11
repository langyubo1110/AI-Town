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