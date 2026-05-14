"""
AKTU PYQ Intelligence System — Backend
FastAPI + Sentence Transformers + ChromaDB
100% free stack
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv

load_dotenv()

from routers import search, upload, admin
from services.embedding import EmbeddingService


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Loading embedding model...")
    app.state.embedder = EmbeddingService()
    print("Embedding model ready")

    yield
    print("Shutting down")


app = FastAPI(
    title="AKTU PYQ Intelligence API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search.router, prefix="/search", tags=["Search"])
app.include_router(upload.router, prefix="/submit", tags=["Submit"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])


@app.get("/health")
def health():
    return {"status": "ok", "service": "AKTU PYQ Intelligence"}

@app.get("/")
def read_root():
    return {"message": "AKTU PYQ API is running. Go to /docs for documentation."}