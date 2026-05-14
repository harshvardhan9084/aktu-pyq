"""
AKTU PYQ Intelligence System — Backend
FastAPI + Sentence Transformers + ChromaDB
"""

from fastapi import FastAPI, Request
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

# ---------------------------------------------------------------------------
# THE "NUCLEAR" CORS FIX: CUSTOM MIDDLEWARE
# This replaces CORSMiddleware entirely to avoid "unhashable type: list" 
# errors and to solve the Vercel Preflight issue once and for all.
# ---------------------------------------------------------------------------

@app.middleware("http")
async def custom_cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin")
    
    # Check if origin is from Vercel or localhost
    is_allowed = False
    if origin:
        if ".vercel.app" in origin or "localhost" in origin:
            is_allowed = True
    
    # 1. Handle the Preflight (OPTIONS) request immediately
    if request.method == "OPTIONS":
        from fastapi.responses import Response
        response = Response(status_code=200)
        if is_allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "*"
            response.headers["Access-Control-Allow-Headers"] = "*"
        return response

    # 2. Handle the actual request (GET, POST, etc.)
    response = await call_next(request)
    
    if is_allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
    
    return response

# ---------------------------------------------------------------------------

app.include_router(search.router, prefix="/search", tags=["Search"])
app.include_router(upload.router, prefix="/submit", tags=["Submit"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])


@app.get("/health")
def health():
    return {"status": "ok", "service": "AKTU PYQ Intelligence"}

@app.get("/")
def root():
    return {"message": "AKTU PYQ Intelligence API is running."}