"""Langfuse 链路追踪（可选）。

没有配置 key 时**全链路 no-op**：项目照常运行，只在启动日志里说明一次。
启用方式：在 `.env` 里填

    LANGFUSE_PUBLIC_KEY=pk-lf-...
    LANGFUSE_SECRET_KEY=sk-lf-...
    LANGFUSE_HOST=https://cloud.langfuse.com      # 自托管改成 http://localhost:3000

langfuse SDK 从环境变量读凭证，所以这里把 `.env` 里的值灌进 os.environ
（用 setdefault：不覆盖 shell 里已经存在的值）。
"""

import os
from functools import lru_cache

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


def _apply_env() -> bool:
    settings = get_settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return False

    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
    os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
    os.environ.setdefault("LANGFUSE_BASEURL", settings.langfuse_host)
    return True


@lru_cache
def get_callbacks() -> tuple:
    """返回 LangChain 回调列表；未配置或 SDK 不可用时返回空元组。

    只构造一次：Langfuse 的 handler 内部持有客户端和后台线程，
    每次请求新建会泄漏线程。
    """
    if not _apply_env():
        log.info(
            "tracing_disabled",
            reason="缺少 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY",
        )
        return ()

    try:
        from langfuse.langchain import CallbackHandler

        handler = CallbackHandler()
    except Exception as exc:
        log.warning(
            "tracing_unavailable",
            error=type(exc).__name__,
            detail=str(exc)[:200],
        )
        return ()

    log.info("tracing_enabled", host=get_settings().langfuse_host)
    return (handler,)


def tracing_metadata(*, thread_id: str, user_id: str | None = None) -> dict:
    """Langfuse 靠这几个 key 把 trace 归到 session / user 下。"""
    metadata: dict = {
        "langfuse_session_id": thread_id,
        "langfuse_tags": ["ai-town"],
    }
    if user_id:
        metadata["langfuse_user_id"] = user_id
    return metadata


def flush() -> None:
    """进程退出前把缓冲中的 trace 推上去（否则最后几条会丢）。"""
    if not get_callbacks():
        return
    try:
        from langfuse import get_client

        get_client().flush()
        log.info("tracing_flushed")
    except Exception as exc:
        log.warning("tracing_flush_failed", error=type(exc).__name__)