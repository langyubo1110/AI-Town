"""初始化种子数据：3 个 NPC。

幂等：重复执行不会插入重复数据。
"""

import asyncio
from sqlalchemy import select
from app.core.config import get_settings
from app.infra.db import build_engine, build_session_factory
from app.models import NPC


#种子数据（Seed Data）：系统运行前预先准备好的基础数据。
#幂等：同一个操作执行一次和执行多次，结果一样。这里指重复运行脚本不会产生重复的 NPC 记录。
SEED_NPCS = [
    {
        "name": "张三",
        "title": "Python工程师",
        "personality": "技术宅，喜欢讨论算法和框架",
        "expertise": "多智能体系统、Python开发、代码优化",
        "style": "简洁专业，喜欢用技术术语，偶尔吐槽bug",
        "location": "工位区",
    },
    {
        "name": "李四",
        "title": "产品经理",
        "personality": "外向健谈，善于沟通协调",
        "expertise": "需求分析、产品规划、用户体验",
        "style": "友好热情，善于引导对话，喜欢用比喻",
        "location": "会议室",
    },
    {
        "name": "王五",
        "title": "UI设计师",
        "personality": "细腻敏感，注重美感",
        "expertise": "界面设计、交互设计、视觉呈现",
        "style": "优雅简洁，喜欢用艺术化的表达",
        "location": "休息区",
    },
]


async def main() -> None:
    '''
    读取配置，创建数据库引擎和会话工厂（连接池）。
    '''
    settings = get_settings()
    engine = build_engine(settings.postgres_dsn)
    factory = build_session_factory(engine)

    async with factory() as session:
        for item in SEED_NPCS:
            exists = await session.scalar(select(NPC).where(NPC.name == item["name"]))
            if exists:
                print(f"跳过（已存在）: {item['name']}")
                continue
            session.add(NPC(**item))
            print(f"插入: {item['name']}")
        await session.commit()

    #关闭连接池，释放资源。
    await engine.dispose()
    print("种子数据完成")


if __name__ == "__main__":
    asyncio.run(main())