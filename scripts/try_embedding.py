"""验证 embedding 通路，并检查语义相似度是否符合直觉。"""

import asyncio
import math

from app.core.config import get_settings
from app.infra.embedding import get_embedding_model


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb)


async def main() -> None:
    settings = get_settings()
    print("embed model =", settings.embed_model)
    print("base        =", settings.embed_base_url)

    embedder = get_embedding_model()

    # ① 维度检查
    vec = await embedder.aembed_query("我在调试多智能体系统")
    print("\n维度 =", len(vec))
    print("前 5 维 =", [round(v, 4) for v in vec[:5]])

    # ② 语义相似度检查（这才是真正的验证）
    print("\n--- 语义相似度 ---")
    sentences = {
        "A_同义1": "我喜欢用 Python 写代码",
        "A_同义2": "Python 是我最常用的编程语言",
        "B_无关": "今天天气真好，适合出去散步",
    }

    vectors = {}
    for key, text in sentences.items():
        vectors[key] = await embedder.aembed_query(text)

    print(f"A1 vs A2（同义）: {cosine(vectors['A_同义1'], vectors['A_同义2']):.4f}")
    print(f"A1 vs B （无关）: {cosine(vectors['A_同义1'], vectors['B_无关']):.4f}")


if __name__ == "__main__":
    asyncio.run(main())