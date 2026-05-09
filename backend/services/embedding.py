"""
Embedding Service
Converts question text → dense vectors using all-MiniLM-L6-v2
Free, runs locally, no API cost (~90MB model download on first run).
"""

from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List

MODEL_NAME = "all-MiniLM-L6-v2"


class EmbeddingService:
    def __init__(self):
        self.model = SentenceTransformer(MODEL_NAME)
        print(f"  Loaded: {MODEL_NAME}")

    def embed(self, text: str) -> List[float]:
        vec = self.model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        vecs = self.model.encode(texts, normalize_embeddings=True, batch_size=64, show_progress_bar=False)
        return vecs.tolist()

    def cosine_similarity(self, a: List[float], b: List[float]) -> float:
        return float(np.dot(a, b))

    def find_similar(self, query_vec: List[float], candidates: List[List[float]], threshold: float = 0.82) -> List[int]:
        scores = [self.cosine_similarity(query_vec, c) for c in candidates]
        return [i for i, s in enumerate(scores) if s >= threshold]
