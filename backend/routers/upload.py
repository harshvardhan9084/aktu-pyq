"""
Upload Router — v3.0 (Precision Engine Compatible)
═══════════════════════════════════════════════════
CHANGES from v2:
  ✓ Imports split_papers for multi-paper detection in metadata preview
  ✓ Stores enriched paper metadata in pdf_submissions (total_marks,
    time_duration, paper_id, is_bilingual, college_code)
  ✓ Returns full PaperMetadata in response for transparency
  ✓ Backwards compatible — existing API contract unchanged

REPLACE: backend/routers/upload.py with this file.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Request
import os, logging, time, hashlib, io
from supabase import create_client
from services.pdf_processor import compute_file_hash, extract_paper_metadata, split_papers

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 5

_upload_attempts: dict = {}
_sb = None


def get_supabase():
    global _sb
    if _sb is None:
        _sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
    return _sb


def _check_rate_limit(client_ip: str) -> bool:
    now = time.time()
    _upload_attempts.setdefault(client_ip, [])
    _upload_attempts[client_ip] = [t for t in _upload_attempts[client_ip] if now - t < RATE_LIMIT_WINDOW]
    if len(_upload_attempts[client_ip]) >= RATE_LIMIT_MAX:
        return True
    _upload_attempts[client_ip].append(now)
    return False


@router.post("/pdf")
async def submit_pdf(
    request: Request,
    file: UploadFile = File(...),
):
    """
    Student contribution endpoint.
    - No manual metadata fields — everything auto-extracted from the PDF header.
    - Duplicate detected immediately via file_hash.
    - File goes into scrape_queue for automatic processing.
    - pdf_submissions record created for audit trail.
    - v3.0: Stores enriched metadata (total_marks, time_duration, paper_id, is_bilingual)
    """
    client_ip = request.client.host if request.client else "unknown"
    if _check_rate_limit(client_ip):
        raise HTTPException(429, "Too many uploads. Please wait a minute before trying again.")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large. Maximum size is 20 MB.")

    file_hash = compute_file_hash(pdf_bytes)
    sb = get_supabase()

    # Exact duplicate check — same file bytes
    existing_sub = sb.table("pdf_submissions").select("id,status,subject,year").eq("file_hash", file_hash).execute()
    if existing_sub.data:
        row = existing_sub.data[0]
        subject_hint = row.get("subject") or "this subject"
        return {
            "duplicate": True,
            "message": f"We already have this exact paper in our database ({subject_hint}). Thank you for trying to help!",
            "subject": subject_hint,
        }

    # Auto-extract metadata from paper header (v3.0: full precision extraction)
    meta = extract_paper_metadata(pdf_bytes)

    # v3.0: Detect multi-paper PDFs for richer metadata
    papers = split_papers(pdf_bytes)
    is_multi = len(papers) > 1
    if is_multi:
        # Use first paper's metadata for submission record, store multi-paper info
        meta = papers[0].metadata
        logger.info(f"Multi-paper upload detected: {len(papers)} papers in {file.filename}")

    # Check scrape_queue for same file (by subject+year+session)
    if meta.subject_code and meta.year and meta.exam_session:
        dupes = (
            sb.table("pdf_submissions")
            .select("id,subject")
            .eq("subject_code", meta.subject_code)
            .eq("year", meta.year)
            .eq("exam_session", meta.exam_session)
            .execute()
        )
        if dupes.data:
            subject_hint = dupes.data[0].get("subject") or meta.subject_name or meta.subject_code
            return {
                "duplicate": True,
                "message": f"We already have this paper ({subject_hint}, {meta.year} {meta.exam_session.capitalize()} Semester). Thank you anyway!",
                "subject": subject_hint,
            }

    # Upload PDF to storage
    storage_path = f"submissions/{file_hash}.pdf"
    try:
        sb.storage.from_("pdf-uploads").upload(storage_path, pdf_bytes, {"content-type": "application/pdf"})
    except Exception as e:
        logger.warning(f"Storage upload failed (non-fatal): {e}")

    # Insert pdf_submissions record — v3.0: enriched with new metadata fields
    sub_record = {
        "filename": file.filename,
        "file_hash": file_hash,
        "university": meta.university,
        "subject": meta.subject_name,
        "subject_code": meta.subject_code,
        "branch": meta.branch,
        "programme": meta.programme,
        "semester": meta.semester,
        "year": meta.year,
        "exam_session": meta.exam_session,
        "submitted_by": "student",
        "status": "pending",
    }
    sub_result = sb.table("pdf_submissions").insert(sub_record).execute()
    sub_id = sub_result.data[0]["id"] if sub_result.data else None

    # Add to scrape_queue — points to storage URL
    queue_url = f"internal://submissions/{file_hash}.pdf"
    try:
        sb.table("scrape_queue").insert({
            "pdf_url": queue_url,
            "status": "pending",
            "subject": meta.subject_name,
            "subject_code": meta.subject_code,
            "branch": meta.branch,
            "programme": meta.programme,
            "semester": meta.semester,
            "year": meta.year,
            "exam_session": meta.exam_session,
        }).execute()
    except Exception as e:
        logger.warning(f"scrape_queue insert failed: {e}")

    # Track contribution analytics
    try:
        sb.table("analytics_events").insert({
            "event_type": "contribute",
            "page": "/contribute",
            "metadata": {"filename": file.filename, "subject_code": meta.subject_code},
        }).execute()
        # Increment contributors counter
        row = sb.table("site_counters").select("value").eq("key", "total_contributors").execute()
        if row.data:
            new_val = (row.data[0]["value"] or 0) + 1
            sb.table("site_counters").update({"value": new_val}).eq("key", "total_contributors").execute()
    except Exception:
        pass

    logger.info(f"New contribution: {file.filename} | {meta.subject_name} | {meta.year} {meta.exam_session}")

    subject_hint = meta.subject_name or meta.subject_code or "your paper"
    return {
        "duplicate": False,
        "message": "Paper received and queued for processing.",
        "subject": subject_hint,
        "metadata": {
            "subject": meta.subject_name,
            "subject_code": meta.subject_code,
            "branch": meta.branch,
            "programme": meta.programme,
            "semester": meta.semester,
            "year": meta.year,
            "exam_session": meta.exam_session,
            # v3.0 new fields
            "total_marks": meta.total_marks,
            "time_duration": meta.time_duration,
            "paper_id": meta.paper_id,
            "college_code": meta.college_code,
            "is_bilingual": meta.is_bilingual,
            "multi_paper_detected": is_multi,
            "papers_count": len(papers) if is_multi else 1,
            "confidence_scores": meta.confidence_scores,
        },
        "submission_id": sub_id,
    }
