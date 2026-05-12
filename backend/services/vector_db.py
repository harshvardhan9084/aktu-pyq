"""
Vector Database Service — ChromaDB
Free, runs locally inside the backend process, no separate server needed.
"""

import chromadb
import os
from typing import List, Optional


class VectorDBService:
    def __init__(self):
        persist_path = os.getenv("CHROMA_PERSIST_PATH", "./chroma_db")
        self.client = chromadb.PersistentClient(path=persist_path)
        self.collection = self.client.get_or_create_collection(
            name="aktu_questions",
            metadata={"hnsw:space": "cosine"},
        )
        print(f"  ChromaDB at: {persist_path} | {self.collection.count()} vectors loaded")

    def add_question(self, question_id: int, embedding: List[float], metadata: dict):
        self.collection.add(
            ids=[str(question_id)],
            embeddings=[embedding],
            metadatas=[metadata],
        )

    def add_questions_batch(self, question_ids: List[int], embeddings: List[List[float]], metadatas: List[dict]):
        self.collection.add(
            ids=[str(qid) for qid in question_ids],
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def search(self, query_embedding: List[float], n_results: int = 10, where: Optional[dict] = None) -> List[dict]:
        n = min(n_results, max(self.collection.count(), 1))
        kwargs = dict(query_embeddings=[query_embedding], n_results=n, include=["metadatas", "distances"])
        if where:
            kwargs["where"] = where

        results = self.collection.query(**kwargs)
        out = []
        for i, meta in enumerate(results["metadatas"][0]):
            out.append({
                "question_id": int(results["ids"][0][i]),
                "metadata": meta,
                "similarity": 1 - results["distances"][0][i],
            })
        return out

    def delete_question(self, question_id: int):
        self.collection.delete(ids=[str(question_id)])

    def count(self) -> int:
        return self.collection.count()
