"""把长文档切成块。

为什么必须切：
    嵌入模型有输入长度上限，整篇塞进去会被截断；而且检索粒度太粗——
    问"发布流程"却召回整篇研发规范，答案里 80% 是无关内容。

为什么按段落切，而不是按固定字数切：
    段落是作者自己划的语义边界。按字数切会把一句话拦腰斩断，
    向量化出来的东西两个半句都不完整。
"""

import re

# 默认块大小：400 字。约等于一个小节，够回答问题，又不至于太散。
DEFAULT_MAX_CHARS = 400
# 相邻块重叠 60 字：防止"答案正好跨在切点上"被切丢
DEFAULT_OVERLAP = 60


def chunk_text(
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """把文本切成若干块。

    规则：
        1. 先按空行拆成段落
        2. 段落累加到不超过 max_chars 为止
        3. 单段本身就超长（比如一整段没换行），才按字数硬切，并保留 overlap
    """
    raw = (text or "").strip()
    if not raw:
        return []

    paragraphs = [chunk.strip() for chunk in re.split(r"\n\s*\n", raw) if chunk.strip()]

    chunks: list[str] = []
    buffer = ""
    for para in paragraphs:
        if len(para) > max_chars:
            # 先把攒着的收尾，避免长段和前面的内容混在一块
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.extend(_split_long(para, max_chars=max_chars, overlap=overlap))
            continue

        if not buffer:
            buffer = para
        elif len(buffer) + 1 + len(para) <= max_chars:
            buffer = f"{buffer}\n{para}"
        else:
            chunks.append(buffer)
            buffer = para

    if buffer:
        chunks.append(buffer)

    return chunks


def _split_long(text: str, *, max_chars: int, overlap: int) -> list[str]:
    """超长段落的硬切，带重叠。"""
    overlap = max(0, min(overlap, max_chars - 1))
    step = max(1, max_chars - overlap)

    pieces: list[str] = []
    for start in range(0, len(text), step):
        piece = text[start : start + max_chars].strip()
        if piece:
            pieces.append(piece)
        if start + max_chars >= len(text):
            break
    return pieces