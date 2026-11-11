"""NPC 日计划的纯规则。

这个文件只做"算"，不碰 Redis、不碰 LLM、不碰数据库 —— 和第 3 步讲的
`domain/affinity_rules.py` 是同一个定位：规则能被毫秒级单测。

计划的数据形状（存 Redis 的 JSON，也是 API 返回的形状）：

    [{"at": "09:30", "goal": "重构登录模块", "room": "工位区", "status": "pending"},
     {"at": "14:00", "goal": "找李四对齐需求", "room": "会议室", "status": "done"}]
"""

from datetime import date, datetime, time

# 这三个房间必须和前端 web/src/scene/layout.ts 的 ROOMS 保持一致
VALID_ROOMS = ("工位区", "会议室", "休息区")
DEFAULT_ROOM = "工位区"

# 一天最多排几步。太多会显得像待办清单，不像人
MAX_STEPS = 5

# 一步计划晚了超过这么久还没做，就标成 missed（不再补做）。
# 为什么需要：worker 停了一上午，16:00 才启动，如果还去补做 09:30 的事，
# 事件时间线就错了 —— NPC 会在下午四点"早上九点半"。
MAX_LATE_MINUTES = 120

# 计划在 Redis 里活多久：一天 + 2 小时缓冲（跨零点还在跑的任务不至于读不到）
PLAN_TTL_SECONDS = 26 * 3600

# ---- 排程窗口 ----
# 为什么需要这套东西：最早的计划 prompt 把时间写死成 "09:00 ~ 18:00"。
# 结果下午 15:00 才第一次启动 worker 时，LLM 照样排出一串 09:30 / 11:00 的事，
# 而 expire_stale 会立刻把它们全标成 missed —— 页面上"今天"的计划看着像全废了。
# 正确做法：让计划只落在"从此刻往后"的那段可用时间里。

# 白天的上班时段
WORK_START_MINUTES = 9 * 60  # 09:00
WORK_END_MINUTES = 18 * 60  # 18:00
# 已经过了 18:00 才开始排时，退到"傍晚窗口"，否则一条都排不出来
EVENING_END_MINUTES = 22 * 60  # 22:00

# 起点要比"现在"晚一点：否则计划刚生成就算到点，看着像抢跑
PLAN_LEAD_MINUTES = 10
# 估算"这段时间该排几步"用的平均间隔
MINUTES_PER_STEP = 120
# 窗口太窄时也至少给一步，否则计划是空的、NPC 整个下午发呆
MINUTE_OF_DAY_MAX = 23 * 60 + 59


def plan_key(npc_id: int, day: date) -> str:
    """一个 NPC 一天一份计划，key 里带日期 —— 天然实现"每天重新开始"。"""
    return f"aitown:plan:{npc_id}:{day.isoformat()}"

def parse_hhmm(text: str) -> time | None:
    """'09:30' → time(9, 30)；解析不出来返回 None（交给调用方丢掉这一步）。"""
    value = (text or "").strip()
    if not value or ":" not in value:
        return None

    parts = value.split(":")
    try:
        hour = int(parts[0].strip())
        minute = int(parts[1].strip())
    except (ValueError, IndexError):
        return None

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)

def normalize_step(raw: dict) -> dict | None:
    """把 LLM 吐出来的一步清洗成合法结构。

    LLM 会犯的错：时间写成 "9点"、房间编一个"天台"、goal 写成长篇。
    这里逐项兜住：时间非法就丢掉这一步，房间非法就落到默认房间。
    """
    goal = str(raw.get("goal") or "").strip()
    at = parse_hhmm(str(raw.get("at") or ""))
    room = str(raw.get("room") or "").strip()

    if not goal or at is None:
        return None
    if room not in VALID_ROOMS:
        room = DEFAULT_ROOM

    return {
        "at": at.strftime("%H:%M"),
        "goal": goal[:40],
        "room": room,
        "status": "pending",
    }

def normalize_steps(raw_steps: list[dict]) -> list[dict]:
    """清洗 + 按时间排序 + 截断到 MAX_STEPS。"""
    steps = [step for step in (normalize_step(r) for r in raw_steps or []) if step]
    steps.sort(key=lambda s: s["at"])
    return steps[:MAX_STEPS]

def due_step(steps: list[dict], now: datetime) -> int | None:
    """返回"最早一个到点且还没做"的下标；没有就返回 None。

    注意：列表必须已按时间排序（normalize_steps 保证），
    所以第一个命中的就是最早的。
    """
    current = now.strftime("%H:%M")
    for index, step in enumerate(steps):
        if step.get("status") != "pending":
            continue
        if step["at"] <= current:
            return index
    return None


def mark_done(steps: list[dict], index: int) -> list[dict]:
    """把第 index 步标成 done，返回新列表（不改原对象，和节点返回增量的风格一致）。"""
    updated = [dict(step) for step in steps]
    if 0 <= index < len(updated):
        updated[index]["status"] = "done"
    return updated

def expire_stale(
    steps: list[dict],
    now: datetime,
    *,
    max_late_minutes: int = MAX_LATE_MINUTES,
) -> tuple[list[dict], int]:
    """把"过期太久还没做"的步骤标成 missed，返回 (新列表, 标记数量)。

    为什么要这一步：否则服务停了一上午再启动，NPC 会一条条补做早上的计划，
    事件时间线看起来像"下午四点在干早上九点半的事"。
    """
    now_minutes = now.hour * 60 + now.minute
    updated = [dict(step) for step in steps]
    expired = 0

    for step in updated:
        if step.get("status") != "pending":
            continue
        at = parse_hhmm(str(step.get("at") or ""))
        if at is None:
            continue
        late = now_minutes - (at.hour * 60 + at.minute)
        if late > max_late_minutes:
            step["status"] = "missed"
            expired += 1

    return updated, expired


def progress(steps: list[dict]) -> tuple[int, int]:
    """(已完成, 总数) —— 给前端显示进度用。"""
    done = sum(1 for step in steps if step.get("status") == "done")
    return done, len(steps)


# ==================== 排程窗口 ====================


def _fmt_hhmm(minutes: int) -> str:
    """一天中的第几分钟 → 'HH:MM'（越界自动夹到当天范围内）。"""
    minutes = max(0, min(MINUTE_OF_DAY_MAX, int(minutes)))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _ceil_to_5(minutes: int) -> int:
    """向上取整到 5 分钟：15:07 → 15:10。让时间看着像人排的，不像机器算的。"""
    return -(-int(minutes) // 5) * 5


def plan_window(now: datetime) -> tuple[str, str]:
    """算出"此刻往后还能排的那段时间"，返回 (起, 止)，都是 HH:MM。

    这是修掉"下午启动、上午计划全废"的核心。三种情况：

        早于 09:00   → ("09:00", "18:00")          正常排一整天
        09:00~18:00  → ("现在+10min", "18:00")     只排剩下的
        18:00 之后   → ("现在+10min", "22:00")     排傍晚，别一条都排不出来

    起点对齐到 5 分钟、且至少比现在晚 1 分钟 —— 否则计划一生成就算"到点"，
    ticker 会立刻执行，看起来像抢跑。
    """
    minute = now.hour * 60 + now.minute

    if minute < WORK_START_MINUTES:
        start = WORK_START_MINUTES
    else:
        start = max(_ceil_to_5(minute + PLAN_LEAD_MINUTES), minute + 1)

    end = WORK_END_MINUTES if start < WORK_END_MINUTES else EVENING_END_MINUTES
    if end <= start:
        # 深夜启动：给一个 1 小时的兜底窗口，绝不返回空区间
        end = min(start + 60, MINUTE_OF_DAY_MAX)

    return _fmt_hhmm(start), _fmt_hhmm(end)


def window_minutes(start: str, end: str) -> int:
    """窗口长度（分钟）；时间解析不出来算 0。"""
    begin, finish = parse_hhmm(start), parse_hhmm(end)
    if begin is None or finish is None:
        return 0
    return max(0, (finish.hour * 60 + finish.minute) - (begin.hour * 60 + begin.minute))


def suggested_steps(start: str, end: str) -> int:
    """窗口这么长，排几步合适。

    为什么要这个：16:30 启动只剩 1.5 小时，还让 LLM 排 4 件事，
    就等于逼它把事全塞在同一个时间点 —— 计划看着就不像真的。
    """
    minutes = window_minutes(start, end)
    if minutes <= 0:
        return 1
    return max(1, min(MAX_STEPS, round(minutes / MINUTES_PER_STEP)))


def clip_to_window(steps: list[dict], *, start: str, end: str) -> list[dict]:
    """丢掉窗口外的步骤。

    LLM 不一定听话：很可能你告诉它"从 15:10 开始"，它照样从 09:30 排起。
    这些步骤留着只会被 expire_stale 标成 missed，不如当场剔掉。
    """
    kept: list[dict] = []
    for step in steps or []:
        at = str(step.get("at") or "")
        if len(at) == 5 and start <= at <= end:
            kept.append(dict(step))
    return kept


def fallback_step(*, at: str, room: str = DEFAULT_ROOM) -> dict:
    """窗口内一步都没排出来时的保底。

    为什么必须有：`ensure_plan` 的约定是"有计划就存，空列表就不存"。
    如果这里返回空，下一个 tick 会再调一次 LLM —— 每轮 tick 烧一次模型钱，
    而且页面上的计划永远是空的。给它一步，"懒生成"才是幂等的。
    """
    return {
        "at": at,
        "goal": "把手头的事做完",
        "room": room if room in VALID_ROOMS else DEFAULT_ROOM,
        "status": "pending",
    }