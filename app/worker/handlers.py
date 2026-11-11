"""各类后台任务的具体处理器。

分发在 consumer.handle() 里，业务实现集中在这里。
每新增一种事件类型：加一个 handle_xxx()，再在 consumer.handle 里注册一行。

★ 处理器【不直接广播】：它们返回 Broadcast 列表，
  由 _process 在数据库 commit 之后统一推送。
  这样不会出现"推送成功但事务回滚"的幽灵事件。
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import talk
from app.core.logging import get_logger
from app.repos import event_repo, npc_repo

log = get_logger(__name__)


@dataclass(frozen=True)
class Broadcast:
    """一条「提交之后要推出去」的事件。"""

    player_id: int
    event: dict


def _persona(npc) -> talk.NpcPersona:
    """ORM 实体 → 纯数据（和 state 一样的原则：业务函数不认 ORM）。"""
    return talk.NpcPersona(
        name=npc.name,
        title=npc.title,
        personality=npc.personality,
        expertise=npc.expertise,
        style=npc.style,
        location=npc.location,
    )


async def handle_npc_chat(
    session: AsyncSession,
    *,
    payload: dict,
    msg_id: str,
) -> list[Broadcast]:
    """让两个 NPC 聊一会儿，写一条事件，并返回待广播的内容。"""
    npc_a_name = payload.get("npc_a", "")
    npc_b_name = payload.get("npc_b", "")
    topic = payload.get("topic", "")
    turns = int(payload.get("turns", 2))
    player_id = int(payload["player_id"])

    npc_a = await npc_repo.get_by_name(session, npc_a_name)
    npc_b = await npc_repo.get_by_name(session, npc_b_name)
    if npc_a is None or npc_b is None:
        # 数据错误 → 重试也没用 → 记一笔就返回（消息会被 ACK）
        log.warning(
            "npc_chat_skipped",
            reason="npc_not_found",
            npc_a=npc_a_name,
            npc_b=npc_b_name,
            msg_id=msg_id,
        )
        return []

    lines = await talk.run_dialogue(
        a=_persona(npc_a),
        b=_persona(npc_b),
        topic=topic,
        turns=turns,
    )

    summary = f"{npc_a.name}和{npc_b.name}聊了聊「{topic or '最近的琐事'}」"
    event_payload = {
        "npc_a": npc_a.name,
        "npc_b": npc_b.name,
        "topic": topic,
        "lines": [{"speaker": line.speaker, "text": line.text} for line in lines],
        "msg_id": msg_id,
        "trigger": payload.get("trigger", "manual"),
    }

    created = await event_repo.create(
        session,
        player_id=player_id,
        npc_id=npc_a.id,
        event_type="npc_dialogue",
        summary=summary,
        payload=event_payload,
    )
    # flush 才会真的 INSERT（拿到自增 id），但事务还没提交
    await session.flush()

    log.info(
        "npc_dialogue_done",
        npc_a=npc_a.name,
        npc_b=npc_b.name,
        lines=len(lines),
        event_id=created.id,
    )

    return [
        Broadcast(
            player_id=player_id,
            event={
                "id": created.id,
                "event_type": created.event_type,
                "npc_id": created.npc_id,
                "summary": created.summary,
                "payload": created.payload,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
    ]