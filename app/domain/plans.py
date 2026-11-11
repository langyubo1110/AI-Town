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