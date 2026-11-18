from core.retrieval import HybridRetriever


def test_hybrid_retriever_finds_same_formula_question():
    docs = [
        {"id":"p1:q1","question_text":"A body of mass 2 kg moves at 5 m/s. Calculate momentum.","options":{"A":"10"},"subject":"Physics","analysis":{"core_concept":"linear momentum p = mv"}},
        {"id":"p1:q2","question_text":"Which plant hormone promotes cell elongation?","options":{},"subject":"Biology","analysis":{"core_concept":"plant growth regulators"}},
    ]
    retriever = HybridRetriever(docs, enable_embeddings=False)
    query = {"question_text":"Find the linear momentum of a 3 kg object moving at 4 m/s.","subject":"Physics","analysis":{"core_concept":"momentum equals mass times velocity"}}
    ranked = retriever.rank(query, top_k=2, subject_filter="Physics")
    assert ranked[0][0]["id"] == "p1:q1"