"""
Embedding Service — Lightweight TF-IDF based
Replaced sentence-transformers (~350MB PyTorch) with scikit-learn TF-IDF (~5MB)
to fit within Render free tier 512MB RAM limit.

Trade-off: TF-IDF is keyword-based (not semantic), but works well for clustering
exam questions from the same subject/paper where vocabulary overlap is high.
"""

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity as sklearn_cosine
import numpy as np
from typing import List


class EmbeddingService:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            max_features=384,
            stop_words='english',
            ngram_range=(1, 2),       # unigrams + bigrams
            sublinear_tf=True,        # log-scaled TF for better weighting
            min_df=1,                 # no minimum doc frequency (small datasets)
            max_df=0.95,              # ignore very common terms
        )
        self._fitted = False
        print("  Loaded: TF-IDF vectorizer (384-dim, ngram 1-2)")

    def _ensure_fitted(self, texts: List[str]):
        """Fit vectorizer on first batch, then reuse."""
        if not self._fitted and texts:
            self.vectorizer.fit(texts)
            self._fitted = True

    def embed(self, text: str) -> List[float]:
        vec = self._transform([text])
        return vec[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        return self._transform(texts)

    def _transform(self, texts: List[str]) -> List[List[float]]:
        """Transform texts to L2-normalized dense vectors."""
        self._ensure_fitted(texts)
        vecs = self.vectorizer.transform(texts).toarray()

        # L2 normalize so cosine similarity = dot product
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1
        vecs = vecs / norms

        return vecs.tolist()

    def cosine_similarity(self, a: List[float], b: List[float]) -> float:
        return float(np.dot(a, b))

    def find_similar(self, query_vec: List[float], candidates: List[List[float]],
                     threshold: float = 0.82) -> List[int]:
        scores = [self.cosine_similarity(query_vec, c) for c in candidates]
        return [i for i, s in enumerate(scores) if s >= threshold]
