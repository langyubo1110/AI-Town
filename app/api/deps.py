"""
FastAPI 依赖注入
用来给每个 HTTP 请求提供一个数据库会话（Session），并在请求结束后自动关闭它。
每个请求进来 → 开一个数据库 session → 处理业务 → 请求结束 → 自动关闭 session
"""

from collections.abc import AsyncIterator
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """每个请求一个 session，请求结束自动关闭。"""
    # 从应用全局状态取会话工厂
    factory = request.app.state.session_factory
    async with factory() as session:
        '''
        如果用 return session，函数结束后 session 不会自动关闭。
        用 yield 才能让 async with 的清理逻辑在请求结束后执行。
        这是 FastAPI 依赖的"带清理逻辑"的标准写法。
        '''
        yield session


def get_redis(request: Request) -> Redis:
    """拿到 lifespan 里创建的 Redis 客户端。"""
    return request.app.state.redis