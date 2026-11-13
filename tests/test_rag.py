"""文档 RAG 的纯逻辑测试：切块 / BM25 / RRF。

都不碰数据库、不调模型 —— 这样改参数时可以秒级回归。
"""

from app.rag.bm25 import BM25, tokenize
from app.rag.chunking import chunk_text
from app.rag.fusion import rrf

# ==================== 切块 ====================


def test_chunk_text_splits_paragraphs():
    text = "\n\n".join(["段落一" * 10, "段落二" * 10, "段落三" * 10])
    chunks = chunk_text(text, max_chars=60)
    assert len(chunks) >= 2
    assert all(len(chunk) <= 60 for chunk in chunks)


def test_chunk_text_merges_short_paragraphs():
    """短段落应该被合并，而不是一段一块（否则块太碎，检索噪音大）。"""
    text = "短句一\n\n短句二\n\n短句三"
    chunks = chunk_text(text, max_chars=400)
    assert len(chunks) == 1


def test_chunk_text_hard_splits_long_paragraph():
    text = "啊" * 500
    chunks = chunk_text(text, max_chars=200, overlap=50)
    assert len(chunks) == 3
    assert all(len(chunk) <= 200 for chunk in chunks)


def test_chunk_text_overlap_keeps_context():
    """相邻块必须重叠，否则答案正好跨在切点上会丢。"""
    text = "甲" * 100 + "乙" * 100 + "丙" * 100
    chunks = chunk_text(text, max_chars=120, overlap=30)
    assert len(chunks) >= 2
    # 第二块的开头应该能在第一块的尾部找到（重叠）
    assert chunks[1][:10] in chunks[0]


def test_chunk_text_empty_returns_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


# ==================== BM25 ====================


def test_tokenize_chinese_bigrams():
    tokens = tokenize("研发规范")
    assert "研" in tokens       # 单字保证召回
    assert "研发" in tokens     # bigram 保证精度
    assert "规范" in tokens


def test_tokenize_latin_lowercased():
    assert "api" in tokenize("API")
    assert "2026" in tokenize("2026")


def test_bm25_ranks_matching_doc_first():
    docs = [
        tokenize("发布窗口是每周二和周四十点到十六点"),
        tokenize("今天食堂有红烧肉"),
        tokenize("工号由入职年份加四位序号组成"),
    ]
    scores = BM25(docs).scores(tokenize("发布窗口"))
    assert scores.index(max(scores)) == 0


def test_bm25_no_match_gives_zero():
    docs = [tokenize("苹果"), tokenize("香蕉")]
    assert BM25(docs).scores(tokenize("汽车")) == [0.0, 0.0]


def test_bm25_shorter_doc_wins_on_same_term():
    """同样的词，短文档得分更高（长度归一化的作用）。"""
    docs = [tokenize("发布窗口"), tokenize("发布窗口" + "补充说明" * 20)]
    scores = BM25(docs).scores(tokenize("发布窗口"))
    assert scores[0] > scores[1]


# ==================== RRF ====================


def test_rrf_prefers_document_in_both_lists():
    fused = rrf([[1, 2, 3], [3, 4, 5]])
    assert fused[0][0] == 3


def test_rrf_scores_descend():
    fused = rrf([[1, 2], [2, 1]])
    scores = [score for _, score in fused]
    assert scores == sorted(scores, reverse=True)


def test_rrf_keeps_every_candidate():
    fused = rrf([[1, 2], [3, 4]])
    assert {doc_id for doc_id, _ in fused} == {1, 2, 3, 4}


def test_rrf_empty_lists():
    assert rrf([[], []]) == []