"""离线验证排程窗口：不需要数据库、Redis、LLM。

用途：在下午/傍晚启动 worker 之前，先确认"这一刻会排出哪个时间段"，
避免又出现"上午的计划被全部标成 missed"的演示事故。

    python scripts/probe_plan_window.py
"""

from datetime import datetime

from app.domain import plans as rules


def show(now: datetime) -> None:
    start, end = rules.plan_window(now)
    steps = rules.suggested_steps(start, end)
    minutes = rules.window_minutes(start, end)
    print(f"现在 {now:%H:%M}  →  窗口 {start}~{end}（{minutes} 分钟）  建议 {steps} 步")


if __name__ == "__main__":
    now = datetime.now()

    print("=== 此刻真实时间 ===")
    show(now)

    print("\n=== 一天里的关键点 ===")
    for hour, minute in [(8, 0), (9, 0), (12, 0), (15, 0), (17, 55), (19, 30), (22, 40)]:
        show(now.replace(hour=hour, minute=minute, second=0, microsecond=0))