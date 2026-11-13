"""把 docs/kb/*.md 切块、向量化、写进 document_chunks。

幂等：每次都按 source 删掉旧块再插入，重复跑不会产生重复数据。

用法：
    python -m scripts.ingest_docs
"""

import asyncio
from pathlib import Path

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infra.db import build_engine, build_session_factory
from app.infra.embedding import get_embedding_model
from app.models import DocumentChunk
from app.rag.chunking import chunk_text

log = get_logger(__name__)

# 知识库目录：项目根 / docs / kb
KB_DIR = Path(__file__).resolve().parents[1] / "docs" / "kb"

# 一次 embed 多少块。批太大容易超模型单次输入上限，太小则请求次数多
BATCH = 10


async def main() -> None:
    if not KB_DIR.exists():
        print(f"知识库目录不存在：{KB_DIR}")
        return

    files = sorted(
        path for path in KB_DIR.iterdir() if path.suffix.lower() in {".md", ".txt"}
    )
    if not files:
        print(f"知识库里没有 .md / .txt 文件：{KB_DIR}")
        return

    settings = get_settings()
    engine = build_engine(settings.postgres_dsn)
    factory = build_session_factory(engine)
    embed = get_embedding_model()

    try:
        async with factory() as session:
            for path in files:
                text = path.read_text(encoding="utf-8")
                chunks = chunk_text(text)
                if not chunks:
                    print(f"跳过（内容为空）: {path.name}")
                    continue

                # 先删旧块：保证重复执行的结果一样（幂等）
                await session.execute(
                    delete(DocumentChunk).where(DocumentChunk.source == path.name)
                )

                for start in range(0, len(chunks), BATCH):
                    batch = chunks[start : start + BATCH]
                    vectors = await embed.aembed_documents(batch)
                    for offset, (content, vector) in enumerate(
                        zip(batch, vectors, strict=True)
                    ):
                        session.add(
                            DocumentChunk(
                                source=path.name,
                                chunk_index=start + offset,
                                title=path.stem,
                                content=content,
                                embedding=vector,
                            )
                        )

                print(f"已入库: {path.name}（{len(chunks)} 块）")

            await session.commit()

            total = await session.scalar(select(DocumentChunk.id).limit(1))
            print("完成" if total else "警告：库里没有文档块")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())