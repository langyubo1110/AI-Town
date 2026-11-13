"""文档 RAG。

和 memory 的区别：
    memory 是"NPC 记得的事"，有归属（npc_id + player_id），检索时按人对齐。
    rag    是"小镇里公开的资料"，无归属，谁都能查，回答要给出处。

四个文件各管一件事：
    chunking  长文档 → 块（检索的最小单位）
    bm25      关键词打分（字面匹配，补向量检索的短板）
    fusion    RRF：把两路排名合成一路
    search    串起来：向量召回 + BM25 召回 + RRF → 带出处的 Hit
"""