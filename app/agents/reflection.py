"""NPC 的反思：把一天的经历压缩成几条洞察。

这是 Generative Agents 三件套里缺的那一块（记忆 ✅ / 规划 ✅ / 反思 ⬜）。
和计划的区别：
    计划 = 我打算做什么（向前看）
    反思 = 我最近是什么状态（向后看，但会改变计划）
"""

from pydantic import BaseModel, Field

from app.agents.plans import get_chat_model
from app.core.logging import get_logger

log = get_logger(__name__)


class ReflectionDraft(BaseModel):
    """LLM 结构化输出的形状。"""

    insights: list[str] = Field(
        ...,
        description="2~3 条洞察，每条 30 字以内，第一人称，是对自己的判断而不是事情复述",
    )


def build_reflection_prompt(
    *,
    name: str,
    title: str,
    done_goals: list[str],
    missed_goals: list[str],
    memories: list[str],
) -> str:
    done_text = "\n".join(f"- {g}" for g in done_goals) or "（今天还没做成什么）"
    missed_text = "\n".join(f"- {g}" for g in missed_goals) or "（没有落下的）"
    memory_text = "\n".join(f"- {m}" for m in memories) or "（还没有记忆）"

    return f"""你是{name}，一名{title}。现在是深夜，你在回顾今天。

【今天做成的事】
{done_text}

【今天没做成的事】
{missed_text}

【你记得的最近发生的事】
{memory_text}

请给**自己**写 2~3 条洞察。

【要求】
1. 每条 30 字以内，第一人称（"我…"）
2. 必须是**判断/结论**，不能是事情复述
   ❌ "我今天 code review 了队友的 PR"
   ✅ "我总在帮别人兜底，自己的模块反而没推进"
3. 可以观察自己的情绪、工作节奏、和别人的关系
4. 不要给建议、不要喊口号（"明天要更努力"这种不算洞察）
"""


async def reflect(
    *,
    name: str,
    title: str,
    done_goals: list[str],
    missed_goals: list[str],
    memories: list[str],
) -> list[str]:
    """调一次 LLM 产出洞察。失败返回空列表（不抛）—— 反思失败不该让小镇停摆。"""
    prompt = build_reflection_prompt(
        name=name,
        title=title,
        done_goals=done_goals,
        missed_goals=missed_goals,
        memories=memories,
    )
    try:
        llm = get_chat_model().with_structured_output(
            ReflectionDraft, method="function_calling"
        )
        draft = await llm.ainvoke(prompt)
        # 兜底清洗：去掉空串、超长的截断、最多 3 条
        cleaned = [s.strip()[:60] for s in draft.insights if s and s.strip()]
        return cleaned[:3]
    except Exception as exc:
        log.warning(
            "reflect_failed",
            npc=name,
            error=type(exc).__name__,
            detail=str(exc)[:200],
        )
        return []