"""生成 README 用的架构图（SVG）。

为什么用 SVG 而不是 PNG：
- GitHub / VS Code 的 Markdown 预览都直接渲染 SVG
- 中文在 SVG 里用系统字体渲染，cairosvg 转 PNG 反而容易丢字

布局约定：box() 会自动把高度撑到"放得下所有文字"，调用方按返回的 y 往下排。

用法：python -m scripts.make_diagrams
输出：docs/images/*.svg
"""

from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "docs" / "images"

FONT = (
    "Segoe UI, Microsoft YaHei, PingFang SC, Noto Sans SC, "
    "Helvetica Neue, Arial, sans-serif"
)

BG = "#ffffff"
INK = "#111827"
SUB = "#4b5563"
LINE = "#d1d5db"

BLUE = "#2563eb"
BLUE_BG = "#eff6ff"
PURPLE = "#7c3aed"
PURPLE_BG = "#f5f3ff"
GREEN = "#059669"
GREEN_BG = "#ecfdf5"
ORANGE = "#ea580c"
ORANGE_BG = "#fff7ed"
GRAY = "#6b7280"
GRAY_BG = "#f9fafb"


def esc(text: str) -> str:
    """文本进 SVG 前必须转义：`<=>` 里的 < 会被当成标签开头，XML 直接非法。"""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def head(w: int, h: int, title: str) -> list[str]:
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="{w}" height="{h}" font-family="{FONT}">',
        f'  <rect width="{w}" height="{h}" fill="{BG}"/>',
        "  <defs>",
    ]
    for name, color in [
        ("blue", BLUE),
        ("green", GREEN),
        ("orange", ORANGE),
        ("purple", PURPLE),
        ("gray", GRAY),
    ]:
        out.append(
            f'    <marker id="a{name}" viewBox="0 0 10 10" refX="9" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{color}"/></marker>'
        )
    out += [
        "  </defs>",
        f'  <text x="32" y="40" font-size="19" font-weight="600" fill="{INK}">{esc(title)}</text>',
    ]
    return out


def foot() -> list[str]:
    return ["</svg>"]


def box(
    x: float,
    y: float,
    w: float,
    title: str,
    lines: list[str] | None = None,
    *,
    fill: str = GRAY_BG,
    stroke: str = LINE,
    title_color: str = INK,
    radius: float = 8,
    title_size: int = 14,
    pad: float = 14,
) -> tuple[list[str], float]:
    """画一个盒子，返回 (svg 片段, 实际高度)。

    高度自动计算：标题 24 + 每行 18 + 底部留白。手写高度几乎必然会裁掉最后一行。
    """
    lines = lines or []
    h = 24 + 18 * len(lines) + pad
    out = [
        f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>',
        f'  <text x="{x + w / 2}" y="{y + 22}" text-anchor="middle" '
        f'font-size="{title_size}" font-weight="600" fill="{title_color}">{esc(title)}</text>',
    ]
    for i, line in enumerate(lines):
        out.append(
            f'  <text x="{x + w / 2}" y="{y + 42 + 18 * i}" text-anchor="middle" '
            f'font-size="12" fill="{SUB}">{esc(line)}</text>'
        )
    return out, h


def label(x: float, y: float, text: str, *, size: int = 12, color: str = SUB, anchor: str = "middle") -> list[str]:
    return [
        f'  <text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" '
        f'fill="{color}">{esc(text)}</text>'
    ]


def arrow(x1: float, y1: float, x2: float, y2: float, *, color: str = BLUE,
          name: str = "blue", dash: str | None = None, width: float = 1.8) -> list[str]:
    extra = f' stroke-dasharray="{dash}"' if dash else ""
    return [
        f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
        f'stroke-width="{width}"{extra} marker-end="url(#a{name})"/>'
    ]


def path_arrow(d: str, *, color: str = BLUE, name: str = "blue", dash: str | None = None) -> list[str]:
    extra = f' stroke-dasharray="{dash}"' if dash else ""
    return [
        f'  <path d="{d}" fill="none" stroke="{color}" stroke-width="1.8"{extra} '
        f'marker-end="url(#a{name})"/>'
    ]


def legend(x: float, y: float, items: list[tuple[str, str, str]]) -> list[str]:
    out = [f'  <text x="{x}" y="{y}" font-size="12.5" font-weight="600" fill="{INK}">图例</text>']
    for i, (color, dash, text) in enumerate(items):
        yy = y + 20 * (i + 1)
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        out.append(
            f'  <line x1="{x}" y1="{yy - 4}" x2="{x + 26}" y2="{yy - 4}" stroke="{color}" '
            f'stroke-width="1.8"{extra}/>'
        )
        out.append(f'  <text x="{x + 34}" y="{yy}" font-size="11.5" fill="{SUB}">{esc(text)}</text>')
    return out


# ---------------------------------------------------------------- 1. 部署架构
def architecture() -> list[str]:
    W, H = 980, 700
    s = head(W, H, "AI Town 部署架构")
    s += [
        f'  <rect x="24" y="58" width="932" height="600" rx="10" fill="none" '
        f'stroke="{LINE}" stroke-dasharray="6,4"/>'
    ]

    cx = 490
    part, h = box(cx - 100, 76, 200, "浏览器", ["Vue 3 + PixiJS 8", "WASD 移动 / 按 E 对话"],
                  fill=BLUE_BG, stroke=BLUE, title_color=BLUE)
    s += part
    s += arrow(cx, 76 + h, cx, 172, color=BLUE)
    s += label(cx + 10, 160, "HTTP 8080 / WS", size=11, anchor="start")

    part, hw = box(cx - 150, 174, 300, "web 容器 · Nginx",
                   ["/ → 静态 dist", "/api → api:8000", "/ws → api:8000（含 Upgrade 头）"],
                   fill=ORANGE_BG, stroke=ORANGE, title_color=ORANGE)
    s += part

    top2 = 174 + hw + 34
    s += arrow(cx - 50, 174 + hw, 350, top2 - 4, color=BLUE)
    s += arrow(cx + 50, 174 + hw, 640, top2 - 4, color=GRAY, name="gray", dash="5,4")

    part, ha = box(190, top2, 320, "api 容器 · FastAPI",
                   ["POST /api/chat → LangGraph", "GET /api/events · WS /ws/events",
                    "GET /api/town/plans"], fill=GREEN_BG, stroke=GREEN, title_color=GREEN)
    s += part
    part, hb = box(560, top2, 300, "worker 容器",
                   ["consumer：XREADGROUP 消费任务", "ticker：每 60s 推进日计划",
                    "与 api 同镜像，只是 command 不同"],
                   fill=PURPLE_BG, stroke=PURPLE, title_color=PURPLE)
    s += part

    top3 = top2 + max(ha, hb) + 36
    s += arrow(250, top2 + ha, 250, top3 - 4, color=GREEN, name="green")
    s += arrow(420, top2 + ha, 470, top3 - 4, color=GREEN, name="green")
    s += arrow(700, top2 + hb, 600, top3 - 4, color=GREEN, name="green")
    s += arrow(790, top2 + hb, 790, top3 - 4, color=GREEN, name="green")

    part, _ = box(150, top3, 300, "postgres + pgvector",
                  ["players / npcs / affinities", "memories（1024 维）/ events"],
                  fill=GRAY_BG, stroke=GRAY)
    s += part
    part, _ = box(520, top3, 300, "redis",
                  ["List：工作记忆 5 轮 / 2h", "Stream：任务队列 + ACK",
                   "Pub/Sub：实时推送"], fill=GRAY_BG, stroke=GRAY)
    s += part

    s += label(500, top3 + 108, "api 与 worker 共用一份代码与镜像；两者只通过 Redis（Stream / Pub/Sub）和数据库交接",
               size=12)
    s += legend(40, top3 + 120, [(BLUE, "", "请求"), (GREEN, "", "数据读写"), (GRAY, "5,4", "异步 / 推送")])
    s += foot()
    return s


# ---------------------------------------------------------------- 2. 对话链路
def chat_flow() -> list[str]:
    W, H = 1000, 900
    s = head(W, H, "一次对话的完整链路（含工具循环）")
    cx, bw = 290, 240
    left = cx - bw / 2

    steps = [
        ("START", [], GRAY_BG, GRAY),
        ("load_context", ["查 NPC / 玩家 / 好感度", "拼 system_prompt"], BLUE_BG, BLUE),
        ("retrieve_memory", ["Redis 取最近 5 轮", "pgvector 三因子召回 Top-5"], GREEN_BG, GREEN),
        ("agent_step ★", ["绑工具调一次 LLM", "要么回答，要么要求调工具"], PURPLE_BG, PURPLE),
        ("analyze_turn", ["一次结构化输出", "delta / importance / facts"], BLUE_BG, BLUE),
        ("apply_affinity", ["算新分数与新等级"], BLUE_BG, BLUE),
        ("write_memory", ["写 Redis 工作记忆", "写 pgvector 长期记忆"], GREEN_BG, GREEN),
        ("persist", ["全图唯一 commit 点"], ORANGE_BG, ORANGE),
        ("END", [], GRAY_BG, GRAY),
    ]

    y = 66
    spans: list[tuple[float, float]] = []
    for title, lines, fill, stroke in steps:
        part, h = box(left, y, bw, title, lines, fill=fill, stroke=stroke, title_color=stroke)
        s += part
        spans.append((y, h))
        y += h + 30

    for i in range(len(spans) - 1):
        s += arrow(cx, spans[i][0] + spans[i][1], cx, spans[i + 1][0] - 4, color=BLUE)

    # 工具循环：两条水平箭头，一上一下，互不干扰
    ay, ah = spans[3]
    mid = ay + ah / 2
    part, th = box(580, ay - 10, 210, "tool_node ★", ["执行工具 / 异常当观察结果", "结果写回 tool_trace"],
                   fill=PURPLE_BG, stroke=PURPLE, title_color=PURPLE)
    s += part
    s += arrow(left + bw, mid - 18, 576, mid - 18, color=PURPLE, name="purple")
    s += label(left + bw + 96, mid - 26, "有 tool_calls", size=11, color=PURPLE)
    s += arrow(576, mid + 26, left + bw + 4, mid + 26, color=PURPLE, name="purple")
    s += label(left + bw + 96, mid + 44, "执行完回来再判断", size=11, color=PURPLE)

    # 条件边：简化成一个短箭头 + 说明盒，避免和主干交叉
    cy, ch = spans[5]
    s += arrow(left + bw, cy + 26, 500, cy + 26, color=ORANGE, name="orange", dash="5,4")
    s += label(455, cy + 16, "等级变化", size=11, color=ORANGE)
    part, _ = box(500, cy - 10, 250, "emit_level_up（条件边）",
                  ["写 events 台账", "产出 pending_broadcast", "由路由在 commit 后推送"],
                  fill=ORANGE_BG, stroke=ORANGE, title_color=ORANGE)
    s += part

    s += label(320, 884, "工具调用是「决策 + 回答合一」：不需要工具时不会多花一次 LLM 调用", size=12)
    s += legend(700, 76, [(BLUE, "", "主干"), (PURPLE, "", "工具循环"), (ORANGE, "5,4", "条件边")])
    s += foot()
    return s


# ---------------------------------------------------------------- 3. 记忆
def memory() -> list[str]:
    W, H = 980, 760
    s = head(W, H, "两级记忆与两段式检索（RAG）")

    part, h = box(40, 76, 240, "玩家这句话", ['"我不吃什么来着？"'], fill=BLUE_BG, stroke=BLUE, title_color=BLUE)
    s += part

    s += label(310, 96, "写入路径", size=13, color=GREEN, anchor="start")
    part, _ = box(310, 108, 200, "write_memory", ["每轮对话 + 抽取的事实"], fill=GREEN_BG, stroke=GREEN, title_color=GREEN)
    s += part
    part, _ = box(600, 92, 200, "Redis List", ["最近 5 轮 · TTL 2h"], fill=GRAY_BG, stroke=GRAY)
    s += part
    part, _ = box(600, 178, 200, "pgvector memories", ["1024 维 · 永久保存"], fill=GRAY_BG, stroke=GRAY)
    s += part
    s += arrow(510, 130, 596, 116, color=GREEN, name="green", dash="5,3")
    s += arrow(510, 156, 596, 200, color=GREEN, name="green", dash="5,3")

    s += label(40, 276, "读取路径", size=13, color=PURPLE, anchor="start")
    part, _ = box(40, 286, 150, "embedding", ["text-embedding-v3"], fill=PURPLE_BG, stroke=PURPLE, title_color=PURPLE)
    s += part
    s += arrow(190, 313, 234, 313, color=PURPLE, name="purple")
    part, _ = box(234, 286, 170, "SQL 粗排", ["ORDER BY <=> LIMIT 20"], fill=GRAY_BG, stroke=GRAY)
    s += part

    # 粗排 → 三个因子（先到汇合点，再分别指向三个盒子）
    fan_x = 440
    s += arrow(404, 313, fan_x, 313, color=PURPLE, name="purple")
    for yy in (250, 313, 376):
        s += [
            f'  <line x1="{fan_x}" y1="313" x2="{fan_x}" y2="{yy}" stroke="{PURPLE}" stroke-width="1.6"/>'
        ]
        s += arrow(fan_x, yy, 468, yy, color=PURPLE, name="purple")

    part, _ = box(470, 228, 160, "relevance", ["1 − 余弦距离"], fill=BLUE_BG, stroke=BLUE, title_color=BLUE, title_size=13)
    s += part
    part, _ = box(470, 291, 160, "recency", ["0.5 ^ (age / 138h)"], fill=GREEN_BG, stroke=GREEN, title_color=GREEN, title_size=13)
    s += part
    part, _ = box(470, 354, 160, "importance", ["LLM 打分 0~1"], fill=ORANGE_BG, stroke=ORANGE, title_color=ORANGE, title_size=13)
    s += part

    for yy in (264, 327, 390):
        s += arrow(630, yy, 676, 327, color=PURPLE, name="purple")
    part, _ = box(676, 288, 150, "三因子重排", ["0.85 / 0.05 / 0.10", "取 Top-5"], fill=PURPLE_BG, stroke=PURPLE, title_color=PURPLE)
    s += part
    s += arrow(826, 327, 852, 327, color=PURPLE, name="purple")
    part, _ = box(852, 300, 100, "注入 prompt", ["你记得…"], fill=BLUE_BG, stroke=BLUE, title_color=BLUE, title_size=12)
    s += part

    # 复习效应回流：从重排盒子向下引出，用文字说明去向（不画到别处以免误导）
    s += arrow(751, 360, 751, 408, color=GREEN, name="green", dash="5,3")
    s += label(751, 428, "命中后 access_count + 1 / 刷新 last_access_at（复习效应）", size=11, color=GREEN)

    part, _ = box(40, 470, 900, "为什么分两层", [
        "工作记忆管「连贯性」：刚才说了什么 → 按时间取，精确、便宜、可丢",
        "长期记忆管「人格一致性」：三个月前说过什么 → 按语义取，模糊、持久、不可丢",
    ], fill=GRAY_BG, stroke=LINE)
    s += part
    part, _ = box(40, 574, 900, "为什么两段式", [
        "数据库擅长按向量距离取前 N（能吃到 ANN 索引）；应用层擅长可解释、可调参、可单测的加权",
        "全放 SQL → 没法做消融实验；全放 Python → 要把整个记忆池拉进内存",
    ], fill=GRAY_BG, stroke=LINE)
    s += part

    s += legend(40, 690, [(GREEN, "5,3", "写 / 强化"), (PURPLE, "", "检索")])
    s += foot()
    return s


# ---------------------------------------------------------------- 4. 异步 + 实时
def async_flow() -> list[str]:
    W, H = 980, 620
    s = head(W, H, "异步任务与实时推送")

    part, h = box(40, 80, 200, "ticker（每 60s）", ["SET NX 抢锁", "XPENDING 背压", "推进日计划 / 派闲聊"],
                  fill=PURPLE_BG, stroke=PURPLE, title_color=PURPLE)
    s += part
    s += arrow(240, 130, 296, 130, color=ORANGE, name="orange")
    s += label(268, 116, "XADD", size=11, color=ORANGE)

    part, _ = box(298, 96, 190, "Redis Stream", ["aitown:events", "消费组 aitown-workers"], fill=GRAY_BG, stroke=GRAY)
    s += part
    s += arrow(488, 130, 544, 130, color=ORANGE, name="orange")
    s += label(492, 118, "XREAD", size=10.5, color=ORANGE)

    part, _ = box(546, 88, 200, "consumer", ["handle_npc_chat", "调 LLM 让两个 NPC 聊"], fill=GREEN_BG, stroke=GREEN, title_color=GREEN)
    s += part

    s += arrow(646, 88 + 70, 646, 196, color=BLUE, name="blue")
    part, _ = box(536, 198, 220, "commit（先落库）", ["events 表写入"], fill=BLUE_BG, stroke=BLUE, title_color=BLUE)
    s += part

    s += path_arrow("M 756,226 L 856,226 L 856,284", color=GREEN, name="green", dash="5,3")
    part, _ = box(766, 288, 180, "PUBLISH", ["按玩家分频道"], fill=GREEN_BG, stroke=GREEN, title_color=GREEN)
    s += part
    s += arrow(646, 252, 646, 286, color=GREEN, name="green")
    part, _ = box(536, 288, 220, "XACK（最后确认）", ["消息离开 pending"], fill=ORANGE_BG, stroke=ORANGE, title_color=ORANGE)
    s += part

    s += arrow(856, 350, 856, 392, color=GRAY, name="gray", dash="5,4")
    part, _ = box(726, 394, 230, "ws.py（api 进程）", ["SUBSCRIBE → send_text"], fill=BLUE_BG, stroke=BLUE, title_color=BLUE)
    s += part
    s += arrow(726, 420, 672, 420, color=BLUE, name="blue")
    part, _ = box(482, 394, 190, "浏览器", ["EventFeed 面板"], fill=BLUE_BG, stroke=BLUE, title_color=BLUE)
    s += part

    part, _ = box(40, 288, 470, "三条规矩", [
        "① 顺序：commit → publish → ACK",
        "  先落库，推出去的一定查得到；后 ACK，消息还能重放",
        "② 推送失败只 warning：前端还有轮询兜底（推拉结合）",
        "③ 崩在 commit 之后、ACK 之前 → 重启重做（at-least-once）",
    ], fill=GRAY_BG, stroke=LINE)
    s += part

    part, _ = box(40, 440, 420, "为什么任务用 Stream、推送用 Pub/Sub", [
        "任务丢了 = 功能缺失 → 必须可靠（pending + ACK）",
        "推送丢了 = 晚几秒看到 → 可丢，轮询能补",
    ], fill=GRAY_BG, stroke=LINE)
    s += part

    s += legend(40, 532, [(ORANGE, "", "任务投递"), (GREEN, "5,3", "广播"), (GRAY, "5,4", "推送下行")])
    s += label(600, 560, "worker 与 api 是两个进程：靠 Redis 交接，不共享内存", size=12)
    s += foot()
    return s


# ---------------------------------------------------------------- 5. WS 时序
def ws_sequence() -> list[str]:
    W, H = 940, 640
    s = head(W, H, "WebSocket 连接的生命周期")
    xs = {"browser": 140, "ws": 340, "redis": 560, "worker": 790}
    names = [
        ("browser", "浏览器", BLUE),
        ("ws", "ws.py（api）", GREEN),
        ("redis", "Redis Pub/Sub", GRAY),
        ("worker", "worker", PURPLE),
    ]

    for key, name, color in names:
        x = xs[key]
        part, _ = box(x - 80, 64, 160, name, [], fill=BG, stroke=color, title_color=color, title_size=13)
        s += part
        s.append(
            f'  <line x1="{x}" y1="116" x2="{x}" y2="546" stroke="{LINE}" stroke-width="1.5" '
            f'stroke-dasharray="6,5"/>'
        )

    rows = [
        (156, "browser", "ws", "WS 握手 /ws/events?player_id=6", BLUE, "blue", None, True),
        (196, "ws", "redis", "SUBSCRIBE aitown:events:player:6", GREEN, "green", None, True),
        (236, "ws", "ws", "accept() + 启动 _pump / _watch", GREEN, "green", None, False),
        (286, "worker", "redis", "PUBLISH {张三去会议室…}", PURPLE, "purple", None, True),
        (326, "redis", "ws", "消息到达 pubsub.listen()", GRAY, "gray", "5,4", True),
        (366, "ws", "browser", "send_text(JSON)", BLUE, "blue", None, True),
        (406, "redis", "ws", "第二条消息到达", GRAY, "gray", "5,4", True),
        (446, "ws", "browser", "send_text(JSON)", BLUE, "blue", None, True),
        (486, "browser", "ws", "关闭页面", ORANGE, "orange", None, True),
        (526, "ws", "redis", "UNSUBSCRIBE + aclose", GREEN, "green", None, True),
    ]

    for y, src, dst, text, color, marker, dash, has_arrow in rows:
        if not has_arrow:
            x = xs[src]
            s += [
                f'  <rect x="{x - 4}" y="{y - 14}" width="8" height="30" fill="{color}" opacity="0.85"/>',
                f'  <text x="{x + 16}" y="{y + 4}" font-size="11.5" fill="{SUB}">{esc(text)}</text>',
            ]
            continue
        x1, x2 = xs[src], xs[dst]
        s += arrow(x1, y, x2, y, color=color, name=marker, dash=dash)
        s += label((x1 + x2) / 2, y - 9, text, size=11)

    part, _ = box(40, 556, 860, "断线处理", [
        "两任务任一结束 → asyncio.wait(FIRST_COMPLETED) → finally：cancel + await + unsubscribe + aclose",
        "前端：指数退避重连（1s→2s→…→30s，带抖动），断线期间靠轮询 GET /api/events 补齐",
    ], fill=GRAY_BG, stroke=LINE, title_size=13)
    s += part
    s += foot()
    return s


# ---------------------------------------------------------------- 6. 数据模型
def data_model() -> list[str]:
    W, H = 960, 660
    s = head(W, H, "数据模型（5 张表）")

    # 左：players；右：npcs；中间：三张子表 —— 两个父表各连三条，箭头不交叉
    part, ph = box(40, 250, 190, "players", ["id · name", "is_active"], fill=BLUE_BG, stroke=BLUE, title_color=BLUE)
    s += part
    part, nh = box(730, 250, 190, "npcs", ["id · name · title", "location · is_active"], fill=PURPLE_BG, stroke=PURPLE, title_color=PURPLE)
    s += part

    children = [
        (110, "affinities", ["player_id (FK) · npc_id (FK)", "score 0~100", "UNIQUE(player_id, npc_id)"], GREEN_BG, GREEN),
        (280, "memories", ["player_id + npc_id (FK)", "content · embedding vector(1024)", "importance · access_count"], GREEN_BG, GREEN),
        (450, "events", ["player_id (FK) · npc_id (FK, 可空)", "type · summary", "payload (JSONB)"], ORANGE_BG, ORANGE),
    ]
    xs, ws = 330, 300
    for y, title, lines, fill, stroke in children:
        part, h = box(xs, y, ws, title, lines, fill=fill, stroke=stroke, title_color=stroke)
        s += part
        cy = y + h / 2
        # players → 子表（从左出，进子表左边）
        s += arrow(230, 250 + ph / 2 if y < 250 else 250 + ph / 2, xs - 4, cy, color=BLUE)
        # npcs → 子表（从右出，进子表右边）
        s += arrow(730, 250 + nh / 2, xs + ws + 4, cy, color=PURPLE, name="purple")
        s += label(xs - 34, cy - 6, "1:n", size=10.5)
        s += label(xs + ws + 34, cy - 6, "1:n", size=10.5)

    part, _ = box(40, 400, 230, "约束与索引", [
        "UNIQUE(player_id, npc_id)",
        "CHECK(score BETWEEN 0 AND 100)",
        "events 索引 (player_id, id)",
        "memories：暂不建 HNSW",
    ], fill=GRAY_BG, stroke=LINE, title_size=13)
    s += part

    part, _ = box(680, 400, 240, "设计要点", [
        "ON DELETE CASCADE：删 NPC",
        "  连带删记忆 / 好感度 / 事件",
        "affinities 是关系表，",
        "  不是玩家表上的 JSON",
        "events 只增不改（台账）",
    ], fill=GRAY_BG, stroke=LINE, title_size=13)
    s += part

    s += label(480, 610, "两个父表各自连三张子表；子表都是「谁和谁」的复合键，所以隔离查询永远带双维度", size=11.5)
    s += foot()
    return s


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    builders = {
        "architecture": architecture,
        "chat-flow": chat_flow,
        "memory": memory,
        "async-flow": async_flow,
        "ws-sequence": ws_sequence,
        "data-model": data_model,
    }
    for name, build in builders.items():
        path = OUT / f"{name}.svg"
        path.write_text("\n".join(build()), encoding="utf-8")
        print(f"written: {path}")


if __name__ == "__main__":
    main()