"""LLM 客户端（OpenAI 兼容协议）。"""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.core.config import get_settings


#单列缓存
@lru_cache
def get_chat_model() -> ChatOpenAI:
    """全局唯一的对话模型客户端。"""
    settings = get_settings()
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout,
        max_retries=2,
        temperature=0.8,
    )