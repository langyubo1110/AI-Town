"""Postgres 异步引擎与会话工厂。
"""

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

'''
这个文件是数据库访问层的"工厂"——负责创建 SQLAlchemy 的异步引擎（带连接池）和会话工厂
'''

#创建引擎
def build_engine(dsn: str, *, echo: bool = False, pool_size: int = 5) -> AsyncEngine:
    """创建异步引擎（内部自带连接池）。"""
    return create_async_engine(
        dsn,
        echo=echo,
        pool_size=pool_size,  # 常驻连接数
        max_overflow=10,  # 高峰期可临时超出几个
        pool_pre_ping=True,  # ★ 取连接前先探活，避免拿到已被数据库断开的死连接
        pool_recycle=1800,  # 30 分钟回收一次，防止被服务端超时踢掉
    )

#基于引擎创建会话工厂
def build_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)
