"""
Admin Router — upload+process, approve/reject, stats, logs
Handles secure administrative actions for the AKTU PYQ system.
"""

from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException, Request
from typing import Optional
import os
import logging
import hashlib
from datetime import datetime
from fastapi.responses import JSONResponse

from supabase import create_client
from services.pdf_processor import compute_file_hash, process_pdf, normalize_question
from services.clustering import cluster_questions

router = APIRouter()

# -----------------------------
# Admin helpers & Security
# -----------------------------

logger = logging.getLogger(__name__)
LOG_BUFFER: list = []

def log(msg: str, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] {level}: {msg}"
    LOG_BUFFER.append(entry)
    if len(LOG_BUFFER) > 200: 
        LOG_BUFFER.pop(0)
    if level == "ERROR":
        logger.error(msg)
    else:
        logger.info(msg)

def _safe_get_token(x_admin_token: Optional[str], auth_header: Optional[str]) -> Optional[str]:
    """Extracts token from either X-Admin-Token header or Authorization Bearer header."""
    if x_admin_token:
        return x_admin_token
    if not auth_header:
        return None
    parts = auth_header.split(' ')
    if len(parts) == 2 and parts[0].lower() == 'bearer':
        return parts[1]
    return auth_header

def verify_admin(token: Optional[str]):
    """
    CRITICAL FIX: Matches the frontend's salted session token logic.
    Frontend creates: sha256(ADMIN_PASSWORD_HASH + 'session_salt_aktu_pyq')
    """
    raw_password_hash = os.getenv("ADMIN_API_TOKEN")
    
    if not raw_password_hash:
        raise HTTPException(403, "Admin configuration missing on server.")
    if not token:
        raise HTTPException(403, "No authentication token provided.")

    # Replicate the exact hashing algorithm used in the Next.js 'route.ts'
    hasher = hashlib.sha256()
    hasher.update((raw_password_hash + 'session_salt_aktu_pyq').encode('utf-8'))
    expected_session_token = hasher.hexdigest()

    if token != expected_session_token:
        raise HTTPException(403, "Admin access denied: Invalid session.")

_supabase_client = None

def get_supabase():
    global _supabase_client
    if _supabase_client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        if not url or not key:
            raise RuntimeError("Supabase credentials not found in environment variables.")
        _supabase_client = create_client(url, key)
    return _supabase_client


# -----------------------------
# Core Processing Logic
# -----------------------------

async def process_and_insert(pdf_bytes: bytes, subject: str, year_int: Optional[int],
                              semester_int: Optional[int], branch: str, university: str,
                              programme: Optional[str], embedder, sb):
    extracted, method, n_pages = process_pdf(pdf_bytes)
    log(f"Extracted {len(extracted)} questions via {method} from {n_pages} pages")

    if not extracted:
        return 0, 0, 0

    # Get normalized text for embeddings
    texts = [normalize_question(q.text) for q in extracted]
    embeddings = embedder.embed_batch(texts)
    cluster_labels = cluster_questions(embeddings, [q.text for q in extracted])
    n_clusters = len(set(l for l in cluster_labels if l != -1))

    new_count = 0
    for eq, cluster_id in zip(extracted, cluster_labels):
        q_text = eq.text
        q_normalized = normalize_question(q_text)

        # Duplicate detection using normalized text
        existing = sb.table("questions").select("id,frequency_count,year_appeared")\
            .ilike("normalized_text", f"%{q_normalized[:60]}%").execute()

        if existing.data:
            r = existing.data[0]
            years = r.get("year_appeared") or []
            if year_int and year_int not in years: 
                years.append(year_int)
            
            sb.table("questions").update({
                "frequency_count": r["frequency_count"] + 1,
                "year_appeared": years,
                "last_appearance_year": year_int or r.get("last_appearance_year"),
            }).eq("id", r["id"]).execute()
        else:
            sb.table("questions").insert({
                "question_text": q_text,
                "normalized_text": q_normalized,
                "university": university or "AKTU",
                "subject": subject or None,
                "branch": branch or None,
                "programme": programme or None,
                "semester": semester_int,
                "year_appeared": [year_int] if year_int else [],
                "frequency_count": 1,
                "first_appearance_year": year_int,
                "last_appearance_year": year_int,
                "question_type": eq.question_type,
                "cluster_id": cluster_id if cluster_id != -1 else None,
                "concept_tags": [],
                "importance_score": 0.0,
                "must_revise_flag": False,
                "trend_direction": "insufficient_data",
            }).execute()
            new_count += 1

    return len(extracted), new_count, n_clusters


# -----------------------------
# API Endpoints
# -----------------------------

@router.post("/upload")
async def admin_upload(
    request: Request,
    file: UploadFile = File(...),
    subject: str = Form(""),
    branch: str = Form(""),
    programme: str = Form(""),
    semester: str = Form(""),
    year: str = Form(""),
    university: str = Form("AKTU"),
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files accepted.")

    pdf_bytes = await file.read()
    file_hash = compute_file_hash(pdf_bytes)
    sb = get_supabase()

    # Check if this paper was already approved via submission
    existing = sb.table("pdf_submissions").select("id,status").eq("file_hash", file_hash).execute()
    if existing.data:
        status = existing.data[0].get("status", "pending")
        if status == "approved":
            raise HTTPException(409, "Duplicate: this paper is already processed.")

    log(f"Admin upload started: {file.filename} | {subject} | {year}")
    year_int = int(year) if year.isdigit() else None
    semester_int = int(semester) if semester.isdigit() else None

    total, new_q, clusters = await process_and_insert(
        pdf_bytes, subject, year_int, semester_int, branch, university, 
        programme or None, request.app.state.embedder, sb
    )

    # Update or insert submission record
    if existing.data:
        sb.table("pdf_submissions").update({
            "status": "approved",
            "subject": subject or None,
            "semester": semester_int,
            "year": year_int,
        }).eq("id", existing.data[0]["id"]).execute()
    else:
        sb.table("pdf_submissions").insert({
            "filename": file.filename, "file_hash": file_hash,
            "university": university or "AKTU", "subject": subject or None,
            "branch": branch or None, "programme": programme or None,
            "semester": semester_int, "year": year_int, "submitted_by": "admin", "status": "approved",
        }).execute()

    log(f"Done: {new_q} new questions, {total - new_q} updates, {clusters} clusters")
    return {"questions_extracted": total, "new_questions": new_q, "clusters_formed": clusters}


@router.get("/submissions")
async def get_submissions(
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    sb = get_supabase()
    return sb.table("pdf_submissions").select("*").order("created_at", desc=True).limit(100).execute().data


@router.post("/submissions/{sid}/approve")
async def approve_submission(
    sid: int,
    request: Request,
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    sb = get_supabase()
    
    sub = sb.table("pdf_submissions").select("*").eq("id", sid).execute()
    if not sub.data: 
        raise HTTPException(404, "Submission not found.")
    
    row = sub.data[0]
    try:
        # Download from Supabase storage
        pdf_bytes = sb.storage.from_("pdf-uploads").download(f"submissions/{row['file_hash']}.pdf")
        await process_and_insert(
            pdf_bytes, row.get("subject",""), row.get("year"), row.get("semester"), 
            row.get("branch",""), row.get("university","AKTU"), row.get("programme"), 
            request.app.state.embedder, sb
        )
        log(f"Submission {sid} approved and processed")
    except Exception as e:
        log(f"Approval processing error for {sid}: {e}", "WARN")
        raise HTTPException(500, f"Processing failed: {str(e)}")

    sb.table("pdf_submissions").update({"status": "approved"}).eq("id", sid).execute()
    return {"ok": True}


@router.post("/submissions/{sid}/reject")
async def reject_submission(
    sid: int,
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    get_supabase().table("pdf_submissions").update({"status": "rejected"}).eq("id", sid).execute()
    log(f"Submission {sid} rejected")
    return {"ok": True}


@router.get("/stats")
async def get_stats(
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    sb = get_supabase()
    
    total_q = sb.table("questions").select("id", count="exact").execute().count or 0
    total_subs = sb.table("pdf_submissions").select("id", count="exact").execute().count or 0
    pending = sb.table("pdf_submissions").select("id", count="exact").eq("status", "pending").execute().count or 0
    
    subjects_data = sb.table("questions").select("subject").execute()
    unique_subjects = len(set(r["subject"] for r in subjects_data.data if r.get("subject")))
    
    ocr_errs = sum(1 for l in LOG_BUFFER if "ERROR" in l and "OCR" in l)
    total_clusters = sb.table("clusters").select("id", count="exact").execute().count or 0
    
    return {
        "total_questions": total_q, 
        "total_clusters": total_clusters,
        "total_subjects": unique_subjects, 
        "total_pdfs_processed": total_subs,
        "pending_submissions": pending, 
        "ocr_errors_today": ocr_errs,
        "last_processed": datetime.now().isoformat(),
    }


@router.get("/logs")
async def get_logs(
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    return {"logs": list(reversed(LOG_BUFFER))}


# -----------------------------
# Placeholder / Maintenance Endpoints
# -----------------------------

@router.post("/rebuild-index")
async def rebuild_index(x_admin_token: Optional[str] = Header(None), authorization: Optional[str] = Header(None)):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    return {"ok": True, "message": "rebuild-index queued/not implemented in this build"}


@router.post("/recalculate")
async def recalculate_scores(x_admin_token: Optional[str] = Header(None), authorization: Optional[str] = Header(None)):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    return {"ok": True, "message": "recalculate queued/not implemented in this build"}


@router.post("/recluster")
async def recluster_all(x_admin_token: Optional[str] = Header(None), authorization: Optional[str] = Header(None)):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    return {"ok": True, "message": "recluster queued/not implemented in this build"}


@router.post("/export")
async def export_database(x_admin_token: Optional[str] = Header(None), authorization: Optional[str] = Header(None)):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    sb = get_supabase()
    questions = sb.table("questions").select("*").execute().data
    submissions = sb.table("pdf_submissions").select("*").execute().data
    clusters = sb.table("clusters").select("*").execute().data
    return {
        "ok": True,
        "export": {"questions": questions, "pdf_submissions": submissions, "clusters": clusters},
    }


@router.delete("/submissions/pending")
async def clear_pending_submissions(x_admin_token: Optional[str] = Header(None), authorization: Optional[str] = Header(None)):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    sb = get_supabase()
    sb.table("pdf_submissions").delete().eq("status", "pending").execute()
    return {"ok": True, "message": "pending submissions cleared"}