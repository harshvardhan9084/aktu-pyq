"""
Admin Router — v2
NEW: scrape_queue pipeline, bulk URL feeder, diagram crop+upload,
     question_hash dedup, analytics counter updates, unit tagging
"""

from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException, Request
from typing import Optional, List
import os, logging, hashlib
from datetime import datetime
from fastapi.responses import JSONResponse

from supabase import create_client
from services.pdf_processor import (
    compute_file_hash, process_pdf, normalize_question,
    extract_diagram_crop, PaperMetadata
)
from services.clustering import cluster_questions, get_representative_question, detect_trend, compute_importance_score

router = APIRouter()
logger = logging.getLogger(__name__)
LOG_BUFFER: list = []

# ── Helpers ────────────────────────────────────────────────────────────────────

def log(msg: str, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] {level}: {msg}"
    LOG_BUFFER.append(entry)
    if len(LOG_BUFFER) > 500:
        LOG_BUFFER.pop(0)
    (logger.error if level == "ERROR" else logger.info)(msg)


def _safe_get_token(x_admin_token: Optional[str], auth_header: Optional[str]) -> Optional[str]:
    if x_admin_token:
        return x_admin_token
    if not auth_header:
        return None
    parts = auth_header.split(" ")
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return auth_header


def verify_admin(token: Optional[str]):
    raw = os.getenv("ADMIN_API_TOKEN")
    if not raw:
        raise HTTPException(403, "Admin configuration missing.")
    if not token:
        raise HTTPException(403, "No authentication token provided.")
    hasher = hashlib.sha256()
    hasher.update((raw + "session_salt_aktu_pyq").encode("utf-8"))
    if token != hasher.hexdigest():
        raise HTTPException(403, "Invalid session.")


_sb = None

def get_supabase():
    global _sb
    if _sb is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        if not url or not key:
            raise RuntimeError("Supabase credentials not configured.")
        _sb = create_client(url, key)
    return _sb


def _sanitize_question_type(qt: str) -> str:
    valid = {"theory", "numerical", "short", "diagram", "other"}
    return qt if qt in valid else "other"


def _increment_counter(sb, key: str, delta: int = 1):
    """Safely increment a site_counters row."""
    try:
        sb.rpc("increment_counter", {"counter_key": key, "delta": delta}).execute()
    except Exception:
        # Fallback: read-modify-write (less ideal under concurrency but safe enough)
        try:
            row = sb.table("site_counters").select("value").eq("key", key).execute()
            if row.data:
                new_val = (row.data[0]["value"] or 0) + delta
                sb.table("site_counters").update({"value": new_val, "updated_at": datetime.now().isoformat()}).eq("key", key).execute()
        except Exception as e:
            logger.warning(f"Counter increment failed for {key}: {e}")


# ── Core Processing ────────────────────────────────────────────────────────────

async def process_and_insert(
    pdf_bytes: bytes,
    subject: str,
    year_int: Optional[int],
    semester_int: Optional[int],
    branch: str,
    university: str,
    programme: Optional[str],
    exam_session: Optional[str],
    subject_code: Optional[str],
    embedder,
    sb,
    upload_diagrams: bool = True,
) -> dict:
    """
    Full pipeline: PDF → extract → embed → cluster → upsert into questions.

    v2 changes:
      - Uses question_hash for exact dedup (not ilike substring)
      - Auto-fills subject/branch/semester/programme from paper metadata if not provided
      - Tags each question with unit + unit_topic
      - Uploads diagram crops to Supabase Storage
      - Updates frequency_count, year_appeared, exam_sessions on duplicates
      - Computes importance_score + must_revise_flag after bulk insert
    """
    extracted, method, n_pages, paper_meta = process_pdf(pdf_bytes)
    log(f"Extracted {len(extracted)} questions via {method} | pages={n_pages} | meta={paper_meta}")

    if not extracted:
        return {"questions_extracted": 0, "new_questions": 0, "updated_questions": 0, "clusters_formed": 0}

    # Fill metadata from paper header if admin didn't provide it
    eff_subject = subject or paper_meta.subject_name or ""
    eff_branch = branch or paper_meta.branch or ""
    eff_semester = semester_int or paper_meta.semester
    eff_programme = programme or paper_meta.programme
    eff_session = exam_session or paper_meta.exam_session
    eff_code = subject_code or paper_meta.subject_code
    eff_year = year_int or paper_meta.year

    # Embed + cluster
    texts = [normalize_question(q.text) for q in extracted]
    embeddings = embedder.embed_batch(texts)
    cluster_labels = cluster_questions(embeddings, [q.text for q in extracted])
    n_clusters = len(set(l for l in cluster_labels if l != -1))

    # Upsert questions
    new_count = 0
    updated_count = 0

    # Build max_frequency for importance_score (get current max from DB for this subject)
    try:
        mf_row = sb.table("questions").select("frequency_count").eq("subject", eff_subject).order("frequency_count", desc=True).limit(1).execute()
        current_max_freq = mf_row.data[0]["frequency_count"] if mf_row.data else 1
    except Exception:
        current_max_freq = 1

    inserted_ids = []  # track (id, question_obj) for diagram upload

    for q, label in zip(extracted, cluster_labels):
        norm = normalize_question(q.text)
        q_hash = q.question_hash

        # Check by hash (exact dedup)
        existing = None
        if q_hash:
            try:
                ex = sb.table("questions").select("id,frequency_count,year_appeared,exam_sessions").eq("question_hash", q_hash).execute()
                existing = ex.data[0] if ex.data else None
            except Exception:
                existing = None

        if existing:
            # Update frequency, year list, session list
            existing_years = existing.get("year_appeared") or []
            existing_sessions = existing.get("exam_sessions") or []
            new_years = list(set(existing_years + ([eff_year] if eff_year else [])))
            new_sessions = list(set(existing_sessions + ([f"{eff_year}-{eff_session}"] if eff_year and eff_session else [])))
            new_freq = len(new_years) if new_years else (existing["frequency_count"] or 1) + 1
            trend = detect_trend(new_years)
            last_year = max(new_years) if new_years else (eff_year or datetime.now().year)
            importance = compute_importance_score(new_freq, max(current_max_freq, new_freq), trend, last_year)
            sb.table("questions").update({
                "frequency_count": new_freq,
                "year_appeared": new_years,
                "exam_sessions": new_sessions,
                "last_appearance_year": last_year,
                "trend_direction": trend,
                "importance_score": importance,
                "must_revise_flag": importance >= 0.75,
            }).eq("id", existing["id"]).execute()
            updated_count += 1
        else:
            # Insert new question
            year_list = [eff_year] if eff_year else []
            session_list = [f"{eff_year}-{eff_session}"] if eff_year and eff_session else []
            trend = "insufficient_data"
            importance = compute_importance_score(1, max(current_max_freq, 1), trend, eff_year or datetime.now().year)
            row = {
                "question_text": q.text,
                "normalized_text": norm,
                "question_hash": q_hash,
                "university": university or "AKTU",
                "subject": eff_subject or None,
                "subject_code": eff_code or None,
                "branch": eff_branch or None,
                "programme": eff_programme or None,
                "semester": eff_semester,
                "unit": q.unit,
                "unit_topic": q.unit_topic,
                "question_type": _sanitize_question_type(q.question_type),
                "has_diagram": q.has_diagram,
                "has_math": q.has_math,
                "sub_parts": q.sub_parts,
                "marks_weightage": q.marks,
                "cluster_id": label if label != -1 else None,
                "year_appeared": year_list,
                "exam_sessions": session_list,
                "frequency_count": 1,
                "first_appearance_year": eff_year,
                "last_appearance_year": eff_year,
                "trend_direction": trend,
                "importance_score": importance,
                "must_revise_flag": importance >= 0.75,
                "page_number": q.page_number,
            }
            try:
                result = sb.table("questions").insert(row).execute()
                if result.data:
                    inserted_ids.append((result.data[0]["id"], q))
                    new_count += 1
            except Exception as e:
                log(f"Insert failed (hash collision?): {e}", "WARN")

    # Insert cluster representatives
    if n_clusters > 0:
        label_groups: dict = {}
        for q, label in zip(extracted, cluster_labels):
            if label != -1:
                label_groups.setdefault(label, []).append(q.text)
        for label, group_texts in label_groups.items():
            rep = group_texts[0]
            try:
                sb.table("clusters").upsert({
                    "representative_question": rep,
                    "university": university or "AKTU",
                    "subject": eff_subject or None,
                    "frequency": len(group_texts),
                    "years": [eff_year] if eff_year else [],
                }).execute()
            except Exception:
                pass

    # Upload diagram crops
    if upload_diagrams and inserted_ids:
        for qid, q_obj in inserted_ids:
            if not q_obj.has_diagram:
                continue
            try:
                crop_bytes = extract_diagram_crop(pdf_bytes, page_number=q_obj.page_number)
                if crop_bytes is None:
                    continue
                storage_path = f"diagrams/{qid}.png"
                sb.storage.from_("diagrams").upload(
                    storage_path, crop_bytes, {"content-type": "image/png"}
                )
                public_url = sb.storage.from_("diagrams").get_public_url(storage_path)
                sb.table("questions").update({"diagram_url": public_url}).eq("id", qid).execute()
                log(f"Diagram saved for question {qid}")
            except Exception as e:
                log(f"Diagram upload failed for {qid}: {e}", "WARN")

    # Update site counter
    if new_count > 0:
        _increment_counter(sb, "total_questions", new_count)

    log(f"Done: {new_count} new, {updated_count} updated, {n_clusters} clusters | subject={eff_subject}")
    return {
        "questions_extracted": len(extracted),
        "new_questions": new_count,
        "updated_questions": updated_count,
        "clusters_formed": n_clusters,
        "paper_metadata": {
            "subject": eff_subject,
            "subject_code": eff_code,
            "branch": eff_branch,
            "semester": eff_semester,
            "year": eff_year,
            "programme": eff_programme,
            "exam_session": eff_session,
        }
    }


# ── Admin API Endpoints ────────────────────────────────────────────────────────

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
    exam_session: str = Form(""),
    subject_code: str = Form(""),
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files accepted.")

    pdf_bytes = await file.read()
    file_hash = compute_file_hash(pdf_bytes)
    sb = get_supabase()

    existing = sb.table("pdf_submissions").select("id,status").eq("file_hash", file_hash).execute()
    if existing.data and existing.data[0].get("status") == "approved":
        raise HTTPException(409, "Duplicate: this paper is already processed.")

    log(f"Admin upload: {file.filename} | {subject} | {year}")
    year_int = int(year) if year.isdigit() else None
    semester_int = int(semester) if semester.isdigit() else None

    result = await process_and_insert(
        pdf_bytes, subject, year_int, semester_int, branch, university,
        programme or None, exam_session or None, subject_code or None,
        request.app.state.embedder, sb,
    )

    # Upsert submission record
    sub_record = {
        "filename": file.filename, "file_hash": file_hash,
        "university": university or "AKTU",
        "subject": result["paper_metadata"]["subject"] or None,
        "subject_code": result["paper_metadata"]["subject_code"] or None,
        "branch": result["paper_metadata"]["branch"] or None,
        "programme": result["paper_metadata"]["programme"] or None,
        "semester": result["paper_metadata"]["semester"],
        "year": result["paper_metadata"]["year"],
        "exam_session": result["paper_metadata"]["exam_session"] or None,
        "submitted_by": "admin", "status": "approved",
    }
    if existing.data:
        sb.table("pdf_submissions").update(sub_record).eq("id", existing.data[0]["id"]).execute()
    else:
        sb.table("pdf_submissions").insert(sub_record).execute()
        _increment_counter(sb, "total_papers")

    return result


@router.post("/metadata/extract")
async def extract_metadata_preview(
    file: UploadFile = File(...),
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """
    Lightweight endpoint: reads only the paper header metadata.
    Used by admin upload form to auto-populate fields before full processing.
    """
    verify_admin(_safe_get_token(x_admin_token, authorization))
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files accepted.")
    pdf_bytes = await file.read()
    from services.pdf_processor import extract_paper_metadata
    meta = extract_paper_metadata(pdf_bytes)
    return {
        "programme": meta.programme,
        "subject_name": meta.subject_name,
        "subject_code": meta.subject_code,
        "branch": meta.branch,
        "semester": meta.semester,
        "year": meta.year,
        "exam_session": meta.exam_session,
    }


@router.get("/submissions")
async def get_submissions(
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    return get_supabase().table("pdf_submissions").select("*").order("created_at", desc=True).limit(200).execute().data


@router.post("/submissions/{sid}/approve")
async def approve_submission(
    sid: int, request: Request,
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
        pdf_bytes = sb.storage.from_("pdf-uploads").download(f"submissions/{row['file_hash']}.pdf")
        await process_and_insert(
            pdf_bytes,
            row.get("subject", ""), row.get("year"), row.get("semester"),
            row.get("branch", ""), row.get("university", "AKTU"),
            row.get("programme"), row.get("exam_session"), row.get("subject_code"),
            request.app.state.embedder, sb,
        )
        log(f"Submission {sid} approved and processed")
    except Exception as e:
        log(f"Approval failed for {sid}: {e}", "WARN")
        raise HTTPException(500, f"Processing failed: {str(e)}")
    sb.table("pdf_submissions").update({"status": "approved"}).eq("id", sid).execute()
    _increment_counter(sb, "total_papers")
    return {"ok": True}


@router.post("/submissions/{sid}/reject")
async def reject_submission(
    sid: int,
    reason: str = Form(""),
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    get_supabase().table("pdf_submissions").update({
        "status": "rejected",
        "rejection_reason": reason or None,
    }).eq("id", sid).execute()
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
    approved = sb.table("pdf_submissions").select("id", count="exact").eq("status", "approved").execute().count or 0
    subjects_data = sb.table("questions").select("subject").execute()
    unique_subjects = len(set(r["subject"] for r in subjects_data.data if r.get("subject")))
    total_clusters = sb.table("clusters").select("id", count="exact").execute().count or 0
    scrape_pending = sb.table("scrape_queue").select("id", count="exact").eq("status", "pending").execute().count or 0
    scrape_done = sb.table("scrape_queue").select("id", count="exact").eq("status", "done").execute().count or 0
    scrape_failed = sb.table("scrape_queue").select("id", count="exact").eq("status", "failed").execute().count or 0

    # Analytics counters
    counters = {r["key"]: r["value"] for r in (sb.table("site_counters").select("*").execute().data or [])}

    ocr_errs = sum(1 for l in LOG_BUFFER if "ERROR" in l and "OCR" in l)
    return {
        "total_questions": total_q,
        "total_clusters": total_clusters,
        "total_subjects": unique_subjects,
        "total_pdfs_processed": total_subs,
        "approved_papers": approved,
        "pending_submissions": pending,
        "scrape_pending": scrape_pending,
        "scrape_done": scrape_done,
        "scrape_failed": scrape_failed,
        "ocr_errors_today": ocr_errs,
        "site_counters": counters,
        "last_processed": datetime.now().isoformat(),
    }


@router.get("/logs")
async def get_logs(
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    return {"logs": list(reversed(LOG_BUFFER))}


# ── Scrape Queue ───────────────────────────────────────────────────────────────

@router.post("/scrape/feed")
async def feed_scrape_queue(
    request: Request,
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """
    Accepts JSON: {"lines": ["btech-1-sem-nec101-2022", ...]}
    Auto-prepends https://www.aktuonline.com/papers/ and appends .pdf
    Validates with HEAD request. Inserts valid URLs into scrape_queue.
    """
    verify_admin(_safe_get_token(x_admin_token, authorization))
    body = await request.json()
    lines: List[str] = body.get("lines", [])

    BASE = "https://www.aktuonline.com/papers/"
    sb = get_supabase()
    valid, not_found, already_queued = 0, 0, 0

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                url = BASE + line + ".pdf"
                try:
                    head = await client.head(url)
                    if head.status_code == 200:
                        try:
                            sb.table("scrape_queue").insert({"pdf_url": url}).execute()
                            valid += 1
                        except Exception:
                            already_queued += 1
                    else:
                        not_found += 1
                except Exception:
                    not_found += 1
    except ImportError:
        raise HTTPException(500, "httpx not installed on server.")

    log(f"Scrape feed: {valid} queued, {not_found} not found, {already_queued} already queued")
    return {"queued": valid, "not_found": not_found, "already_queued": already_queued}


@router.post("/scrape/run")
async def run_scraper_batch(
    request: Request,
    batch_size: int = 10,
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Pick up to batch_size pending items from scrape_queue and process each."""
    verify_admin(_safe_get_token(x_admin_token, authorization))
    sb = get_supabase()

    pending = sb.table("scrape_queue").select("*").eq("status", "pending").limit(batch_size).execute().data
    if not pending:
        return {"processed": 0, "message": "No pending items in scrape queue."}

    results = []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            for item in pending:
                sb.table("scrape_queue").update({"status": "processing"}).eq("id", item["id"]).execute()
                try:
                    resp = await client.get(item["pdf_url"])
                    if resp.status_code != 200:
                        raise ValueError(f"HTTP {resp.status_code}")
                    pdf_bytes = resp.content
                    proc = await process_and_insert(
                        pdf_bytes,
                        item.get("subject", ""),
                        item.get("year"),
                        item.get("semester"),
                        item.get("branch", ""),
                        "AKTU",
                        item.get("programme"),
                        item.get("exam_session"),
                        item.get("subject_code"),
                        request.app.state.embedder, sb,
                    )
                    sb.table("scrape_queue").update({
                        "status": "done",
                        "questions_extracted": proc["questions_extracted"],
                        "processed_at": datetime.now().isoformat(),
                    }).eq("id", item["id"]).execute()
                    _increment_counter(sb, "total_papers")
                    results.append({"url": item["pdf_url"], "status": "done", **proc})
                except Exception as e:
                    err = str(e)[:300]
                    sb.table("scrape_queue").update({
                        "status": "failed",
                        "error_message": err,
                        "processed_at": datetime.now().isoformat(),
                    }).eq("id", item["id"]).execute()
                    log(f"Scrape failed: {item['pdf_url']} — {err}", "WARN")
                    results.append({"url": item["pdf_url"], "status": "failed", "error": err})
    except ImportError:
        raise HTTPException(500, "httpx not installed.")

    return {"processed": len(results), "results": results}


@router.get("/scrape/status")
async def scrape_status(
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    sb = get_supabase()
    recent = sb.table("scrape_queue").select("*").order("created_at", desc=True).limit(50).execute().data
    pending = sum(1 for r in recent if r["status"] == "pending")
    processing = sum(1 for r in recent if r["status"] == "processing")
    done = sum(1 for r in recent if r["status"] == "done")
    failed = sum(1 for r in recent if r["status"] == "failed")
    return {"pending": pending, "processing": processing, "done": done, "failed": failed, "recent": recent}


# ── Analytics ──────────────────────────────────────────────────────────────────

@router.post("/analytics/event")
async def track_event(request: Request):
    """Internal endpoint — called by frontend middleware for page views, searches, etc."""
    try:
        body = await request.json()
        sb = get_supabase()
        sb.table("analytics_events").insert({
            "event_type": body.get("event_type", "unknown"),
            "page": body.get("page"),
            "metadata": body.get("metadata", {}),
            "session_id": body.get("session_id"),
        }).execute()
        if body.get("event_type") == "page_view":
            _increment_counter(sb, "total_visitors")
        elif body.get("event_type") == "search":
            _increment_counter(sb, "total_searches")
        elif body.get("event_type") == "contribute":
            _increment_counter(sb, "total_contributors")
    except Exception as e:
        logger.warning(f"Analytics event failed: {e}")
    return {"ok": True}


@router.get("/analytics/summary")
async def analytics_summary(
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    sb = get_supabase()
    counters = {r["key"]: r["value"] for r in (sb.table("site_counters").select("*").execute().data or [])}

    # Monthly breakdown from analytics_events
    monthly = {}
    try:
        rows = sb.table("analytics_events").select("event_type,created_at").eq("event_type", "page_view").execute().data or []
        for row in rows:
            month = row["created_at"][:7]  # YYYY-MM
            monthly[month] = monthly.get(month, 0) + 1
    except Exception:
        pass

    return {"counters": counters, "monthly_visitors": monthly}


# ── Question management ────────────────────────────────────────────────────────

@router.post("/questions/{qid}/confirm-appeared")
async def confirm_appeared_in_exam(qid: int, request: Request):
    """Student clicks 'this appeared in my exam' — increments user_confirmed_count."""
    try:
        sb = get_supabase()
        row = sb.table("questions").select("user_confirmed_count").eq("id", qid).execute()
        if not row.data:
            raise HTTPException(404, "Question not found.")
        new_val = (row.data[0]["user_confirmed_count"] or 0) + 1
        sb.table("questions").update({"user_confirmed_count": new_val}).eq("id", qid).execute()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"ok": True}


# ── Maintenance endpoints ──────────────────────────────────────────────────────

@router.post("/rebuild-index")
async def rebuild_index(x_admin_token: Optional[str] = Header(None), authorization: Optional[str] = Header(None)):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    return {"ok": True, "message": "rebuild-index: not yet implemented"}


@router.post("/recalculate")
async def recalculate_scores(
    request: Request,
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Recalculate importance_score + must_revise_flag for all questions."""
    verify_admin(_safe_get_token(x_admin_token, authorization))
    sb = get_supabase()
    questions = sb.table("questions").select("id,frequency_count,year_appeared,trend_direction,last_appearance_year").execute().data or []
    max_freq = max((q.get("frequency_count") or 1) for q in questions) if questions else 1
    updated = 0
    for q in questions:
        freq = q.get("frequency_count") or 1
        years = q.get("year_appeared") or []
        trend = detect_trend(years) if years else "insufficient_data"
        last_year = q.get("last_appearance_year") or datetime.now().year
        score = compute_importance_score(freq, max_freq, trend, last_year)
        sb.table("questions").update({
            "importance_score": score,
            "trend_direction": trend,
            "must_revise_flag": score >= 0.75,
        }).eq("id", q["id"]).execute()
        updated += 1
    log(f"Recalculated scores for {updated} questions")
    return {"ok": True, "updated": updated}


@router.post("/recluster")
async def recluster_all(x_admin_token: Optional[str] = Header(None), authorization: Optional[str] = Header(None)):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    return {"ok": True, "message": "recluster: not yet implemented"}


@router.post("/export")
async def export_database(x_admin_token: Optional[str] = Header(None), authorization: Optional[str] = Header(None)):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    sb = get_supabase()
    return {
        "ok": True,
        "export": {
            "questions": sb.table("questions").select("*").execute().data,
            "pdf_submissions": sb.table("pdf_submissions").select("*").execute().data,
            "clusters": sb.table("clusters").select("*").execute().data,
            "scrape_queue": sb.table("scrape_queue").select("*").execute().data,
        },
    }


@router.delete("/submissions/pending")
async def clear_pending_submissions(x_admin_token: Optional[str] = Header(None), authorization: Optional[str] = Header(None)):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    get_supabase().table("pdf_submissions").delete().eq("status", "pending").execute()
    return {"ok": True}
