"""事件的类型常量与构造函数（纯函数）。"""

AFFINITY_LEVEL_UP = "affinity_level_up"

LEVEL_UP_SUMMARY = "你和{npc_name}的关系从「{old}」变成了「{new}」"

#产出人看的日志
def level_up_summary(*, npc_name: str, old_level: str, new_level: str) -> str:
    return LEVEL_UP_SUMMARY.format(npc_name=npc_name, old=old_level, new=new_level)


#产出机器看的JSONB数据
def level_up_payload(*, old_level: str, new_level: str, score: float) -> dict:
    return {
        "old_level": old_level,
        "new_level": new_level,
        "score": round(float(score), 2),
    }