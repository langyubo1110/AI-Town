"""
系统级接口：健康检查。
用来告诉外部（运维系统、负载均衡器、K8s 探针）"这个服务现在活得好不好、依赖的组件是否正常"。它是系统级接口——不属于任何业务，专门服务于部署和运维。
"""

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text

from app.core.config import get_settings

#创建路由
#在 FastAPI 自动生成的 Swagger 文档里，这个接口会归到 "system" 分组下
router = APIRouter(tags=["system"])


@router.get("/health", summary="健康检查（含依赖）")
async def health(request: Request, response: Response) -> dict:
    '''
    访问当前请求对象。这里用来拿到 request.app.state（应用级共享状态）
    app.state 是 FastAPI 提供的应用级共享存储
    直接操作响应对象（比如动态改状态码）。注意它和"返回值"是不同的东西
    '''
    #读取字典
    settings = get_settings()
    #初始化检查的容器
    checks: dict[str, str] = {}
    #任何一项有问题就为false
    ok = True

    # ① Postgres：执行最简单的查询探活
    try:
        engine = request.app.state.engine
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {type(exc).__name__}"
        ok = False

    # ② Redis：PING
    try:
        redis = request.app.state.redis
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {type(exc).__name__}"
        ok = False

    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if ok else "degraded",
        "app": settings.app_name,
        "version": settings.app_version,
        "env": settings.env,
        "checks": checks,
    }
