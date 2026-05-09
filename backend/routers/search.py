"""Search Router — NL and filter-based endpoints"""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
import re, os
from supabase import create_client

router = APIRouter()

def get_supabase():
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

SUBJECT_MAP = {
    "electrical": "Electrical Engineering",
    "maths": "Engineering Mathematics",
    "mathematics": "Engineering Mathematics",
    "dbms": "Database Management Systems",
    "network theory": "Network Theory",
    "signals": "Signals & Systems",
    "control": "Control Systems",
    "digital": "Digital Electronics",
    "data structures": "Data Structures",
    "os": "Operating Systems",
    "operating systems": "Operating Systems",
}

def parse_nl_query(query: str) -> dict:
    q = query.lower()
    result = {}
    m = re.search(r"\b(\d+)\b", q)
    result["count"] = int(m.group(1)) if m else 10
    if any(w in q for w in ["theory", "theoretical", "descriptive"]): result["question_type"] = "theory"
    elif any(w in q for w in ["numerical", "numeric", "calculation"]): result["question_type"] = "numerical"
    elif any(w in q for w in ["short", "brief", "define"]): result["question_type"] = "short"
    m = re.search(r"unit\s*(\d)", q)
    if m: result["unit"] = int(m.group(1))
    for key, full in SUBJECT_MAP.items():
        if key in q: result["subject"] = full; break
    m = re.search(r"(?:more than|at least|repeated)\s*(\d+)", q)
    if m: result["min_frequency"] = int(m.group(1))
    return result


class NLSearchRequest(BaseModel):
    query: str

class FilterSearchRequest(BaseModel):
    subject: Optional[str] = None
    unit: Optional[int] = None
    question_type: Optional[str] = None
    count: int = 10
    min_frequency: Optional[int] = None


@router.post("/nl")
async def search_natural_language(req: NLSearchRequest, request: Request):
    if not req.query.strip():
        raise HTTPException(400, "Query cannot be empty")
    parsed = parse_nl_query(req.query)
    results = await run_search(**{k: parsed.get(k) for k in ["subject","unit","question_type","count","min_frequency"]})
    return {"parsed_intent": parsed, "results": results}


@router.post("/filter")
async def search_with_filters(req: FilterSearchRequest):
    results = await run_search(subject=req.subject, unit=req.unit, question_type=req.question_type,
                                count=req.count, min_frequency=req.min_frequency)
    return {"results": results}


async def run_search(subject=None, unit=None, question_type=None, count=10, min_frequency=None):
    sb = get_supabase()
    q = sb.table("questions").select("*")
    if subject: q = q.ilike("subject", f"%{subject}%")
    if unit: q = q.eq("unit", unit)
    if question_type: q = q.eq("question_type", question_type)
    if min_frequency: q = q.gte("frequency_count", min_frequency)
    result = q.order("importance_score", desc=True).order("frequency_count", desc=True).limit(count or 10).execute()
    return result.data
