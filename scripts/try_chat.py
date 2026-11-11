"""端到端验证：跨工作记忆窗口的长期记忆召回。

8 轮对话：
  第 1 轮埋信息
  第 2~7 轮灌废话，把 Redis 的 5 条窗口挤出去
  第 8 轮问"我之前说我在学什么" → 只能靠 pgvector 答出来
"""

import sys

import httpx

# Windows 控制台防止中文/emoji 编码报错
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8000/api/chat"
PLAYER = "小明"
NPC = "张三"

MESSAGES = [
    "我叫小明，我是前端工程师，最近在学 Rust",   # 1  ← 埋信息
    "今天天气不错啊",                             # 2
    "你平时喜欢干什么？",                         # 3
    "这条街晚上热闹吗？",                         # 4
    "哈哈，听起来挺有意思",                       # 5
    "嗯嗯，我也这么觉得",                         # 6
    "好的，改天再聊",                             # 7
    "对了，我之前跟你说过我在学什么吗？",         # 8  ← 验收
]


def main() -> None:
    with httpx.Client(timeout=180.0) as client:
        for i, msg in enumerate(MESSAGES, 1):
            resp = client.post(
                BASE,
                json={"player_name": PLAYER, "npc_name": NPC, "message": msg},
            )
            resp.raise_for_status()          # 失败立刻炸，不要静默
            data = resp.json()

            mark = "  ★★★ 验收" if i == len(MESSAGES) else ""
            print(f"[{i}] 我：{msg}{mark}")
            print(f"    {data['npc_name']}：{data['reply']}")
            print(
                f"    score={data['affinity_score']:.1f} "
                f"delta={data['affinity_delta']:+.1f} "
                f"level={data['affinity_level']}"
            )
            print()


if __name__ == "__main__":
    main()