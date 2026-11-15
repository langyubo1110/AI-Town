"""
FastAPI 依赖注入
用来给每个 HTTP 请求提供一个数据库会话（Session），并在请求结束后自动关闭它。
每个请求进来 → 开一个数据库 session → 处理业务 → 请求结束 → 自动关闭 session
"""

from collections.abc import AsyncIterator

from fastapi import HTTPException, Query, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import COOKIE_NAME, verify_player

log = get_logger(__name__)


def _player_from_cookie(request: Request) -> int | None:
    """从 Cookie 里取已签名的玩家身份；没有或签名不对都返回 None。"""
    return verify_player(request.cookies.get(COOKIE_NAME))


def resolve_player_id(
    request: Request,
    player_id: int | None = Query(None, ge=1, description="兼容老前端的回退参数"),
) -> int:
    """确定"这次请求是谁"。

    优先级：**签名 Cookie > 显式 query 参数**。

    为什么还要留 query 回退：
        前端是在页面加载后才知道自己的身份，中间存在"还没拿到 Cookie"的窗口；
        而且老链接（比如分享出去的 ?player_id=1）不应该直接 404。
        回退时会打一条 `identity_unsigned` 日志 —— 线上如果一直看到它，
        说明有调用方没走 /api/session，这是要修的。

    只有一种情况直接拒绝：**Cookie 存在但签名不对**（伪造/被改），
    这时候绝不能悄悄回退到 query，否则签名就白做了。
    """
    raw = request.cookies.get(COOKIE_NAME)
    if raw is not None:
        pid = verify_player(raw)
        if pid is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="身份令牌无效，请重新进入",
            )
        return pid

    if player_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少身份：先调用 POST /api/session 建立会话",
        )

    log.info("identity_unsigned", path=request.url.path, player_id=player_id)
    return player_id

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