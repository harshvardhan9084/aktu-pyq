"""Admin Router — upload+process, approve/reject, stats, logs"""

from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException, Request
from typing import Optional
import os, logging
from datetime import datetime
from supabase import create_client
from services.pdf_processor import compute_file_hash, process_pdf, normalize_question, extract_question_type
from services.clustering import cluster_questions, detect_trend, compute_importance_score

router = APIRouter()
logger = logging.getLogger(__name__)
LOG_BUFFER: list = []


def log(msg: str, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] {level}: {msg}"
    LOG_BUFFER.append(entry)
    if len(LOG_BUFFER) > 200: LOG_BUFFER.pop(0)
    (logger.error if level == "ERROR" else logger.info)(msg)


def get_supabase():
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))


def verify_admin(token: Optional[str]):
    expected = os.getenv("ADMIN_API_TOKEN")
    if not expected or token != expected:
        raise HTTPException(403, "Admin access denied.")


async def process_and_insert(pdf_bytes: bytes, subject: str, year_int: Optional[int],
                              semester_int: Optional[int], branch: str, embedder, sb):
    extracted, method, n_pages = process_pdf(pdf_bytes)
    log(f"Extracted {len(extracted)} questions via {method} from {n_pages} pages")

    if not extracted:
        return 0, 0, 0

    # extracted is now List[ExtractedQuestion] — get text for embedding
    texts = [normalize_question(q.text) for q in extracted]
    embeddings = embedder.embed_batch(texts)
    cluster_labels = cluster_questions(embeddings, [q.text for q in extracted])
    n_clusters = len(set(l for l in cluster_labels if l != -1))

    new_count = 0
    for eq, cluster_id in zip(extracted, cluster_labels):
        q_text = eq.text
        existing = sb.table("questions").select("id,frequency_count,year_appeared").ilike("question_text", q_text[:80]).execute()
        if existing.data:
            r = existing.data[0]
            years = r.get("year_appeared") or []
            if year_int and year_int not in years: years.append(year_int)
            sb.table("questions").update({
                "frequency_count": r["frequency_count"] + 1,
                "year_appeared": years,
                "last_appearance_year": year_int or r.get("last_appearance_year"),
            }).eq("id", r["id"]).execute()
        else:
            sb.table("questions").insert({
                "question_text": q_text,
                "normalized_text": normalize_question(q_text),
                "subject": subject or None,
                "branch": branch or None,
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


@router.post("/upload")
async def admin_upload(
    request: Request,
    file: UploadFile = File(...),
    subject: str = Form(""), branch: str = Form(""),
    semester: str = Form(""), year: str = Form(""),
    university: str = Form("AKTU"),
    x_admin_token: Optional[str] = Header(None),
):
    verify_admin(x_admin_token)
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files accepted.")

    pdf_bytes = await file.read()
    file_hash = compute_file_hash(pdf_bytes)
    sb = get_supabase()

    if sb.table("pdf_submissions").select("id").eq("file_hash", file_hash).execute().data:
        raise HTTPException(409, "Duplicate: this paper is already processed.")

    log(f"Admin upload: {file.filename} | {subject} | {year}")
    year_int = int(year) if year.isdigit() else None
    semester_int = int(semester) if semester.isdigit() else None

    total, new_q, clusters = await process_and_insert(pdf_bytes, subject, year_int, semester_int, branch, request.app.state.embedder, sb)

    sb.table("pdf_submissions").insert({
        "filename": file.filename, "file_hash": file_hash, "subject": subject or None,
        "semester": semester_int, "year": year_int, "submitted_by": "admin", "status": "approved",
    }).execute()

    log(f"Done: {new_q} new questions, {total - new_q} updates, {clusters} clusters")
    return {"questions_extracted": total, "new_questions": new_q, "clusters_formed": clusters}


@router.get("/submissions")
async def get_submissions(x_admin_token: Optional[str] = Header(None)):
    verify_admin(x_admin_token)
    sb = get_supabase()
    return sb.table("pdf_submissions").select("*").order("created_at", desc=True).limit(100).execute().data


@router.post("/submissions/{sid}/approve")
async def approve_submission(sid: int, request: Request, x_admin_token: Optional[str] = Header(None)):
    verify_admin(x_admin_token)
    sb = get_supabase()
    sub = sb.table("pdf_submissions").select("*").eq("id", sid).execute()
    if not sub.data: raise HTTPException(404, "Not found.")
    row = sub.data[0]
    try:
        pdf_bytes = sb.storage.from_("pdf-uploads").download(f"submissions/{row['file_hash']}.pdf")
        await process_and_insert(pdf_bytes, row.get("subject",""), row.get("year"), row.get("semester"), "", request.app.state.embedder, sb)
        log(f"Submission {sid} approved and processed")
    except Exception as e:
        log(f"Approval processing error for {sid}: {e}", "WARN")
    sb.table("pdf_submissions").update({"status": "approved"}).eq("id", sid).execute()
    return {"ok": True}


@router.post("/submissions/{sid}/reject")
async def reject_submission(sid: int, x_admin_token: Optional[str] = Header(None)):
    verify_admin(x_admin_token)
    get_supabase().table("pdf_submissions").update({"status": "rejected"}).eq("id", sid).execute()
    log(f"Submission {sid} rejected")
    return {"ok": True}


@router.get("/stats")
async def get_stats(x_admin_token: Optional[str] = Header(None)):
    verify_admin(x_admin_token)
    sb = get_supabase()
    total_q = sb.table("questions").select("id", count="exact").execute().count or 0
    total_subs = sb.table("pdf_submissions").select("id", count="exact").execute().count or 0
    pending = sb.table("pdf_submissions").select("id", count="exact").eq("status", "pending").execute().count or 0
    subjects_data = sb.table("questions").select("subject").execute()
    unique_subjects = len(set(r["subject"] for r in subjects_data.data if r.get("subject")))
    ocr_errs = sum(1 for l in LOG_BUFFER if "ERROR" in l and "OCR" in l)
    return {
        "total_questions": total_q, "total_clusters": 0,
        "total_subjects": unique_subjects, "total_pdfs_processed": total_subs,
        "pending_submissions": pending, "ocr_errors_today": ocr_errs,
        "last_processed": datetime.now().isoformat(),
    }


@router.get("/logs")
async def get_logs(x_admin_token: Optional[str] = Header(None)):
    verify_admin(x_admin_token)
    return {"logs": list(reversed(LOG_BUFFER))}
