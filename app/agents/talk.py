"""NPC 之间的对话。

刻意【不】使用 LangGraph：这里没有条件分支、没有需要恢复的状态、
没有中断继续，一个 for 循环就是最贴切的表达。

什么时候才该上图？——当"下一句说什么/跟谁说"由状态决定时。
"""

from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.prompts import build_npc_chat_prompt, build_turn_input
from app.core.logging import get_logger
from app.infra.llm import get_chat_model

log = get_logger(__name__)

MAX_TURNS = 3          # 每人最多说 3 轮，防止一条消息跑太久


@dataclass(frozen=True)
class NpcPersona:
    """只保留对话需要的字段（和 state 一样：不放 ORM 实体）。"""

    name: str
    title: str
    personality: str
    expertise: str
    style: str
    location: str


@dataclass(frozen=True)
class DialogueLine:
    speaker: str
    text: str


async def run_dialogue(
    *,
    a: NpcPersona,
    b: NpcPersona,
    topic: str,
    turns: int = 2,
) -> list[DialogueLine]:
    """两个 NPC 轮流说话，返回完整对话。turns = 每人说几轮。"""
    turns = max(1, min(turns, MAX_TURNS))
    llm = get_chat_model()
    history: list[DialogueLine] = []

    for i in range(turns * 2):
        speaker, listener = (a, b) if i % 2 == 0 else (b, a)

        system = build_npc_chat_prompt(
            name=speaker.name,
            title=speaker.title,
            personality=speaker.personality,
            expertise=speaker.expertise,
            style=speaker.style,
            location=speaker.location,
            other_name=listener.name,
        )
        #你们目前说了什么，该你说了
        turn_input = build_turn_input(
            topic=topic,
            history=[(h.speaker, h.text) for h in history],
        )

        response = await llm.ainvoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=turn_input),
            ]
        )
        text = str(response.content).strip()
        history.append(DialogueLine(speaker=speaker.name, text=text))
        log.info("npc_dialogue_line", speaker=speaker.name, chars=len(text))

    return history