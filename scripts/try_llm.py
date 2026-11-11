"""验证 LLM 通路（不涉及 HTTP、不涉及数据库）。"""

import asyncio

from langchain_openai import ChatOpenAI

from app.core.config import get_settings


async def main() -> None:
    settings = get_settings()
    print("model =", settings.llm_model)
    print("base  =", settings.llm_base_url)

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=30,
    )

    message = await llm.ainvoke("用一句话介绍你自己")
    print("\nreply =", message.content)
    print("usage =", message.usage_metadata)


if __name__ == "__main__":
    asyncio.run(main())