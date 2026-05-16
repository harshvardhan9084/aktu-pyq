"""
Search Router — v2
NEW: unit filter, seen_in_label, full question context, papers browser endpoint,
     subject dropdown from DB, question view tracking, /papers endpoint
"""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
import re, os
from supabase import create_client

router = APIRouter()
_sb = None


def get_supabase():
    global _sb
    if _sb is None:
        _sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
    return _sb


SUBJECT_MAP = {
    "electrical": "Basic Electrical Engineering",
    "bee": "Basic Electrical Engineering",
    "maths": "Engineering Mathematics",
    "mathematics": "Engineering Mathematics",
    "em1": "Engineering Mathematics I",
    "em2": "Engineering Mathematics II",
    "dbms": "Database Management Systems",
    "database": "Database Management Systems",
    "network theory": "Network Theory",
    "signals": "Signals & Systems",
    "control": "Control Systems",
    "digital": "Digital Electronics",
    "data structures": "Data Structures",
    "ds": "Data Structures",
    "os": "Operating Systems",
    "operating systems": "Operating Systems",
    "computer networks": "Computer Networks",
    "cn": "Computer Networks",
    "fluid": "Fluid Mechanics",
    "thermodynamics": "Engineering Thermodynamics",
    "software": "Software Engineering",
    "se": "Software Engineering",
}

UNIVERSITY_MAP = {
    "aktu": "AKTU", "apjaktu": "AKTU", "uptu": "AKTU", "gbtu": "AKTU",
}


def parse_nl_query(query: str) -> dict:
    q = query.lower()
    result = {}
    m = re.search(r"\b(\d+)\b", q)
    result["count"] = int(m.group(1)) if m else 10
    if any(w in q for w in ["theory", "theoretical", "descriptive", "long"]): result["question_type"] = "theory"
    elif any(w in q for w in ["numerical", "numeric", "calculation", "solve"]): result["question_type"] = "numerical"
    elif any(w in q for w in ["short", "brief", "define", "2 marks"]): result["question_type"] = "short"
    elif any(w in q for w in ["diagram", "draw", "circuit", "sketch"]): result["question_type"] = "diagram"
    m = re.search(r"unit[\s\-]*([1-5]|i{1,3}v?|vi?)", q, re.IGNORECASE)
    if m:
        unit_str = m.group(1)
        roman = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5}
        result["unit"] = roman.get(unit_str.lower(), int(unit_str) if unit_str.isdigit() else None)
    for key, full in SUBJECT_MAP.items():
        if key in q: result["subject"] = full; break
    for key, code in UNIVERSITY_MAP.items():
        if key in q: result["university"] = code; break
    m = re.search(r"(?:more than|at least|repeated)\s*(\d+)", q)
    if m: result["min_frequency"] = int(m.group(1))
    m = re.search(r"sem(?:ester)?\s*([1-8])", q)
    if m: result["semester"] = int(m.group(1))
    if "must revise" in q or "important" in q: result["must_revise"] = True
    return result


def build_seen_in_label(frequency_count: int, year_appeared: list) -> str:
    n = frequency_count or 0
    years = sorted(year_appeared or [])
    if n == 0:
        return "No data"
    if n == 1:
        yr = f" ({years[0]})" if years else ""
        return f"Seen in 1 exam{yr}"
    if years:
        yr_range = f" ({years[0]}–{years[-1]})" if years[0] != years[-1] else f" ({years[0]})"
        return f"Seen in {n} exams{yr_range}"
    return f"Seen in {n} exams"


def enrich_question(q: dict) -> dict:
    """Add computed display fields to a question row."""
    q["seen_in_label"] = build_seen_in_label(
        q.get("frequency_count", 0),
        q.get("year_appeared") or [],
    )
    return q


def escape_like(val: str) -> str:
    return val.replace("%", r"\%").replace("_", r"\_")


class NLSearchRequest(BaseModel):
    query: str

class FilterSearchRequest(BaseModel):
    university: Optional[str] = None
    subject: Optional[str] = None
    branch: Optional[str] = None
    programme: Optional[str] = None
    semester: Optional[int] = None
    unit: Optional[int] = None
    question_type: Optional[str] = None
    must_revise: Optional[bool] = None
    min_frequency: Optional[int] = None
    count: Optional[int] = 10


@router.post("/nl")
async def search_natural_language(req: NLSearchRequest):
    if not req.query.strip():
        raise HTTPException(400, "Query cannot be empty")
    parsed = parse_nl_query(req.query)
    results = await run_search(
        university=parsed.get("university"),
        subject=parsed.get("subject"),
        unit=parsed.get("unit"),
        semester=parsed.get("semester"),
        question_type=parsed.get("question_type"),
        must_revise=parsed.get("must_revise"),
        min_frequency=parsed.get("min_frequency"),
        count=parsed.get("count", 10),
    )
    return {"parsed_intent": parsed, "results": results}


@router.post("/filter")
async def search_with_filters(req: FilterSearchRequest):
    results = await run_search(
        university=req.university,
        subject=req.subject,
        branch=req.branch,
        programme=req.programme,
        semester=req.semester,
        unit=req.unit,
        question_type=req.question_type,
        must_revise=req.must_revise,
        min_frequency=req.min_frequency,
        count=req.count,
    )
    return {"results": results}


async def run_search(
    university=None, subject=None, branch=None, programme=None,
    semester=None, unit=None, question_type=None,
    must_revise=None, min_frequency=None, count=10,
):
    sb = get_supabase()
    # Select all columns for full context
    q = sb.table("questions").select(
        "id,question_text,normalized_text,university,subject,subject_code,"
        "branch,programme,semester,unit,unit_topic,question_type,"
        "difficulty_level,marks_weightage,has_diagram,diagram_url,has_math,"
        "sub_parts,cluster_id,year_appeared,exam_sessions,frequency_count,"
        "first_appearance_year,last_appearance_year,trend_direction,"
        "primary_topic,concept_tags,importance_score,exam_probability_score,"
        "must_revise_flag,user_views_count,user_confirmed_count,page_number,created_at"
    )
    q = q.eq("university", university or "AKTU")
    if subject:
        q = q.ilike("subject", f"%{escape_like(subject)}%")
    if branch:
        q = q.ilike("branch", f"%{escape_like(branch)}%")
    if programme:
        q = q.eq("programme", programme)
    if semester:
        q = q.eq("semester", semester)
    if unit:
        q = q.eq("unit", unit)
    if question_type:
        q = q.eq("question_type", question_type)
    if must_revise:
        q = q.eq("must_revise_flag", True)
    if min_frequency:
        q = q.gte("frequency_count", min_frequency)
    effective_count = count if count is not None else 10
    result = (
        q.order("importance_score", desc=True)
         .order("frequency_count", desc=True)
         .limit(effective_count)
         .execute()
    )
    return [enrich_question(row) for row in result.data]


@router.get("/universities")
async def list_universities():
    sb = get_supabase()
    data = sb.table("universities").select("name, short_code").eq("is_active", True).execute().data
    return {"universities": data}


@router.get("/subjects")
async def list_subjects(
    university: str = "AKTU",
    branch: Optional[str] = None,
    semester: Optional[int] = None,
):
    """Dynamic subject list from actual DB data — for DynamicForm dropdown."""
    sb = get_supabase()
    q = sb.table("questions").select("subject").eq("university", university).not_.is_("subject", "null")
    if branch:
        q = q.ilike("branch", f"%{escape_like(branch)}%")
    if semester:
        q = q.eq("semester", semester)
    rows = q.execute().data or []
    subjects = sorted(set(r["subject"] for r in rows if r.get("subject")))
    return {"subjects": subjects}


@router.get("/papers")
async def list_papers(
    university: str = "AKTU",
    programme: Optional[str] = None,
    branch: Optional[str] = None,
    semester: Optional[int] = None,
    year: Optional[int] = None,
    limit: int = 100,
):
    """
    Papers browser — lists indexed papers as cards.
    Returns pdf_submissions with status=approved, filtered.
    Each paper includes question count from questions table.
    """
    sb = get_supabase()
    q = sb.table("pdf_submissions").select("*").eq("university", university).eq("status", "approved")
    if programme:
        q = q.eq("programme", programme)
    if branch:
        q = q.ilike("branch", f"%{escape_like(branch)}%")
    if semester:
        q = q.eq("semester", semester)
    if year:
        q = q.eq("year", year)
    papers = q.order("year", desc=True).limit(limit).execute().data or []

    # Attach question counts per subject+semester+year
    for paper in papers:
        try:
            cq = sb.table("questions").select("id", count="exact")
            if paper.get("subject"):
                cq = cq.ilike("subject", f"%{escape_like(paper['subject'])}%")
            if paper.get("semester"):
                cq = cq.eq("semester", paper["semester"])
            paper["question_count"] = cq.execute().count or 0
        except Exception:
            paper["question_count"] = 0

    return {"papers": papers, "total": len(papers)}


@router.get("/stats/public")
async def public_stats():
    """Public stats for homepage counter — questions indexed."""
    sb = get_supabase()
    total_q = sb.table("questions").select("id", count="exact").execute().count or 0
    total_papers = sb.table("pdf_submissions").select("id", count="exact").eq("status", "approved").execute().count or 0
    total_subjects = len(set(
        r["subject"] for r in
        (sb.table("questions").select("subject").not_.is_("subject", "null").execute().data or [])
        if r.get("subject")
    ))
    return {
        "total_questions": total_q,
        "total_papers": total_papers,
        "total_subjects": total_subjects,
    }


@router.post("/questions/{qid}/view")
async def track_question_view(qid: int):
    """Increment user_views_count when a student expands a question."""
    try:
        sb = get_supabase()
        row = sb.table("questions").select("user_views_count").eq("id", qid).execute()
        if row.data:
            new_val = (row.data[0]["user_views_count"] or 0) + 1
            sb.table("questions").update({"user_views_count": new_val}).eq("id", qid).execute()
    except Exception as e:
        pass  # non-fatal
    return {"ok": True}
