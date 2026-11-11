"""LangGraph 的状态定义。

铁律：这里只能放「可序列化的业务数据」（str / int / float / bool / list / dict / None）。
- 连接对象（session / redis）→ 走 config["configurable"]，见 app/agents/runtime.py
- 数据库实体（NPC / Player / Affinity）→ 只放 id，需要时用 session.get() 按需取回

字段的读写形状：
    调用方 ──→ [输入] ──load_context──→ [身份 + system_prompt]
                            │
                            ├──retrieve_memory──→ [recent_turns / recalled_memories]
                            ├──generate_reply───→ [reply / llm_failed]
                            ├──analyze_turn─────→ [delta / importance / facts]
                            ├──apply_affinity───→ [old_level / new_level / level_changed]
                            └──emit_level_up / write_memory / persist ──→ 只读

total=False：所有字段都是「可选」的。
运行时 state 就是普通 dict，框架不保证 key 存在，所以：
    - 必填输入 / 关键计算结果 → state["x"]        （缺失就是 bug，该立刻炸）
    - 可选中间产物           → state.get("x") or [] （缺失是合法状态，如"没有记忆"）
"""

from typing import TypedDict


class ChatState(TypedDict, total=False):
    """一次对话在图里流转时携带的全部数据。"""

    # ---- 输入：由调用方（路由 / 探针脚本）提供 ----
    player_name: str       # 玩家名字。用名字不用 id：可能是新玩家，靠 get_or_create 建号
    npc_name: str          # NPC 名字。load_context 靠它查 NPC
    message: str           # 玩家原话。既是 HumanMessage 的内容，也是向量检索的 query

    # ---- 身份：全是基本类型，只存 id 不存实体 ----
    player_id: int         # 玩家主键。load_context 写；写记忆 / 写事件时读
    npc_id: int            # NPC 主键。load_context 写；写记忆 / 写事件时读
    affinity_id: int       # 好感度行主键。apply_affinity 靠它 session.get() 取回 ORM 改分数
    npc_title: str         # NPC 头衔，如「Python工程师」。仅为了让 ChatOut 能返回给前端显示

    # ---- 本轮上下文 ----
    system_prompt: str     # 已拼好的完整人设提示词（人设+专长+风格+地点+关系等级+60字限制）。
                           # generate_reply 直接使用，不再碰 NPC 实体
    affinity_score: float  # 好感度分数。load_context 写初值 → apply_affinity 覆盖为新值 → 再写回 ORM
                           # 由 persist 提交。注意：真值在数据库，state 里这份是"本轮工作副本"

    # ---- LLM 结果 ----
    reply: str             # NPC 的回复文本。LLM 失败时放降级文案
    llm_failed: bool       # 降级标记。True 时 analyze_turn 直接跳过（不拿假回复去做情感分析），delta=0

    # ---- 好感度结果 ----
    delta: float           # 实际生效的变化量。被写两次：analyze_turn 写 LLM 建议值
                           # → apply_affinity 覆盖为裁剪后的真实值（如 99 分时 +8 只算 +1）
    old_level: str         # 变化前的等级，如「友好」。必须在改 score 之前算
    new_level: str         # 变化后的等级，如「亲密」
    level_changed: bool    # 条件边路由依据。True → emit_level_up；False → 直接 write_memory

    # ---- 记忆 ----
    recent_turns: list[str]       # 工作记忆：Redis 中最近 5 轮，按时间正序，2 小时 TTL。
                                  # 拼提示词时用「你们最近的对话」
    recalled_memories: list[str]  # 长期记忆：pgvector 三因子重排后的 top-5 内容（只有文本，
                                  # 分数在 recall 里打日志）。拼提示词时用「你记得关于这个人的事」
    importance: float             # 本轮对话作为记忆的重要性 0~1，由 LLM 打分。
                                  # write_memory 用它填 memories.importance 列
    facts: list[str]              # 本轮抽取的关于玩家的稳定事实（0~2 条）。
                                  # write_memory 把它们另存为 memory_type="fact" 的记录

    # ---- 待执行的副作用 ----
    # 纯数据（dict），由图产出、由路由在 persist 提交之后执行。
    # 节点里不做外部副作用 —— 保证「推出去的，库里一定查得到」。
    pending_broadcast: dict

    # ---- 工具调用（ReAct 循环）----
    # 本轮模型要执行的工具调用列表（agent_step 写，tool_node 读）
    # 结构：[{"name": "get_time", "args": {}, "id": "call_xxx", "type": "tool_call"}]
    tool_calls: list[dict]

    # 已执行的工具轨迹。[{"call": 上面那个 dict, "result": str, "error": None|str}]
    # 每次回到 agent_step 时，用它重建 ToolMessage 让模型看到"我刚才查到了什么"
    tool_trace: list[dict]

    # 已经进过几轮工具循环。达到上限后不再给模型工具，强制它开口 —— 防死循环
    tool_iterations: int