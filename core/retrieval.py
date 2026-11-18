from __future__ import annotations

import hashlib
import re
from pathlib import Path
from difflib import SequenceMatcher
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from core.config import CACHE_DIR


def _plain(text: str) -> str:
    text = (text or "").lower()
    text = text.replace("\\times", " ").replace("\\rightarrow", " to ").replace("\\frac", " fraction ")
    text = re.sub(r"[^a-z0-9μΩαβγΔλπ√.+-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def question_search_text(q: dict[str, Any]) -> str:
    a = q.get("analysis") or {}
    parts = [
        q.get("question_text", ""),
        " ".join(f"{k}: {v}" for k, v in (q.get("options") or {}).items()),
        str(a.get("subject", q.get("subject", ""))),
        str(a.get("chapter", "")),
        str(a.get("topic", "")),
        str(a.get("subtopic", "")),
        str(a.get("core_concept", "")),
        " ".join(a.get("concept_tags", []) or []),
        " ".join(a.get("formulae_or_laws", []) or []),
        " ".join(a.get("reactions_or_mechanisms", []) or []),
        str(a.get("short_search_text", "")),
    ]
    return "\n".join(x for x in parts if x and x != "None")


class HybridRetriever:
    """Hybrid semantic + lexical retrieval. LLM comparison is the final adjudicator."""

    def __init__(self, documents: list[dict[str, Any]], embedding_model_name: str = "BAAI/bge-small-en-v1.5", enable_embeddings: bool = True):
        if not documents:
            raise ValueError("Question bank is empty; ingest mock papers first.")
        self.documents = documents
        self.texts = [question_search_text(q) for q in documents]
        self.subjects = [q.get("subject") or (q.get("analysis") or {}).get("subject") for q in documents]
        self.word_vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=180000, sublinear_tf=True, strip_accents="unicode")
        self.char_vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, max_features=220000, sublinear_tf=True)
        self.word_matrix = self.word_vectorizer.fit_transform(self.texts)
        self.char_matrix = self.char_vectorizer.fit_transform([_plain(t) for t in self.texts])
        self.embedding_model = None
        self.document_embeddings = None
        self.embedding_status = "Disabled"
        if enable_embeddings:
            try:
                from sentence_transformers import SentenceTransformer
                corpus_hash = hashlib.sha256((embedding_model_name + "\n" + "\n".join(self.texts)).encode("utf-8")).hexdigest()[:20]
                cache_file = CACHE_DIR / f"bge_embeddings_{corpus_hash}.npz"
                if cache_file.exists():
                    self.document_embeddings = np.load(cache_file)["embeddings"].astype(np.float32)
                    self.embedding_status = f"Local embeddings loaded from cache: {embedding_model_name}"
                else:
                    self.embedding_model = SentenceTransformer(embedding_model_name, device="cpu")
                    self.document_embeddings = self.embedding_model.encode(
                        self.texts, batch_size=32, show_progress_bar=False,
                        normalize_embeddings=True, convert_to_numpy=True
                    ).astype(np.float32)
                    np.savez_compressed(cache_file, embeddings=self.document_embeddings)
                    self.embedding_status = f"Local embeddings computed and cached: {embedding_model_name}"
                # Retain the model only for query embeddings. It is not needed when loaded from cache until a query arrives.
                if self.embedding_model is None:
                    self.embedding_model = SentenceTransformer(embedding_model_name, device="cpu")
            except Exception as exc:
                self.embedding_status = f"Local embedding model unavailable; lexical retrieval active ({type(exc).__name__})."

    def rank(self, query_question: dict[str, Any], top_k: int = 30, subject_filter: str | None = None) -> list[tuple[dict[str, Any], float]]:
        query = question_search_text(query_question)
        q_word = self.word_vectorizer.transform([query])
        q_char = self.char_vectorizer.transform([_plain(query)])
        word_scores = cosine_similarity(q_word, self.word_matrix).ravel()
        char_scores = cosine_similarity(q_char, self.char_matrix).ravel()
        if self.embedding_model is not None and self.document_embeddings is not None:
            q_embedding = self.embedding_model.encode([query], normalize_embeddings=True, convert_to_numpy=True)[0]
            dense_scores = np.dot(self.document_embeddings, q_embedding)
            dense_scores = np.clip((dense_scores + 1.0) / 2.0, 0, 1)
            rough_scores = 0.60 * dense_scores + 0.26 * word_scores + 0.14 * char_scores
        else:
            rough_scores = 0.67 * word_scores + 0.33 * char_scores
        if subject_filter:
            mask = np.array([s == subject_filter for s in self.subjects], dtype=bool)
            if mask.any():
                rough_scores = rough_scores.copy()
                rough_scores[~mask] = -1.0
        # Fuzzy string comparison is expensive across every pair. Run it only on the
        # leading lexical/semantic shortlist; the BGE + word/character scores rank the full bank.
        rough_count = min(200, len(self.documents))
        rough_indices = np.argpartition(rough_scores, -rough_count)[-rough_count:]
        exact_scores = np.zeros(len(self.documents), dtype=np.float32)
        norm_q = _plain(query)
        for i in rough_indices:
            exact_scores[int(i)] = SequenceMatcher(None, norm_q, _plain(self.texts[int(i)])).ratio()
        combined = 0.95 * rough_scores + 0.05 * exact_scores
        count = min(top_k, len(self.documents))
        indices = np.argpartition(combined, -count)[-count:]
        indices = indices[np.argsort(combined[indices])[::-1]]
        return [(self.documents[int(i)], float(combined[int(i)])) for i in indices]