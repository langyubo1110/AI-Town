"""
结构化日志：开发用彩色文本，生产用 JSON。
开发环境输出彩色易读的文本，生产环境输出机器可解析的 JSON
"""

import logging

import structlog


#传入 日志级别、输出json为false表示为开发环境
def setup_logging(level: str = "INFO", json_output: bool = False) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", level=numeric)

    #选择渲染器
    renderer = (
        #生产
        structlog.processors.JSONRenderer(ensure_ascii=False)
        if json_output
        #开发
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        #加工日志
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


#得到log实例对象
def get_logger(name: str = "aitown"):
    return structlog.get_logger(name)
