"""Upload Router — student PDF submissions with duplicate detection"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
import os, logging
from supabase import create_client
from services.pdf_processor import compute_file_hash

router = APIRouter()
logger = logging.getLogger(__name__)
MAX_FILE_SIZE = 20 * 1024 * 1024

def get_supabase():
    return create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))


@router.post("/pdf")
async def submit_pdf(
    file: UploadFile = File(...),
    subject: Optional[str] = Form(None),
    semester: Optional[str] = Form(None),
    year: Optional[str] = Form(None),
    submitted_by: str = Form("anonymous"),
):
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
        "subject": subject,
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

    logger.info(f"New submission: {file.filename} from {submitted_by}")
    return {"message": "Submitted successfully. An admin will review your paper.", "id": result.data[0]["id"]}
