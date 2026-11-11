"""构建对话图。

拓扑（★ 是这次新加的工具循环）：

    START
      │
    load_context          查 NPC/玩家/好感度 → 拼 system_prompt
      │
    retrieve_memory       取工作记忆 + 长期记忆
      │
    agent_step  ★         绑上工具，一次调用决定「说话」还是「调工具」
      │
      ├─ 有 tool_calls ──→ tool_node ★ ──┐
      │                                  │
      └─ 无 tool_calls ──────────────────┼──→ analyze_turn
                                         │
    （tool_node 执行完回到 agent_step ┘ ）

    analyze_turn → apply_affinity → [emit_level_up] → write_memory → persist → END

设计要点：agent_step 一次调用同时负责「决策」和「回答」，
所以**不需要工具时没有任何额外开销**（不是在它前面再加一个分类节点）。
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
    graph.add_edge("load_context", "retrieve_memory")
    graph.add_edge("retrieve_memory", "agent_step")

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