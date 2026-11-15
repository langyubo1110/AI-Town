"""构建对话图。

拓扑（★ 是这次的改动：检索从串行变成**并行扇出 + 汇聚**）：

    START
      │
    load_context              查 NPC/玩家/好感度 → 拼 system_prompt
      │
      ├──────────────┬──────────────┐        ← fan-out：同一个 superstep 并行
      ▼              ▼
    retrieve_memory  retrieve_docs           记忆（pgvector）   文档（BM25+向量）
      │              │
      └──────┬───────┘                        ← fan-in：两个都完成才进下一步
             ▼
    agent_step  ★         绑上工具，一次调用决定「说话」还是「调工具」
      │
      ├─ 有 tool_calls ──→ tool_node ★ ──┐
      │                                  │
      └─ 无 tool_calls ──────────────────┼──→ analyze_turn
                                         │
    （tool_node 执行完回到 agent_step ┘ ）

    analyze_turn → apply_affinity → [emit_level_up] → write_memory → persist → END

设计要点：
1. agent_step 一次调用同时负责「决策」和「回答」，所以**不需要工具时没有任何额外开销**。
2. 检索做成并行分支而不是工具：走工具要多一次 LLM 往返（约 1.5s），
   并行节点只多一次 embedding，而且两个检索互不依赖 —— 这正是 DAG 扇出该用的地方。
3. 工具循环（agent_step ⇄ tool_node）是**刻意的环**：Agent 需要"想一想、查一下、再想想"，
   硬做成 DAG 就得展开成固定深度，既不灵活也浪费。所以这张图主干是 DAG、局部有环。
"""

from functools import lru_cache

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents import nodes
from app.agents.state import ChatState


def _route_after_agent(state: ChatState) -> str:
    """agent_step 的出口：要调工具就去 tool_node，否则进入后处理。"""
    return "tool_node" if state.get("tool_calls") else "analyze_turn"


def build_chat_graph():
    graph = StateGraph(ChatState)

    # 加载 NPC / 玩家 / 好感度
    graph.add_node("load_context", nodes.load_context)
    # 检索相关记忆（工作记忆 + 长期记忆）
    graph.add_node("retrieve_memory", nodes.retrieve_memory)
    # ★ 并行分支：查内部知识库（和 retrieve_memory 同时跑）
    graph.add_node("retrieve_docs", nodes.retrieve_docs)
    # ★ 决策 + 回答合一：绑工具调一次 LLM
    graph.add_node("agent_step", nodes.agent_step)
    # ★ 执行工具调用，把结果写进 tool_trace
    graph.add_node("tool_node", nodes.tool_node)
    # 用 LLM 判断这次对话该加/减多少好感度
    graph.add_node("analyze_turn", nodes.analyze_turn)
    # 计算新分数和新等级，并写回到 ORM 对象
    graph.add_node("apply_affinity", nodes.apply_affinity)
    # 等级变化时触发（events 表 + 推送）
    graph.add_node("emit_level_up", nodes.emit_level_up)
    # 写入记忆库
    graph.add_node("write_memory", nodes.write_memory)
    # 统一提交所有变更
    graph.add_node("persist", nodes.persist)

    graph.add_edge(START, "load_context")
    # ★ fan-out：两条边从同一个节点出发，LangGraph 会把它们放进同一个 superstep 并行执行
    graph.add_edge("load_context", "retrieve_memory")
    graph.add_edge("load_context", "retrieve_docs")
    # ★ fan-in：agent_step 有两条入边，必须两个都完成才会开始（天然的屏障）
    graph.add_edge("retrieve_memory", "agent_step")
    graph.add_edge("retrieve_docs", "agent_step")

    # ★ 工具循环：需要工具 → 执行 → 回到 agent_step 再判断一次
    graph.add_conditional_edges(
        "agent_step",
        _route_after_agent,
        {
            "tool_node": "tool_node",
            "analyze_turn": "analyze_turn",
        },
    )
    graph.add_edge("tool_node", "agent_step")

    graph.add_edge("analyze_turn", "apply_affinity")

    # 条件边：等级变了才走 emit_level_up
    graph.add_conditional_edges(
        "apply_affinity",
        lambda state: "emit_level_up" if state.get("level_changed") else "write_memory",
        {
            "emit_level_up": "emit_level_up",
            "write_memory": "write_memory",
        },
    )
    graph.add_edge("emit_level_up", "write_memory")
    graph.add_edge("write_memory", "persist")
    graph.add_edge("persist", END)

    # 内存版 checkpointer：进程重启就丢
    return graph.compile(checkpointer=MemorySaver())


@lru_cache
def get_chat_graph():
    """编译一次，全程复用。"""
    return build_chat_graph()