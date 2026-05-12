"""Search Router — NL and filter-based endpoints
Supports multi-university search via university filter parameter."""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
import re, os
from supabase import create_client

router = APIRouter()

_supabase_client = None


def get_supabase():
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
    return _supabase_client


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

# Known university short codes for NL parsing
UNIVERSITY_MAP = {
    "aktu": "AKTU",
    "apjaktu": "AKTU",
    "uptu": "AKTU",
    "gbtu": "AKTU",
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
    for key, code in UNIVERSITY_MAP.items():
        if key in q: result["university"] = code; break
    m = re.search(r"(?:more than|at least|repeated)\s*(\d+)", q)
    if m: result["min_frequency"] = int(m.group(1))
    return result


class NLSearchRequest(BaseModel):
    query: str

class FilterSearchRequest(BaseModel):
    university: Optional[str] = None
    subject: Optional[str] = None
    branch: Optional[str] = None
    programme: Optional[str] = None
    unit: Optional[int] = None
    question_type: Optional[str] = None
    count: Optional[int] = 10
    min_frequency: Optional[int] = None


@router.post("/nl")
async def search_natural_language(req: NLSearchRequest, request: Request):
    if not req.query.strip():
        raise HTTPException(400, "Query cannot be empty")
    parsed = parse_nl_query(req.query)
    results = await run_search(**{k: parsed.get(k) for k in ["university","subject","branch","programme","unit","question_type","count","min_frequency"]})
    return {"parsed_intent": parsed, "results": results}


@router.post("/filter")
async def search_with_filters(req: FilterSearchRequest):
    results = await run_search(
        university=req.university, subject=req.subject, branch=req.branch,
        programme=req.programme, unit=req.unit, question_type=req.question_type,
        count=req.count, min_frequency=req.min_frequency
    )
    return {"results": results}


@router.get("/universities")
async def list_universities():
    """Return list of active universities for the frontend dropdown."""
    sb = get_supabase()
    data = sb.table("universities").select("name, short_code").eq("is_active", True).execute().data
    return {"universities": data}


def escape_like(val: str) -> str:
    """Escape LIKE special characters % and _ so they match literally."""
    return val.replace("%", r"\%").replace("_", r"\_")


async def run_search(university=None, subject=None, branch=None, programme=None,
                     unit=None, question_type=None, count=10, min_frequency=None):
    sb = get_supabase()
    q = sb.table("questions").select("*")
    if university:
        q = q.eq("university", university)
    elif not university:
        # Default to AKTU for backward compatibility
        q = q.eq("university", "AKTU")
    if subject:
        q = q.ilike("subject", f"%{escape_like(subject)}%")
    if branch:
        q = q.ilike("branch", f"%{escape_like(branch)}%")
    if programme:
        q = q.eq("programme", programme)
    if unit: q = q.eq("unit", unit)
    if question_type: q = q.eq("question_type", question_type)
    if min_frequency: q = q.gte("frequency_count", min_frequency)
    # Fix: use "if count is not None" instead of "count or 10" to handle count=0
    effective_count = count if count is not None else 10
    result = q.order("importance_score", desc=True).order("frequency_count", desc=True).limit(effective_count).execute()
    return result.data
