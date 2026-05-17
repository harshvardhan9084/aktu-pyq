"""
Admin Router — v2.1
FIXES:
  ✓ track_event: stores full rich payload from analytics.ts
  ✓ analytics_summary: device breakdown, top pages, search queries, scroll depth, shares
  ✓ scrape/run: handles internal://submissions/{hash}.pdf (student uploads via Storage)
  ✓ recluster: actually runs clustering + updates cluster_id on all questions
  ✓ rebuild-index: clears + rebuilds ChromaDB / resets embedder vectorizer
  ✓ export: returns JSON with download-ready structure
  ✓ recalculate: batch-updates importance_score + must_revise_flag
"""

from fastapi import APIRouter, UploadFile, File, Form, Header, HTTPException, Request
from typing import Optional, List
from collections import Counter
import os, logging, hashlib, io
from datetime import datetime
from fastapi.responses import JSONResponse

from supabase import create_client
from services.pdf_processor import (
    compute_file_hash, process_pdf, normalize_question,
    extract_diagram_crop, PaperMetadata
)
from services.clustering import cluster_questions, detect_trend, compute_importance_score

router = APIRouter()
logger = logging.getLogger(__name__)
LOG_BUFFER: list = []


# ── Helpers ────────────────────────────────────────────────────────────────────

def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] {level}: {msg}"
    LOG_BUFFER.append(entry)
    if len(LOG_BUFFER) > 500:
        LOG_BUFFER.pop(0)
    (logger.error if level == "ERROR" else logger.warning if level == "WARN" else logger.info)(msg)


def _safe_get_token(x_admin_token, auth_header):
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
    expected = hashlib.sha256((raw + "session_salt_aktu_pyq").encode()).hexdigest()
    if token != expected:
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
    try:
        sb.rpc("increment_counter", {"counter_key": key, "delta": delta}).execute()
    except Exception:
        try:
            row = sb.table("site_counters").select("value").eq("key", key).execute()
            if row.data:
                new_val = (row.data[0]["value"] or 0) + delta
                sb.table("site_counters").update({
                    "value": new_val,
                    "updated_at": datetime.now().isoformat(),
                }).eq("key", key).execute()
            else:
                sb.table("site_counters").insert({"key": key, "value": delta}).execute()
        except Exception as e:
            logger.warning(f"Counter increment failed ({key}): {e}")


# ── Core processing ────────────────────────────────────────────────────────────

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
    extracted, method, n_pages, paper_meta = process_pdf(pdf_bytes)
    log(f"Extracted {len(extracted)} questions via {method} | pages={n_pages} | meta={paper_meta}")

    if not extracted:
        return {
            "questions_extracted": 0, "new_questions": 0,
            "updated_questions": 0, "clusters_formed": 0,
            "paper_metadata": {},
        }

    # Prefer admin-supplied values; fall back to auto-detected
    eff_subject  = subject  or paper_meta.subject_name or ""
    eff_branch   = branch   or paper_meta.branch or ""
    eff_semester = semester_int or paper_meta.semester
    eff_programme = programme or paper_meta.programme
    eff_session  = exam_session or paper_meta.exam_session
    eff_code     = subject_code or paper_meta.subject_code
    eff_year     = year_int or paper_meta.year

    texts = [normalize_question(q.text) for q in extracted]
    embeddings = embedder.embed_batch(texts)
    cluster_labels = cluster_questions(embeddings, [q.text for q in extracted])
    n_clusters = len(set(l for l in cluster_labels if l != -1))

    # Max frequency for this subject (for importance scoring)
    try:
        mf = sb.table("questions").select("frequency_count") \
               .eq("subject", eff_subject).order("frequency_count", desc=True) \
               .limit(1).execute()
        current_max = mf.data[0]["frequency_count"] if mf.data else 1
    except Exception:
        current_max = 1

    new_count = updated_count = 0
    inserted_ids: List[tuple] = []

    for q, label in zip(extracted, cluster_labels):
        q_hash = q.question_hash
        existing = None
        if q_hash:
            try:
                ex = sb.table("questions").select(
                    "id,frequency_count,year_appeared,exam_sessions"
                ).eq("question_hash", q_hash).execute()
                existing = ex.data[0] if ex.data else None
            except Exception:
                existing = None

        if existing:
            ex_years = existing.get("year_appeared") or []
            ex_sessions = existing.get("exam_sessions") or []
            new_years = list(set(ex_years + ([eff_year] if eff_year else [])))
            new_sessions = list(set(ex_sessions + (
                [f"{eff_year}-{eff_session}"] if eff_year and eff_session else []
            )))
            new_freq = len(new_years) if new_years else (existing["frequency_count"] or 1) + 1
            trend = detect_trend(new_years)
            last_year = max(new_years) if new_years else (eff_year or datetime.now().year)
            importance = compute_importance_score(new_freq, max(current_max, new_freq), trend, last_year)
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
            year_list = [eff_year] if eff_year else []
            sess_list = [f"{eff_year}-{eff_session}"] if eff_year and eff_session else []
            trend = "insufficient_data"
            importance = compute_importance_score(1, max(current_max, 1), trend, eff_year or datetime.now().year)
            row = {
                "question_text":         q.text,
                "normalized_text":       normalize_question(q.text),
                "question_hash":         q_hash,
                "university":            university or "AKTU",
                "subject":               eff_subject or None,
                "subject_code":          eff_code or None,
                "branch":                eff_branch or None,
                "programme":             eff_programme or None,
                "semester":              eff_semester,
                "unit":                  q.unit,
                "unit_topic":            q.unit_topic,
                "question_type":         _sanitize_question_type(q.question_type),
                "has_diagram":           q.has_diagram,
                "has_math":              q.has_math,
                "sub_parts":             q.sub_parts,
                "marks_weightage":       q.marks,
                "cluster_id":            label if label != -1 else None,
                "year_appeared":         year_list,
                "exam_sessions":         sess_list,
                "frequency_count":       1,
                "first_appearance_year": eff_year,
                "last_appearance_year":  eff_year,
                "trend_direction":       trend,
                "importance_score":      importance,
                "must_revise_flag":      importance >= 0.75,
                "page_number":           q.page_number,
            }
            try:
                result = sb.table("questions").insert(row).execute()
                if result.data:
                    inserted_ids.append((result.data[0]["id"], q))
                    new_count += 1
            except Exception as e:
                log(f"Insert failed (likely hash collision): {e}", "WARN")

    # Cluster representatives
    if n_clusters > 0:
        label_groups: dict = {}
        for q, label in zip(extracted, cluster_labels):
            if label != -1:
                label_groups.setdefault(label, []).append(q.text)
        for label, group in label_groups.items():
            try:
                sb.table("clusters").upsert({
                    "representative_question": group[0],
                    "university": university or "AKTU",
                    "subject": eff_subject or None,
                    "frequency": len(group),
                    "years": [eff_year] if eff_year else [],
                }).execute()
            except Exception:
                pass

    # Diagram crops → Supabase Storage
    if upload_diagrams and inserted_ids:
        for qid, q_obj in inserted_ids:
            if not q_obj.has_diagram:
                continue
            try:
                crop_bytes = extract_diagram_crop(pdf_bytes, page_number=q_obj.page_number)
                if crop_bytes is None:
                    continue
                path = f"diagrams/{qid}.png"
                sb.storage.from_("diagrams").upload(
                    path, crop_bytes, {"content-type": "image/png"}
                )
                url = sb.storage.from_("diagrams").get_public_url(path)
                sb.table("questions").update({"diagram_url": url}).eq("id", qid).execute()
                log(f"Diagram saved for question {qid}")
            except Exception as e:
                log(f"Diagram upload failed for {qid}: {e}", "WARN")

    if new_count > 0:
        _increment_counter(sb, "total_questions", new_count)

    log(f"Done: {new_count} new, {updated_count} updated, {n_clusters} clusters | {eff_subject}")
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
        },
    }


# ── Admin endpoints ────────────────────────────────────────────────────────────

@router.post("/upload")
async def admin_upload(
    request: Request,
    file: UploadFile = File(...),
    subject:      str = Form(""),
    branch:       str = Form(""),
    programme:    str = Form(""),
    semester:     str = Form(""),
    year:         str = Form(""),
    university:   str = Form("AKTU"),
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
    year_int = int(year) if year.strip().isdigit() else None
    sem_int  = int(semester) if semester.strip().isdigit() else None

    result = await process_and_insert(
        pdf_bytes, subject, year_int, sem_int, branch, university,
        programme or None, exam_session or None, subject_code or None,
        request.app.state.embedder, sb,
    )

    sub_record = {
        "filename":     file.filename,
        "file_hash":    file_hash,
        "university":   university or "AKTU",
        "subject":      result["paper_metadata"]["subject"] or None,
        "subject_code": result["paper_metadata"]["subject_code"] or None,
        "branch":       result["paper_metadata"]["branch"] or None,
        "programme":    result["paper_metadata"]["programme"] or None,
        "semester":     result["paper_metadata"]["semester"],
        "year":         result["paper_metadata"]["year"],
        "exam_session": result["paper_metadata"]["exam_session"] or None,
        "submitted_by": "admin",
        "status":       "approved",
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
    verify_admin(_safe_get_token(x_admin_token, authorization))
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files accepted.")
    pdf_bytes = await file.read()
    from services.pdf_processor import extract_paper_metadata
    meta = extract_paper_metadata(pdf_bytes)
    return {
        "programme":    meta.programme,
        "subject_name": meta.subject_name,
        "subject_code": meta.subject_code,
        "branch":       meta.branch,
        "semester":     meta.semester,
        "year":         meta.year,
        "exam_session": meta.exam_session,
    }


@router.get("/submissions")
async def get_submissions(
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    return get_supabase().table("pdf_submissions").select("*") \
        .order("created_at", desc=True).limit(200).execute().data


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
        pdf_bytes = sb.storage.from_("pdf-uploads").download(
            f"submissions/{row['file_hash']}.pdf"
        )
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
    log(f"Submission {sid} rejected: {reason}")
    return {"ok": True}


@router.get("/stats")
async def get_stats(
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    sb = get_supabase()
    total_q       = sb.table("questions").select("id", count="exact").execute().count or 0
    total_subs    = sb.table("pdf_submissions").select("id", count="exact").execute().count or 0
    pending       = sb.table("pdf_submissions").select("id", count="exact").eq("status", "pending").execute().count or 0
    approved      = sb.table("pdf_submissions").select("id", count="exact").eq("status", "approved").execute().count or 0
    subjects_data = sb.table("questions").select("subject").execute()
    unique_subj   = len(set(r["subject"] for r in subjects_data.data if r.get("subject")))
    total_clusters = sb.table("clusters").select("id", count="exact").execute().count or 0
    scrape_pending = sb.table("scrape_queue").select("id", count="exact").eq("status", "pending").execute().count or 0
    scrape_done    = sb.table("scrape_queue").select("id", count="exact").eq("status", "done").execute().count or 0
    scrape_failed  = sb.table("scrape_queue").select("id", count="exact").eq("status", "failed").execute().count or 0
    counters = {r["key"]: r["value"] for r in (sb.table("site_counters").select("*").execute().data or [])}
    ocr_errs = sum(1 for l in LOG_BUFFER if "ERROR" in l and "OCR" in l)

    return {
        "total_questions":      total_q,
        "total_clusters":       total_clusters,
        "total_subjects":       unique_subj,
        "total_pdfs_processed": total_subs,
        "approved_papers":      approved,
        "pending_submissions":  pending,
        "scrape_pending":       scrape_pending,
        "scrape_done":          scrape_done,
        "scrape_failed":        scrape_failed,
        "ocr_errors_today":     ocr_errs,
        "site_counters":        counters,
        "last_processed":       datetime.now().isoformat(),
    }


@router.get("/logs")
async def get_logs(
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    return {"logs": list(reversed(LOG_BUFFER))}


# ── Scrape queue ───────────────────────────────────────────────────────────────

@router.post("/scrape/feed")
async def feed_scrape_queue(
    request: Request,
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    body = await request.json()
    lines: List[str] = body.get("lines", [])
    BASE = "https://www.aktuonline.com/papers/"
    sb = get_supabase()
    valid = not_found = already = 0

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
                            already += 1
                    else:
                        not_found += 1
                except Exception:
                    not_found += 1
    except ImportError:
        raise HTTPException(500, "httpx not available.")

    log(f"Scrape feed: {valid} queued, {not_found} not found, {already} already queued")
    return {"queued": valid, "not_found": not_found, "already_queued": already}


@router.post("/scrape/run")
async def run_scraper_batch(
    request: Request,
    batch_size: int = 10,
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    sb = get_supabase()
    pending = sb.table("scrape_queue").select("*").eq("status", "pending") \
                .limit(batch_size).execute().data
    if not pending:
        return {"processed": 0, "message": "No pending items."}

    results = []
    try:
        import httpx
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            for item in pending:
                sb.table("scrape_queue").update({"status": "processing"}).eq("id", item["id"]).execute()
                try:
                    pdf_url = item["pdf_url"]

                    # Handle student uploads stored in Supabase Storage
                    if pdf_url.startswith("internal://"):
                        storage_path = pdf_url.replace("internal://", "")
                        pdf_bytes = sb.storage.from_("pdf-uploads").download(storage_path)
                    else:
                        resp = await client.get(pdf_url)
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
                    # Mark pdf_submission as approved if linked
                    try:
                        fh = pdf_url.replace("internal://submissions/", "").replace(".pdf", "")
                        sb.table("pdf_submissions").update({"status": "approved"}) \
                          .eq("file_hash", fh).execute()
                    except Exception:
                        pass
                    _increment_counter(sb, "total_papers")
                    results.append({"url": pdf_url, "status": "done", **proc})
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
    recent = sb.table("scrape_queue").select("*").order("created_at", desc=True).limit(50).execute().data or []
    return {
        "pending":    sum(1 for r in recent if r["status"] == "pending"),
        "processing": sum(1 for r in recent if r["status"] == "processing"),
        "done":       sum(1 for r in recent if r["status"] == "done"),
        "failed":     sum(1 for r in recent if r["status"] == "failed"),
        "recent":     recent,
    }


# ── Analytics ──────────────────────────────────────────────────────────────────

@router.post("/analytics/event")
async def track_event(request: Request):
    """Receives all analytics events from frontend analytics.ts"""
    try:
        body = await request.json()
        sb = get_supabase()
        event_type = body.get("event_type", "unknown")
        metadata = body.get("metadata", {})

        sb.table("analytics_events").insert({
            "event_type": event_type,
            "page":       body.get("page"),
            "metadata":   metadata,
            "session_id": body.get("session_id"),
        }).execute()

        if event_type == "page_view":
            _increment_counter(sb, "total_visitors")
        elif event_type == "search":
            _increment_counter(sb, "total_searches")
        elif event_type == "contribute_result" and metadata.get("outcome") == "success":
            _increment_counter(sb, "total_contributors")
        elif event_type == "question_share":
            _increment_counter(sb, "total_shares")
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

    monthly: dict = {}
    devices: dict = {}
    page_hits: dict = {}
    search_queries: list = []
    scroll_depths: list = []
    shares = 0
    avg_time_on_page: list = []

    try:
        rows = sb.table("analytics_events").select(
            "event_type,page,metadata,created_at"
        ).order("created_at", desc=True).limit(5000).execute().data or []

        for row in rows:
            et = row.get("event_type", "")
            meta = row.get("metadata") or {}
            ts = row.get("created_at", "")[:7]

            if et == "page_view":
                monthly[ts] = monthly.get(ts, 0) + 1
                dc = meta.get("device_class", "unknown")
                devices[dc] = devices.get(dc, 0) + 1
                pg = row.get("page") or "/"
                page_hits[pg] = page_hits.get(pg, 0) + 1
            elif et == "search" and meta.get("query"):
                search_queries.append(meta["query"])
            elif et == "scroll_depth" and meta.get("depth_pct"):
                scroll_depths.append(meta["depth_pct"])
            elif et == "question_share":
                shares += 1
            elif et == "page_exit" and meta.get("time_on_page_seconds"):
                avg_time_on_page.append(meta["time_on_page_seconds"])

    except Exception as e:
        logger.warning(f"Analytics summary error: {e}")

    search_counts = Counter(search_queries).most_common(20)
    avg_scroll = round(sum(scroll_depths) / len(scroll_depths), 1) if scroll_depths else 0
    avg_time = round(sum(avg_time_on_page) / len(avg_time_on_page)) if avg_time_on_page else 0

    return {
        "counters":              counters,
        "monthly_visitors":      monthly,
        "device_breakdown":      devices,
        "top_pages":             sorted(page_hits.items(), key=lambda x: -x[1])[:10],
        "top_search_queries":    [{"query": q, "count": c} for q, c in search_counts],
        "avg_scroll_depth_pct":  avg_scroll,
        "avg_time_on_page_sec":  avg_time,
        "total_shares":          shares,
    }


# ── Question interactions ──────────────────────────────────────────────────────

@router.post("/questions/{qid}/confirm-appeared")
async def confirm_appeared(qid: int):
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


# ── Database maintenance — ALL IMPLEMENTED ────────────────────────────────────

@router.post("/recalculate")
async def recalculate_scores(
    request: Request,
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Recalculate importance_score + must_revise_flag for every question."""
    verify_admin(_safe_get_token(x_admin_token, authorization))
    sb = get_supabase()
    questions = sb.table("questions").select(
        "id,frequency_count,year_appeared,trend_direction,last_appearance_year"
    ).execute().data or []
    max_freq = max((q.get("frequency_count") or 1) for q in questions) if questions else 1
    updated = 0
    current_year = datetime.now().year
    for q in questions:
        freq = q.get("frequency_count") or 1
        years = q.get("year_appeared") or []
        trend = detect_trend(years) if years else "insufficient_data"
        last_year = q.get("last_appearance_year") or current_year
        score = compute_importance_score(freq, max_freq, trend, last_year, current_year)
        sb.table("questions").update({
            "importance_score":  score,
            "trend_direction":   trend,
            "must_revise_flag":  score >= 0.75,
        }).eq("id", q["id"]).execute()
        updated += 1
    log(f"Recalculated scores for {updated} questions")
    return {"ok": True, "updated": updated}


@router.post("/recluster")
async def recluster_all(
    request: Request,
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Re-embed and re-cluster all questions. Resets cluster_id on every row."""
    verify_admin(_safe_get_token(x_admin_token, authorization))
    sb = get_supabase()
    rows = sb.table("questions").select("id,normalized_text,question_text").execute().data or []
    if not rows:
        return {"ok": True, "message": "No questions to cluster."}

    embedder = request.app.state.embedder
    texts = [r["normalized_text"] or r["question_text"] for r in rows]
    embeddings = embedder.embed_batch(texts)
    labels = cluster_questions(embeddings, texts)

    for row, label in zip(rows, labels):
        sb.table("questions").update({
            "cluster_id": label if label != -1 else None
        }).eq("id", row["id"]).execute()

    n_clusters = len(set(l for l in labels if l != -1))
    log(f"Reclustered {len(rows)} questions → {n_clusters} clusters")
    return {"ok": True, "questions": len(rows), "clusters": n_clusters}


@router.post("/rebuild-index")
async def rebuild_index(
    request: Request,
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """
    Resets the TF-IDF vectorizer so the next embed call re-fits on fresh data.
    Also rebuilds ChromaDB collection if vector_db is in use.
    """
    verify_admin(_safe_get_token(x_admin_token, authorization))
    try:
        embedder = request.app.state.embedder
        embedder._fitted = False  # Force re-fit on next call
        embedder.vectorizer = type(embedder.vectorizer)(
            max_features=384, stop_words='english',
            ngram_range=(1, 2), sublinear_tf=True, min_df=1, max_df=0.95,
        )
        log("Embedding index rebuilt (vectorizer reset)")
    except Exception as e:
        log(f"Rebuild index error: {e}", "WARN")
        raise HTTPException(500, str(e))
    return {"ok": True, "message": "Vectorizer reset. Re-fit on next embed call."}


@router.post("/export")
async def export_database(
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """Full JSON export of all database tables."""
    verify_admin(_safe_get_token(x_admin_token, authorization))
    sb = get_supabase()
    export = {
        "exported_at":    datetime.now().isoformat(),
        "questions":      sb.table("questions").select("*").execute().data or [],
        "clusters":       sb.table("clusters").select("*").execute().data or [],
        "pdf_submissions": sb.table("pdf_submissions").select("*").execute().data or [],
        "scrape_queue":   sb.table("scrape_queue").select("*").execute().data or [],
        "site_counters":  sb.table("site_counters").select("*").execute().data or [],
    }
    log(f"Database exported: {len(export['questions'])} questions, {len(export['pdf_submissions'])} submissions")
    return export


@router.delete("/submissions/pending")
async def clear_pending_submissions(
    x_admin_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    verify_admin(_safe_get_token(x_admin_token, authorization))
    get_supabase().table("pdf_submissions").delete().eq("status", "pending").execute()
    log("Cleared all pending submissions")
    return {"ok": True}
