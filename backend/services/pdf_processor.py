"""
PDF Processing Service
Uses pypdf (pure Python, zero compilation) for text extraction.
OCR via pytesseract — gracefully skipped if tesseract binary not installed.
"""

import hashlib
import re
import logging
from typing import List, Tuple

from pypdf import PdfReader
import io

logger = logging.getLogger(__name__)

NOISE_PATTERNS = [
    r"(?i)note\s*:", r"(?i)all questions are compulsory",
    r"(?i)attempt any \w+", r"(?i)maximum marks",
    r"(?i)time allowed", r"(?i)roll no",
    r"(?i)examination\s+\d{4}", r"\[\d+\]", r"\(\d+ marks?\)",
]
NOISE_RE = re.compile("|".join(NOISE_PATTERNS), re.IGNORECASE)


def compute_file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def extract_text_digital(pdf_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        parts = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(parts)
    except Exception as e:
        logger.warning(f"pypdf extraction failed: {e}")
        return ""


def extract_text_ocr(pdf_bytes: bytes) -> str:
    try:
        import pdf2image
        import pytesseract
        images = pdf2image.convert_from_bytes(pdf_bytes, dpi=200)
        return "\n".join(pytesseract.image_to_string(img.convert("L"), config="--psm 6") for img in images)
    except Exception as e:
        logger.warning(f"OCR skipped or failed: {e}")
        return ""


def is_scanned_pdf(pdf_bytes: bytes) -> bool:
    text = extract_text_digital(pdf_bytes)
    try:
        n_pages = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    except:
        n_pages = 1
    return len(text.strip()) < n_pages * 100


def clean_text(text: str) -> str:
    lines = [l for l in text.split("\n") if not NOISE_RE.search(l)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def normalize_question(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def segment_questions(text: str) -> List[str]:
    questions = []
    text = clean_text(text)

    pattern = re.compile(
        r"(?:^|\n)\s*(?:Q\.?\s*)?(\d{1,2})\s*[.)]\s*([A-Z].{20,}?)(?=\n\s*(?:Q\.?\s*)?\d{1,2}\s*[.)]|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    for _, q_text in pattern.findall(text):
        q = q_text.strip()
        if 15 < len(q) < 800:
            questions.append(q)

    if len(questions) < 3:
        TRIGGER_WORDS = ["explain","define","derive","write","describe","discuss",
                         "what","why","how","compare","find","prove","state",
                         "calculate","determine","analyze"]
        for line in text.split("\n"):
            line = line.strip()
            if (len(line) > 30 and line[0].isupper()
                    and not NOISE_RE.search(line)
                    and any(kw in line.lower() for kw in TRIGGER_WORDS)):
                questions.append(line)

    seen, unique = set(), []
    for q in questions:
        n = normalize_question(q)
        if n not in seen:
            seen.add(n); unique.append(q)
    return unique


def extract_question_type(question: str) -> str:
    q = question.lower()
    if any(k in q for k in ["calculate","find","determine","solve","compute","evaluate","derive","prove"]):
        return "numerical"
    if any(k in q for k in ["define","list","state","name","what is","mention"]) and len(question) < 120:
        return "short"
    return "theory"


def process_pdf(pdf_bytes: bytes) -> Tuple[List[str], str, int]:
    scanned = is_scanned_pdf(pdf_bytes)
    if scanned:
        text = extract_text_ocr(pdf_bytes); method = "ocr"
        if not text.strip():
            text = extract_text_digital(pdf_bytes); method = "digital_fallback"
    else:
        text = extract_text_digital(pdf_bytes); method = "digital"
        if len(text.strip()) < 200:
            text = extract_text_ocr(pdf_bytes); method = "ocr_fallback"

    try:
        n_pages = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    except:
        n_pages = 0

    questions = segment_questions(text)
    logger.info(f"Extracted {len(questions)} questions via {method}")
    return questions, method, n_pages
