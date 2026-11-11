"""图的运行时依赖：从 config["configurable"] 取连接对象。"""

from typing import Any

from langchain_core.runnables import RunnableConfig
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession


class MissingRuntimeError(RuntimeError):
    """调用图时忘了注入运行时依赖。"""

#RunnableConfig "运行时配置容器"
def _configurable(config: RunnableConfig | None) -> dict[str, Any]:
    if not config or "configurable" not in config:
        raise MissingRuntimeError(
            "调用图时必须传 config={'configurable': {'session': ..., 'redis': ...}}"
        )
    return config["configurable"]


def get_session(config: RunnableConfig | None) -> AsyncSession:
    session = _configurable(config).get("session")
    if session is None:
        raise MissingRuntimeError("config['configurable'] 里缺少 session")
    return session


def get_redis(config: RunnableConfig | None) -> Redis:
    redis = _configurable(config).get("redis")
    if redis is None:
        raise MissingRuntimeError("config['configurable'] 里缺少 redis")
    return redis

def get_thread_id(config: RunnableConfig | None) -> str:
    thread_id = _configurable(config).get("thread_id")
    if not thread_id:
        raise MissingRuntimeError(
            "config['configurable'] 里缺少 thread_id（checkpointer 需要它定位会话）"
        )
    return thread_id

'''
路由和脚本都调它，config 的形状只有一处定义。
以后加 callbacks、metadata（Langfuse 用），只改这一个函数。
'''
def build_config(
    *,
    session: AsyncSession,
    redis: Redis,
    thread_id: str,
    user_id: str | None = None,
) -> dict:
    """统一构造图调用的 config，避免每处手写字典漏字段。

    - configurable：运行时依赖（session / redis / thread_id）
    - metadata：Langfuse 用它把 trace 归到 session / user 下
    - callbacks：没配 Langfuse 时为空，等于零开销
    """
    from app.infra.tracing import get_callbacks, tracing_metadata

    config: dict = {
        "configurable": {
            "session": session,
            "redis": redis,
            "thread_id": thread_id,
        },
        "metadata": tracing_metadata(thread_id=thread_id, user_id=user_id),
    }

    callbacks = get_callbacks()
    if callbacks:
        config["callbacks"] = list(callbacks)

    return config