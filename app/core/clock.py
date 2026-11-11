"""统一的"现在"。

**业务时间一律走这里，不要直接用 `datetime.now()`。**

为什么：开发机（Windows，+08）上 `datetime.now()` 恰好等于本地时间，
一进容器就变成 UTC —— 计划里写着 `09:15`，容器的 `now` 却是 `03:15`，
`due_step()` 永远判"还没到点"，表现就是**小镇一整天一动不动**。

绝对时间（事件时间戳、记忆写入时间）继续用 `datetime.now(UTC)`，
那些是"瞬时点"，和时区无关，换时区不该改变它们。
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def local_now() -> datetime:
    """当前本地时间（带时区信息）。"""
    return datetime.now(ZoneInfo(get_settings().app_timezone))