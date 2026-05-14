"""Upload Router — student PDF submissions with duplicate detection
Supports multi-university submissions."""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from typing import Optional
import os, logging, time
from supabase import create_client
from services.pdf_processor import compute_file_hash

router = APIRouter()
logger = logging.getLogger(__name__)
MAX_FILE_SIZE = 20 * 1024 * 1024

# Simple in-memory rate limiter: IP -> [timestamps]
_upload_attempts: dict = {}
RATE_LIMIT_WINDOW = 60   # seconds
RATE_LIMIT_MAX = 5       # max uploads per window per IP


def _check_rate_limit(client_ip: str) -> bool:
    """Returns True if the client is rate-limited."""
    now = time.time()
    if client_ip not in _upload_attempts:
        _upload_attempts[client_ip] = []
    # Prune old entries
    _upload_attempts[client_ip] = [t for t in _upload_attempts[client_ip] if now - t < RATE_LIMIT_WINDOW]
    if len(_upload_attempts[client_ip]) >= RATE_LIMIT_MAX:
        return True
    _upload_attempts[client_ip].append(now)
    return False


_supabase_client = None


def get_supabase():
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))
    return _supabase_client


@router.post("/pdf")
async def submit_pdf(
    request: Request,
    file: UploadFile = File(...),
    subject: Optional[str] = Form(None),
    branch: Optional[str] = Form(None),
    programme: Optional[str] = Form(None),
    semester: Optional[str] = Form(None),
    year: Optional[str] = Form(None),
    university: Optional[str] = Form("AKTU"),
    submitted_by: str = Form("anonymous"),
):
    # Rate limiting by client IP
    client_ip = request.client.host if request.client else "unknown"
    if _check_rate_limit(client_ip):
        raise HTTPException(429, "Too many uploads. Please wait a minute before trying again.")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")

    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large. Maximum size is 20MB.")

    file_hash = compute_file_hash(pdf_bytes)
    sb = get_supabase()

    existing = sb.table("pdf_submissions").select("id").eq("file_hash", file_hash).execute()
    if existing.data:
        raise HTTPException(409, "This paper is already in our database.")

    record = {
        "filename": file.filename,
        "file_hash": file_hash,
        "university": university or "AKTU",
        "subject": subject,
        "branch": branch,
        "programme": programme,
        "semester": int(semester) if semester and semester.isdigit() else None,
        "year": int(year) if year and year.isdigit() else None,
        "submitted_by": submitted_by[:100],
        "status": "pending",
    }
    result = sb.table("pdf_submissions").insert(record).execute()

    try:
        sb.storage.from_("pdf-uploads").upload(f"submissions/{file_hash}.pdf", pdf_bytes)
    except Exception as e:
        logger.warning(f"Storage upload failed: {e}")

    logger.info(f"New submission: {file.filename} from {submitted_by} [{university}]")
    return {"message": "Submitted successfully. An admin will review your paper.", "id": result.data[0]["id"]}
