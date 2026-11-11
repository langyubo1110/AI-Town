"""worker 入口：python -m app.worker"""

import asyncio
import contextlib
import logging

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.infra.cache import build_redis
from app.infra.db import build_engine, build_session_factory
from app.worker.consumer import BLOCK_MS, run
from app.worker.ticker import run_ticker


async def main() -> None:
    settings = get_settings()
    setup_logging("DEBUG" if settings.debug else "INFO", json_output=not settings.debug)

    # 第三方库降噪：只给自己项目开 DEBUG
    for noisy in ("httpx", "httpcore", "openai", "sqlalchemy.engine", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    log = get_logger(__name__)

    engine = build_engine(settings.postgres_dsn, echo=False, pool_size=2)
    factory = build_session_factory(engine)
    redis = build_redis(settings.redis_url, socket_timeout=BLOCK_MS / 1000 + 5)

    log.info("worker_booting")

    # ticker 和消费循环并行跑在同一个进程里
    ticker = asyncio.create_task(run_ticker(redis, factory), name="npc-ticker")

    try:
        await run(redis, factory)
    finally:
        ticker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await ticker
        await redis.aclose()
        await engine.dispose()
        log.info("worker_stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nworker 已停止")