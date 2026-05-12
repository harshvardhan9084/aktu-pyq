"""
Clustering Service — groups similar questions using DBSCAN.
Works with TF-IDF vectors (lower threshold than neural embeddings).
"""

from datetime import datetime
import numpy as np
from sklearn.cluster import DBSCAN
from sklearn.metrics.pairwise import cosine_similarity
from typing import List
import logging

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.45   # TF-IDF cosine threshold (lower than neural 0.82)
MIN_CLUSTER_SIZE = 2


def cluster_questions(embeddings: List[List[float]], question_texts: List[str]) -> List[int]:
    if len(embeddings) < 2:
        return [-1] * len(embeddings)

    X = np.array(embeddings)
    eps = 1 - SIMILARITY_THRESHOLD

    # Fix: limit n_jobs to avoid resource exhaustion on shared hosting
    db = DBSCAN(eps=eps, min_samples=MIN_CLUSTER_SIZE, metric="cosine", n_jobs=2).fit(X)
    labels = db.labels_.tolist()
    n_clusters = len(set(l for l in labels if l != -1))
    logger.info(f"Clustering: {n_clusters} clusters, {labels.count(-1)} unique, from {len(embeddings)} inputs")
    return labels


def get_representative_question(cluster_questions: List[str], cluster_embeddings: List[List[float]]) -> str:
    if len(cluster_questions) == 1:
        return cluster_questions[0]
    X = np.array(cluster_embeddings)
    avg_sims = cosine_similarity(X).mean(axis=1)
    return cluster_questions[int(np.argmax(avg_sims))]


def detect_trend(year_appeared: List[int]) -> str:
    if not year_appeared or len(year_appeared) < 2:
        return "insufficient_data"
    years = sorted(year_appeared)
    recent = [y for y in years if y >= max(years) - 3]
    if len(recent) >= 3: return "rising"
    if len(recent) == 0: return "declining"
    if years[-1] - years[0] >= 5 and len(years) >= 4: return "consistent"
    return "intermittent"


def compute_importance_score(frequency: int, max_frequency: int, trend: str, last_appearance: int, current_year: int = None) -> float:
    # Fix: default to current year instead of hardcoded 2024
    if current_year is None:
        current_year = datetime.now().year
    freq_score = min(frequency / max(max_frequency, 1), 1.0)
    trend_weights = {"rising": 1.0, "consistent": 0.85, "intermittent": 0.6, "declining": 0.3, "insufficient_data": 0.5}
    trend_score = trend_weights.get(trend, 0.5)
    recency = max(0, 1 - (current_year - last_appearance) / 5)
    return round(0.5 * freq_score + 0.3 * trend_score + 0.2 * recency, 3)
