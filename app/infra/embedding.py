"""Embedding 客户端（OpenAI 兼容协议）。"""

from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from app.core.config import get_settings


#全局单例
@lru_cache
def get_embedding_model() -> OpenAIEmbeddings:
    """全局唯一的向量模型客户端。"""
    settings = get_settings()
    return OpenAIEmbeddings(
        model=settings.embed_model,
        api_key=settings.embed_api_key or settings.llm_api_key,
        base_url=settings.embed_base_url,
        timeout=30,
        max_retries=2,
        check_embedding_ctx_length=False
    )