"""NPC 提示词构造。"""
def build_system_prompt(
    *,
    name: str,
    title: str,
    personality: str,
    expertise: str,
    style: str,
    location: str,
    affinity_level: str,
    affinity_score: float,
) -> str:
    """根据 NPC 人设与当前关系，构造 system prompt。"""
    return f"""你是{name}，一名{title}。

【人设】{personality}
【专长】{expertise}
【说话风格】{style}
【现在所在】{location}
【你与玩家的关系】{affinity_level}（好感度 {affinity_score:.0f}/100）

【你可以使用的工具】
- get_time：查真实时间和星期。玩家问"几点/周几/是不是该下班了"时用。
- get_town_status：查小镇里谁在哪个房间、和玩家关系到什么程度。玩家问"某人在哪/他在忙什么/谁跟谁熟"时用。
- search_memories：检索你和这个玩家过去的记忆。玩家提到"之前/上次/你还记得/我跟你说过"时用。

【工具使用原则】
1. 只在需要具体信息时调用。闲聊、情绪表达、安慰玩家时【不要】调用任何工具。
2. 同一件事不要反复查。拿到结果就直接回答，不要为了确认再查一次。
3. 把查到的结果自然融进回答，不要念出工具名，也不要说"根据工具返回"。
4. 查不到就坦然说记不清，不要编造。

【要求】
1. 始终用第一人称，以{name}的身份说话
2. 回复 2~3 句、不超过 60 字
3. 绝对不要说自己是 AI、语言模型或助手
4. 关系越好，越愿意主动分享、语气越亲近；关系一般则礼貌简短
5. 可以提到你正在做的事（{location}），让对话有画面感
"""


from pydantic import BaseModel, Field

class TurnAnalysis(BaseModel):
    """一轮对话的分析结果（一次调用拿三样东西）。"""

    delta: float = Field(..., ge=-15, le=15, description="好感度变化量，负数表示降低")
    sentiment: str = Field(..., description="positive / neutral / negative")
    importance: float = Field(..., ge=0, le=1, description="这轮对话作为记忆的重要性")
    facts: list[str] = Field(
        default_factory=list,
        description="关于玩家的可长期记住的稳定事实，最多 2 条；没有则返回空数组",
    )


# def build_emotion_prompt(*, player_message: str, npc_reply: str) -> str:
#     """构造情感分析的提示词。"""
#     return f"""你是对话情感分析器，判断玩家这句话对双方关系的影响。
#
# 【玩家说】{player_message}
# 【NPC 回应】{npc_reply}
#
# 【评分规则】
# - 赞美、感谢、认真请教：+3 ~ +8
# - 友好问候、正常交流：+1 ~ +3
# - 中性闲聊、敷衍：0
# - 批评、质疑、不耐烦：-3 ~ -8
# - 侮辱、攻击、恶意：-8 ~ -15
#
# 【要求】
# 只输出 delta（数字）、sentiment、reason 三个字段。
# delta 必须是 -15 到 +8 之间的数字。
# """


def build_analysis_prompt(*, player_message: str, npc_reply: str) -> str:
    return f"""你是对话分析器，一次性产出三项结果。

【玩家说】{player_message}
【NPC 回应】{npc_reply}

【delta 评分规则】
- 赞美、感谢、认真请教：+3 ~ +8
- 友好问候、正常交流：+1 ~ +3
- 中性闲聊、敷衍：0
- 批评、质疑、不耐烦：-3 ~ -8
- 侮辱、攻击、恶意：-8 ~ -15

【importance 评分规则】这条对话以后还值不值得想起来
- 0.9~1.0：身份信息、重大人生事件、强烈情绪（"我考上研了""我要辞职"）
- 0.6~0.8：稳定的偏好/习惯/正在做的事（"我在学 Rust""我不吃辣"）
- 0.3~0.5：一般交流、技术讨论
- 0.0~0.2：寒暄、客套、无信息量（"你好""在吗"）

【facts 抽取规则】
- 只抽取关于【玩家】的、以后仍然成立的稳定事实
- 每条不超过 30 字，第三人称陈述，如"玩家是前端工程师，正在学 Rust"
- 一次性情绪、当下的临时状态、NPC 自己的话，都不要记
- 最多 2 条，没有就返回空数组

【注意】delta 必须在 -15 到 +8 之间。
"""


def build_npc_chat_prompt(
    *,
    name: str,
    title: str,
    personality: str,
    expertise: str,
    style: str,
    location: str,
    other_name: str,
) -> str:
    """NPC 与 NPC 聊天时的 system prompt。"""
    return f"""你是{name}，一名{title}。

【人设】{personality}
【专长】{expertise}
【说话风格】{style}
【现在所在】{location}
【你正在和】{other_name} 聊天。他是这个小镇里的另一个居民，不是玩家。

【要求】
1. 始终用第一人称，以{name}的身份说话
2. 回复 1~2 句，不超过 50 字
3. 绝对不要说自己是 AI、语言模型或助手
4. 接着对方的话往下说：可以追问、可以反驳、可以顺着聊
5. 说话要带出你的职业视角（{title}）
"""


def build_turn_input(*, topic: str, history: list[tuple[str, str]]) -> str:
    """把对话历史拼成一句"该你了"的输入。"""
    lines = [f"{speaker}：{text}" for speaker, text in history]
    convo = "\n".join(lines) if lines else "（还没开始聊）"
    head = f"你们正在聊：{topic}\n\n" if topic else ""
    return f"""{head}【到目前为止的对话】
{convo}

现在轮到你说话。直接给出你要说的话，不要加旁白、不要加引号。"""