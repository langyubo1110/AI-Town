"""
装配层，把各层的零件组装起来
"""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, npc,chat,event,town,ws
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.infra.cache import build_redis
from app.infra.llm import get_chat_model
from app.infra.db import build_engine, build_session_factory
from app.infra.tracing import flush as flush_tracing

settings = get_settings()
setup_logging("DEBUG" if settings.debug else "INFO", json_output=not settings.debug)
log = get_logger(__name__)


# Python 的上下文管理器协议
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动前、关闭后各跑一段。"""
    log.info(
        "app_starting",
        app=settings.app_name,
        version=settings.app_version,
        env=settings.env,
    )
    # 启动时校验 LLM 配置，配置错了立刻起不来，而不是等第一个请求
    get_chat_model()
    log.info("llm_ready", model=settings.llm_model)
    # ===== yield 之前：创建资源 =====
    app.state.engine = build_engine(
        settings.postgres_dsn,
        echo=settings.db_echo,
        pool_size=settings.db_pool_size,
    )
    app.state.session_factory = build_session_factory(app.state.engine)
    app.state.redis = build_redis(settings.redis_url)
    log.info("resources_ready")

    print(f"📚 API 文档: http://127.0.0.1:{settings.port}/docs")
    yield
    # ===== yield 之后：按【相反顺序】释放 =====
    flush_tracing()   # 把 Langfuse 缓冲里的 trace 推上去（没配 key 时是 no-op）
    await app.state.redis.aclose()
    await app.state.engine.dispose()
    log.info("app_stopped")


app = FastAPI(
    # title/version/description 三个参数只影响 /docs 页面的显示，不影响运行
    title=settings.app_name,
    version=settings.app_version,
    description="多npc智能体小镇",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#挂载路由
app.include_router(health.router)
app.include_router(npc.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(event.router, prefix="/api")
app.include_router(town.router, prefix="/api")

# WebSocket：不加 /api 前缀，与前端 vite 代理里的 '/ws' 对应
app.include_router(ws.router)

# if __name__ == "__main__":
#     uvicorn.run(
#         "app.main:app",
#         # 监听所有网卡，局域网其他设备、Docker 容器、云服务器公网才能访问
#         # 自己本地测试使用127.0.0.1
#         host=settings.host,
#         # 监听端口
#         port=settings.port,
#         # 热重载
#         # 父进程（reloader）：只干一件事——监听文件变化
#         # ↓ fork
#         # 子进程（server）：真正
#         # import 你的代码、监听端口
#         reload=True,
#     )
