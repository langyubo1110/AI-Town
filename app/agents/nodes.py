"""
LangGraph 节点：
每个节点是一个 async 函数，
输入 state，返回要更新的字段。
"""
from datetime import UTC, datetime

from app.memory import working,episodic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agents.prompts import (
    TurnAnalysis,
    build_analysis_prompt,
    build_system_prompt,
)
from app.models import Affinity
from app.agents.state import ChatState
from app.core.logging import get_logger
from app.domain import affinity_rules,events
from app.domain.exceptions import NPCNotFoundError
from app.infra.llm import get_chat_model
from app.repos import affinity_repo, npc_repo, player_repo,event_repo
from langchain_core.runnables import RunnableConfig

from app.agents.runtime import get_redis, get_session
from app.agents.tools import MAX_TOOL_ITERATIONS, build_tools

log = get_logger(__name__)


async def load_context(state: ChatState,config: RunnableConfig) -> dict:
    """加载 NPC / 玩家 / 好感度。
        把NPC人设直接拼成系统提示词
    """
    session = get_session(config)

    npc = await npc_repo.get_by_name(session, state["npc_name"])
    if npc is None or not npc.is_active:
        raise NPCNotFoundError(f"NPC '{state['npc_name']}' 不存在或已下线")

    player = await player_repo.get_or_create_by_name(session, state["player_name"])
    affinity = await affinity_repo.get_or_create(session, player.id, npc.id)
    score = float(affinity.score)
    system_prompt = build_system_prompt(
        name=npc.name,
        title=npc.title,
        personality=npc.personality,
        expertise=npc.expertise,
        style=npc.style,
        location=npc.location,
        affinity_level=affinity_rules.level_from_score(score),
        affinity_score=score,
    )
    return {
        "player_id": player.id,
        "npc_id": npc.id,
        "affinity_id": affinity.id,
        "affinity_score": score,
        "system_prompt": system_prompt,
        "npc_title": npc.title,
        # ★ 每轮必须清零的字段。
        # 原因：state 是按 thread_id 被 checkpointer 存下来的，同一个玩家和同一个 NPC
        # 聊第二句时，上一轮写进去的 tool_trace / pending_broadcast 还在 state 里。
        # 不清会怎样：
        #   tool_trace 泄漏  → 这一轮明明没调工具，接口却返回"用了 get_time"
        #   tool_iterations  → 累计到 3 之后，这个 NPC 永远失去工具能力
        #   pending_broadcast → 上一轮升级事件被重复推送
        "tool_calls": [],
        "tool_trace": [],
        "tool_iterations": 0,
        "pending_broadcast": {},
    }

async def retrieve_memory(state: ChatState, config: RunnableConfig) -> dict:
    recent = await working.recent_turns(
        get_redis(config), npc_id=state["npc_id"], player_id=state["player_id"]
    )
    try:
        recalled = await episodic.recall(
            get_session(config),
            npc_id=state["npc_id"],
            player_id=state["player_id"],
            query=state["message"],
        )
        recalled_texts = [c.content for c in recalled]
    except Exception as exc:
        # 长期记忆是"增强"，读不到就不注入，不影响本轮对话
        log.warning("memory_recall_failed", error=type(exc).__name__, detail=str(exc)[:300])
        recalled_texts = []

    return {"recent_turns": recent, "recalled_memories": recalled_texts}

def _build_agent_messages(state: ChatState) -> list:
    """拼 agent_step 的消息：人设 + 最近对话 + 长期记忆 + 玩家这句话 + 工具轨迹。

    ★ 顺序有讲究：工具调用对（AIMessage/ToolMessage）必须排在 HumanMessage【之后】。
      这是 OpenAI tool-calling 的格式要求 —— 放错位置服务端会直接拒掉。
    """
    #人设 + 工具说明，全部在这儿
    messages: list = [SystemMessage(content=state["system_prompt"])]

    #从redis里面取出最近的5条对话
    recent = state.get("recent_turns") or []
    if recent:
        messages.append(SystemMessage(content=f"【你们最近的对话】\n" + "\n".join(recent)))

    #pg数据库里面的top5相关记忆
    recalled = state.get("recalled_memories") or []
    if recalled:
        messages.append(
            SystemMessage(content=f"【你记得关于这个人的事】\n" + "\n".join(recalled))
        )

    messages.append(HumanMessage(content=state["message"]))

    # 把已经执行过的工具调用「重放」给模型：
    # state 里只存 dict（可序列化），这里还原成 message 对象
    for step in state.get("tool_trace") or []:
        #ai要求调用的工具与
        messages.append(AIMessage(content="", tool_calls=[step["call"]]))
        #对应的工具结果
        messages.append(
            ToolMessage(content=str(step["result"]), tool_call_id=step["call"]["id"])
        )

    return messages

async def agent_step(state: ChatState, config: RunnableConfig) -> dict:
    """一次 LLM 调用：要么直接开口回答，要么要求调工具。

    为什么把「决策」和「回答」合成一个节点：
      如果拆成 decide_tool + generate_reply 两个节点，**每一轮都要多一次 LLM 调用**
      （P50 从 3.5s 涨到 5s）。合成之后，不需要工具时开销和以前完全一样。
    """
    #获取所有相关消息
    messages = _build_agent_messages(state)
    iterations = state.get("tool_iterations", 0)

    if iterations >= MAX_TOOL_ITERATIONS:
        # 调够轮数还想要工具：这一轮不再给它，强制它开口 —— 防死循环的最后一道闸
        llm = get_chat_model()
        log.info(
            "tool_budget_exhausted", npc=state["npc_name"], iterations=iterations
        )
    else:
        tools = build_tools(
            get_session(config),
            npc_id=state["npc_id"],
            player_id=state["player_id"],
        )
        llm = get_chat_model().bind_tools(tools)

    try:
        response = await llm.ainvoke(messages)
    except Exception as exc:
        log.warning(
            "llm_failed", npc=state["npc_name"], error=type(exc).__name__, detail=str(exc)[:300]
        )
        return {
            "reply": f"（{state['npc_name']}正忙着，含糊地应了一声）……你刚才说什么？",
            "llm_failed": True,
            "tool_calls": [],
        }

    usage = response.usage_metadata or {}
    calls = list(response.tool_calls or [])
    log.info(
        "llm_reply",
        npc=state["npc_name"],
        prompt_tokens=usage.get("input_tokens"),
        completion_tokens=usage.get("output_tokens"),
        tool_calls=len(calls),
    )

    if calls:
        # 这一轮不输出内容，先去查资料；执行完由 tool_node 把它送回本节点
        return {
            "tool_calls": calls,
            "tool_iterations": iterations + 1,
            "llm_failed": False,
        }

    reply = str(response.content or "").strip()
    return {
        "reply": reply or "（沉默了一下，似乎在组织语言）",
        "tool_calls": [],
        # 即使没用工具也写回，保证这个字段始终可读（评测脚本要用）
        "tool_iterations": iterations,
        "llm_failed": False,
    }

async def tool_node(state: ChatState, config: RunnableConfig) -> dict:
    """执行模型要求的工具调用，把结果写进 tool_trace。

    ★ 工具抛异常【不往外抛】：把失败当成一条观察结果回填给模型，
      它能自己换个说法或坦然说不知道。让工具失败拖垮整轮对话是最差的选择。
    """
    session = get_session(config)
    #获得全部工具列表
    tools = {
        item.name: item
        for item in build_tools(
            session, npc_id=state["npc_id"], player_id=state["player_id"]
        )
    }
    #获得工具使用记录
    trace = list(state.get("tool_trace") or [])

    #需要调用的工具列表
    for call in state.get("tool_calls") or []:
        name = str(call.get("name", ""))
        tool = tools.get(name)
        #列表中没有对应工具
        if tool is None:
            trace.append(
                {"call": call, "result": f"[没有名为 {name} 的工具]", "error": "UnknownTool"}
            )
            continue
        try:
            #有则直接执行对应工具
            result = await tool.ainvoke(call.get("args") or {})
            trace.append({"call": call, "result": str(result), "error": None})
            log.info("tool_called", tool=name, args=call.get("args"), ok=True)
        except Exception as exc:
            log.warning(
                "tool_failed", tool=name, error=type(exc).__name__, detail=str(exc)[:200]
            )
            trace.append(
                {
                    "call": call,
                    "result": f"[工具执行失败：{type(exc).__name__}]",
                    "error": type(exc).__name__,
                }
            )
    #返回执行的工具记录，清空待执行列表
    return {"tool_trace": trace, "tool_calls": []}

async def analyze_turn(state: ChatState) -> dict:
    """一次 LLM 调用：好感度变化 + 记忆重要性 + 事实抽取。"""
    if state.get("llm_failed"):
        return {"delta": 0.0, "importance": 0.0, "facts": []}

    prompt = build_analysis_prompt(
        player_message=state["message"],
        npc_reply=state["reply"],
    )
    try:
        llm = get_chat_model().with_structured_output(
            TurnAnalysis, method="function_calling"
        )
        result = await llm.ainvoke(prompt)
        log.info(
            "turn_analyzed",
            delta=result.delta,
            importance=result.importance,
            facts=len(result.facts),
        )
        return {
            "delta": float(result.delta),
            "importance": float(result.importance),
            "facts": list(result.facts),
        }
    except Exception as exc:
        log.warning("analysis_failed", error=type(exc).__name__, detail=str(exc)[:300])
        return {"delta": 0.0, "importance": 0.3, "facts": []}

async def apply_affinity(state: ChatState, config: RunnableConfig) -> dict:
    """计算新分数和新等级，并写回到 ORM 对象。"""
    session=get_session(config)

    affinity = await session.get(Affinity, state["affinity_id"])
    if affinity is None:
        raise RuntimeError(f"affinity {state['affinity_id']} 不存在")
    old_score = state["affinity_score"]
    old_level = affinity_rules.level_from_score(old_score)
    new_score, actual_delta = affinity_rules.apply_delta(old_score, state.get("delta", 0.0))
    affinity.score = new_score

    new_level = affinity_rules.level_from_score(new_score)
    return {
        "delta": actual_delta,
        "affinity_score": new_score,    # ← 同步回 state
        "old_level": old_level,
        "new_level": new_level,
        "level_changed": new_level != old_level,
    }

async def emit_level_up(state: ChatState, config: RunnableConfig) -> dict:
    """等级变化时写入事件台账，并把「待广播」交给外层。

    节点里【不做】外部副作用（推送/发邮件/调第三方），只产出纯数据，
    由路由在 persist 提交之后执行 —— 保证「推出去的，库里一定查得到」。
    """
    session = get_session(config)

    created = await event_repo.create(
        session,
        player_id=state["player_id"],
        npc_id=state["npc_id"],
        event_type=events.AFFINITY_LEVEL_UP,
        summary=events.level_up_summary(
            npc_name=state["npc_name"],
            old_level=state["old_level"],
            new_level=state["new_level"],
        ),
        payload=events.level_up_payload(
            old_level=state["old_level"],
            new_level=state["new_level"],
            score=state["affinity_score"]
        ),
    )
    # flush 才能拿到自增 id；commit 由 persist 统一做
    await session.flush()

    log.info(
        "affinity_level_changed",
        npc=state["npc_name"],
        player=state["player_name"],
        old=state["old_level"],
        new=state["new_level"],
        event_id=created.id,
    )

    return {
        "pending_broadcast": {
            "id": created.id,
            "event_type": created.event_type,
            "npc_id": created.npc_id,
            "summary": created.summary,
            "payload": created.payload,
            "created_at": datetime.now(UTC).isoformat(),
        }
    }

async def write_memory(state: ChatState,config: RunnableConfig) -> dict:
    # 1) 工作记忆（Redis）——上一轮已经通了
    text = f"玩家说「{state['message']}」，我回答「{state['reply']}」"
    await working.append_turn(
        get_redis(config),
        npc_id=state["npc_id"],
        player_id=state["player_id"],
        text=text,
    )

    # 2) 长期记忆（pgvector）
    try:
        await episodic.remember(
            get_session(config),
            npc_id=state["npc_id"],
            player_id=state["player_id"],
            turn_text=text,
            facts=state.get("facts") or [],
            importance=state.get("importance", 0.5),
        )
    except Exception as exc:
        log.exception("memory_write_failed", error=type(exc).__name__, detail=str(exc)[:300])
    return {}

async def persist(state: ChatState, config: RunnableConfig) -> dict:
    """统一提交所有变更。"""
    await  get_session(config).commit()
    return {}