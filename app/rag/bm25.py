"""BM25：关键词打分。

为什么要它（向量检索的短板）：
    问"张三的工号是多少"，向量检索可能召回一堆"关于张三"的段落，
    却没召回写着"工号：A1234"的那一段 —— 因为"工号"这个词在语义上
    和"张三"没关系，但字面上它才是关键。BM25 补的就是这一刀。

为什么自己写、不用 Postgres 全文检索：
    Postgres 的 tsvector 默认词典对中文不分词（"研发规范"会被当成一个整体），
    要装 zhparser 之类的扩展。这个项目只有几十个块，Python 里算完全够用，
    而且能单测。
"""

import math
import re
from collections import Counter
from itertools import pairwise

# 中文取字 + 相邻两字组合（中文没有空格，bigram 是最省事的分词近似）
_CJK = re.compile(r"[\u4e00-\u9fff]")
_WORD = re.compile(r"[a-zA-Z0-9_]+")


def tokenize(text: str) -> list[str]:
    """切成检索用的 token。

    中文："研发规范" → 研,发,规,范,研发,发规,规范
         单字保证召回，bigram 保证精度（两字组合更接近"词"）
    英文/数字：按词，转小写
    """
    chars = _CJK.findall(text or "")
    tokens: list[str] = list(chars)
    tokens.extend(a + b for a, b in pairwise(chars))
    tokens.extend(word.lower() for word in _WORD.findall(text or ""))
    return tokens


class BM25:
    """标准 BM25（k1=1.5, b=0.75 是通用默认值）。"""

    def __init__(self, docs: list[list[str]], *, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs = docs
        self.size = len(docs)
        self.avg_len = sum(len(d) for d in docs) / self.size if self.size else 0.0
        self.term_freqs = [Counter(d) for d in docs]

        # 文档频率：有多少篇文档包含这个词
        doc_freq: Counter = Counter()
        for tokens in docs:
            doc_freq.update(set(tokens))
        # +0.5 的平滑，避免"词表里没出现过"时除零或负值
        self.idf = {
            term: math.log(1 + (self.size - freq + 0.5) / (freq + 0.5))
            for term, freq in doc_freq.items()
        }

    def scores(self, query: list[str]) -> list[float]:
        """给每篇文档打一个分（长度和篇数一一对应）。"""
        results: list[float] = []
        for freqs in self.term_freqs:
            doc_len = sum(freqs.values())
            total = 0.0
            for term in query:
                freq = freqs.get(term)
                if not freq:
                    continue
                denominator = freq + self.k1 * (
                    1 - self.b + self.b * doc_len / (self.avg_len or 1.0)
                )
                total += self.idf.get(term, 0.0) * freq * (self.k1 + 1) / denominator
            results.append(total)
        return results