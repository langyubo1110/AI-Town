from app.memory import ranking


def _c(id, rel, imp, age):
    return ranking.Candidate(id=id, content=f"m{id}", relevance=rel, importance=imp, age_hours=age)

def test_relevance_clipped():
    assert ranking.relevance_from_distance(1.4) == 0.0
    assert ranking.relevance_from_distance(-0.2) == 1.0

def test_recency_halves_at_half_life():
    assert ranking.recency_from_age(0) == 1.0
    assert abs(ranking.recency_from_age(138) - 0.5) < 1e-9

def test_old_but_relevant_beats_new_but_irrelevant():
    old_relevant = _c(1, rel=0.9, imp=0.8, age=1000)
    new_irrelevant = _c(2, rel=0.1, imp=0.1, age=0)
    assert ranking.rank([old_relevant, new_irrelevant], top_k=1)[0].id == 1

def test_top_k_truncates():
    cands = [_c(i, 0.5, 0.5, i) for i in range(10)]
    assert len(ranking.rank(cands, top_k=5)) == 5