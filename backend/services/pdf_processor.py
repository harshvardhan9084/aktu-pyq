"""
PDF Processing Service — AKTU PYQ Intelligence System
Handles every failure mode found in real AKTU papers:

  - Digital (text-based) PDFs          - pypdf + pdfplumber
  - Scanned PDFs                        - Tesseract OCR
  - Rotated/skewed scans               - OpenCV deskew
  - Shadow, low contrast, noise        - OpenCV preprocessing
  - Math equations & symbols           - pix2tex LaTeX OCR
  - Circuits/diagrams                  - detected, tagged, skipped cleanly
  - Questions split across pages       - cross-page stitching
  - Sub-parts (a)(b)(c) under one Q    - grouped under parent
  - Garbled Unicode from bad OCR       - ftfy cleanup
  - Duplicate questions in same paper  - hash dedup
"""

import hashlib
import re
import io
import logging
import math
from typing import List, Tuple, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ExtractedQuestion:
    text: str
    question_type: str = "theory"           # theory | numerical | short | diagram
    has_diagram: bool = False
    has_math: bool = False
    math_latex: List[str] = field(default_factory=list)
    sub_parts: List[str] = field(default_factory=list)
    page_number: int = 0
    marks: Optional[int] = None
    raw_text: str = ""                      # original before cleaning


# ── Noise patterns ────────────────────────────────────────────────────────────

NOISE_PATTERNS = [
    r"(?i)note\s*:",
    r"(?i)all questions are compulsory",
    r"(?i)attempt any \w+",
    r"(?i)maximum marks\s*[:\-]?\s*\d+",
    r"(?i)time\s*(?:allowed|duration)\s*[:\-]",
    r"(?i)roll\s*no",
    r"(?i)examination\s+\d{4}",
    r"(?i)b\.?\s*tech",
    r"(?i)end\s*term\s*exam",
    r"(?i)mid\s*term\s*exam",
    r"(?i)paper\s*code\s*:",
    r"\[\s*\d+\s*(?:marks?)?\s*\]",
    r"\(\s*\d+\s*(?:marks?)?\s*\)",
    r"(?i)page\s*\d+\s*of\s*\d+",
    r"(?i)contd\.?",
    r"(?i)turn\s*over",
]
NOISE_RE = re.compile("|".join(NOISE_PATTERNS), re.IGNORECASE)

# Marks extractor — finds [10] or (5 marks) near a question
MARKS_RE = re.compile(r"\[(\d+)\]|\((\d+)\s*marks?\)", re.IGNORECASE)

# Question number patterns
Q_NUM_RE = re.compile(
    r"(?:^|\n)\s*"
    r"(?:(?:Q(?:uestion)?\.?\s*)|(?:(?:Section|Part)\s+[A-Z]\s*[-–:]\s*)?)?"
    r"(\d{1,2})\s*[.)]\s*"
    r"([A-Z].{15,})",
    re.DOTALL | re.MULTILINE,
)

SUB_PART_RE = re.compile(
    r"(?:^|\n)\s*\(([a-z])\)\s*(.+?)(?=\n\s*\([a-z]\)|\Z)",
    re.DOTALL | re.MULTILINE,
)

# Diagram/circuit indicators — these questions get has_diagram=True
DIAGRAM_INDICATORS = [
    r"(?i)(?:draw|sketch|show|plot|illustrate)\s+(?:the\s+)?(?:circuit|diagram|graph|waveform|figure|block\s+diagram|network)",
    r"(?i)referring\s+to\s+(?:the\s+)?(?:circuit|figure|diagram)",
    r"(?i)from\s+the\s+(?:circuit|figure|diagram)\s+(?:shown|given|above|below)",
    r"(?i)fig(?:ure|\.)\s*\d+",
    r"(?i)as\s+shown\s+in\s+(?:the\s+)?(?:circuit|figure|diagram)",
]
DIAGRAM_RE = re.compile("|".join(DIAGRAM_INDICATORS))

# Math/equation indicators
MATH_INDICATORS = [
    r"(?i)derive\s+(?:the\s+)?(?:expression|equation|formula)",
    r"(?i)solve\s+(?:the\s+)?(?:differential|integral|equation)",
    r"[∫∑∏√∂∇±×÷≤≥≠∞αβγδεζηθλμπρσφψω]",
    r"\b(?:laplace|fourier|z-transform|integral|differential)\b",
    r"d[xy]/d[txy]",                           # dy/dx, dx/dt etc.
    r"\^[{(]?\d",                              # x^2 style
]
MATH_RE = re.compile("|".join(MATH_INDICATORS), re.IGNORECASE)

TRIGGER_WORDS = [
    "explain", "define", "derive", "write", "describe", "discuss",
    "what", "why", "how", "compare", "find", "prove", "state",
    "calculate", "determine", "analyze", "differentiate", "enumerate",
    "list", "obtain", "evaluate", "solve", "draw", "sketch", "show",
    "examine", "justify", "illustrate", "classify", "summarize",
]


# ── Core utilities ────────────────────────────────────────────────────────────

def compute_file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def fix_unicode(text: str) -> str:
    """Fix garbled characters from bad OCR using ftfy."""
    try:
        import ftfy
        return ftfy.fix_text(text)
    except ImportError:
        return text


def normalize_question(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_marks(text: str) -> Optional[int]:
    m = MARKS_RE.search(text)
    if m:
        return int(m.group(1) or m.group(2))
    return None


def clean_line(text: str) -> str:
    """Remove noise patterns from a single block of text."""
    lines = text.split("\n")
    clean = [l for l in lines if not NOISE_RE.search(l)]
    text = "\n".join(clean)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Image preprocessing ───────────────────────────────────────────────────────

def preprocess_image_for_ocr(pil_image):
    """
    OpenCV pipeline that maximises OCR accuracy:
      1. Grayscale
      2. Deskew (correct rotation from binding/scan angle)
      3. Denoise
      4. Adaptive threshold (handles uneven lighting/shadows)
      5. Morphological cleanup
    Returns a PIL Image ready for Tesseract.
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image

        img = np.array(pil_image.convert("RGB"))
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        # ── Deskew ──────────────────────────────────────────────────────────
        coords = np.column_stack(np.where(gray < 200))
        if len(coords) > 100:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = 90 + angle
            if abs(angle) > 0.5:  # only correct if noticeably skewed
                (h, w) = gray.shape
                M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
                gray = cv2.warpAffine(gray, M, (w, h),
                                      flags=cv2.INTER_CUBIC,
                                      borderMode=cv2.BORDER_REPLICATE)

        # ── Denoise ─────────────────────────────────────────────────────────
        gray = cv2.fastNlMeansDenoising(gray, h=10)

        # ── Adaptive threshold ───────────────────────────────────────────────
        # Handles shadows from book binding and uneven scan lighting
        processed = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 31, 11
        )

        # ── Morphological cleanup ────────────────────────────────────────────
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
        processed = cv2.morphologyEx(processed, cv2.MORPH_CLOSE, kernel)

        return Image.fromarray(processed)

    except ImportError:
        logger.warning("OpenCV not available — using raw image for OCR")
        return pil_image.convert("L")
    except Exception as e:
        logger.warning(f"Image preprocessing error: {e} — using raw image")
        return pil_image.convert("L")


# ── Math / equation OCR ───────────────────────────────────────────────────────

# Singleton: load the pix2tex model once, reuse across all calls
_latex_ocr_model = None


def _get_latex_ocr_model():
    """Lazy singleton for the pix2tex LatexOCR model (~200MB)."""
    global _latex_ocr_model
    if _latex_ocr_model is None:
        from pix2tex.cli import LatexOCR
        _latex_ocr_model = LatexOCR()
    return _latex_ocr_model


def extract_math_from_image(pil_image) -> List[str]:
    """
    Detect and extract math equations from an image using pix2tex.
    Returns list of LaTeX strings found.
    If pix2tex not available, returns empty list gracefully.
    """
    try:
        model = _get_latex_ocr_model()
        latex = model(pil_image)
        if latex and len(latex.strip()) > 3:
            return [latex.strip()]
        return []
    except ImportError:
        return []
    except Exception as e:
        logger.debug(f"Math OCR skipped: {e}")
        return []


# ── PDF text extraction ───────────────────────────────────────────────────────

def extract_text_digital_pypdf(pdf_bytes: bytes) -> Tuple[List[str], int]:
    """
    Extract text per-page using pypdf.
    Returns (list_of_page_texts, page_count).
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)
        return pages, len(pages)
    except Exception as e:
        logger.warning(f"pypdf failed: {e}")
        return [], 0


def extract_text_digital_pdfplumber(pdf_bytes: bytes) -> Tuple[List[str], int]:
    """
    Extract text per-page using pdfplumber — better for tables and
    multi-column layouts common in AKTU papers.
    """
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages.append(text)
        return pages, len(pages)
    except Exception as e:
        logger.warning(f"pdfplumber failed: {e}")
        return [], 0


def extract_text_ocr_pages(pdf_bytes: bytes) -> Tuple[List[str], int]:
    """
    Full OCR pipeline for scanned PDFs.
    Per page: convert to image -> preprocess -> Tesseract.
    Returns (list_of_page_texts, page_count).
    """
    try:
        import pdf2image
        import pytesseract

        images = pdf2image.convert_from_bytes(pdf_bytes, dpi=300)
        pages = []
        for i, img in enumerate(images):
            try:
                preprocessed = preprocess_image_for_ocr(img)
                # PSM 6: assume uniform block of text (best for exam papers)
                # OEM 3: use both legacy and LSTM engines
                text = pytesseract.image_to_string(
                    preprocessed,
                    config="--psm 6 --oem 3 -l eng"
                )
                text = fix_unicode(text)
                pages.append(text)
                logger.debug(f"OCR page {i+1}: {len(text)} chars")
            except Exception as e:
                logger.warning(f"OCR failed on page {i+1}: {e}")
                pages.append("")
        return pages, len(images)
    except Exception as e:
        logger.error(f"OCR pipeline failed: {e}")
        return [], 0


def is_scanned_pdf(pdf_bytes: bytes) -> bool:
    """Heuristic: if digital extraction yields <100 chars per page, it's scanned."""
    pages, n = extract_text_digital_pypdf(pdf_bytes)
    if n == 0:
        return True
    total_chars = sum(len(p.strip()) for p in pages)
    return total_chars < n * 100


def best_digital_extraction(pdf_bytes: bytes) -> Tuple[List[str], str]:
    """
    Try pypdf first, then pdfplumber.
    Return whichever gives more text, and the method name.
    """
    pypdf_pages, _ = extract_text_digital_pypdf(pdf_bytes)
    plumber_pages, _ = extract_text_digital_pdfplumber(pdf_bytes)

    pypdf_chars = sum(len(p) for p in pypdf_pages)
    plumber_chars = sum(len(p) for p in plumber_pages)

    if plumber_chars > pypdf_chars * 1.1:  # pdfplumber got >10% more text
        return plumber_pages, "pdfplumber"
    return pypdf_pages, "pypdf"


# ── Cross-page question stitching ─────────────────────────────────────────────

def stitch_pages(page_texts: List[str]) -> str:
    """
    Join pages intelligently — detect when a question is cut mid-sentence
    at a page boundary and stitch it back together.
    A page ending mid-sentence (no terminal punctuation) gets joined
    directly to the next page start rather than separated by a newline.
    """
    result = []
    for i, page in enumerate(page_texts):
        page = page.rstrip()
        if not page:
            continue
        if result:
            # Check if previous page ended mid-sentence
            last_char = result[-1][-1] if result[-1] else ""
            if last_char not in ".?!:":
                # Mid-sentence cut — stitch directly
                result[-1] = result[-1] + " " + page.lstrip()
            else:
                result.append(page)
        else:
            result.append(page)
    return "\n\n".join(result)


# ── Question segmentation ─────────────────────────────────────────────────────

def extract_sub_parts(text: str) -> Tuple[str, List[str]]:
    """
    If a question has sub-parts (a) (b) (c), extract them separately
    and return (parent_text, [sub_part_texts]).
    """
    sub_matches = SUB_PART_RE.findall(text)
    if len(sub_matches) >= 2:
        # Remove sub-parts from main text
        parent = SUB_PART_RE.sub("", text).strip()
        sub_parts = [f"({letter}) {content.strip()}" for letter, content in sub_matches]
        return parent, sub_parts
    return text, []


def classify_question(text: str) -> Tuple[str, bool, bool]:
    """
    Returns (question_type, has_diagram, has_math).
    question_type: theory | numerical | short | diagram
    All returned values are valid for the DB CHECK constraint:
      question_type IN ('theory','numerical','short','other','diagram')
    """
    has_diagram = bool(DIAGRAM_RE.search(text))
    has_math = bool(MATH_RE.search(text))

    q = text.lower()

    numerical_kw = ["calculate", "find", "determine", "solve", "compute",
                    "evaluate", "obtain the value", "derive the expression",
                    "prove that", "show that"]
    if any(k in q for k in numerical_kw) or has_math:
        return "numerical", has_diagram, True

    short_kw = ["define", "list", "state", "name", "what is", "mention",
                "write short note", "briefly explain"]
    if any(k in q for k in short_kw) and len(text) < 150:
        return "short", has_diagram, has_math

    if has_diagram:
        return "diagram", True, has_math

    return "theory", False, has_math


def segment_questions_from_text(full_text: str, page_offset: int = 0) -> List[ExtractedQuestion]:
    """
    Extract individual questions from a full paper text.
    Handles numbered questions, sub-parts, and fallback line-by-line detection.
    """
    questions: List[ExtractedQuestion] = []
    full_text = clean_line(full_text)

    # ── Strategy 1: numbered questions ──────────────────────────────────────
    matches = list(Q_NUM_RE.finditer(full_text))

    for i, match in enumerate(matches):
        q_text = match.group(2).strip()

        # If there's a next match, cut the text there
        if i + 1 < len(matches):
            end = matches[i + 1].start()
            q_text = full_text[match.start(2):end].strip()

        q_text = fix_unicode(q_text)
        marks = extract_marks(q_text)

        # Clean marks notation from question text
        q_text = MARKS_RE.sub("", q_text).strip()

        if len(q_text) < 10 or len(q_text) > 1200:
            continue

        parent_text, sub_parts = extract_sub_parts(q_text)
        q_type, has_diag, has_math = classify_question(parent_text)

        questions.append(ExtractedQuestion(
            text=parent_text,
            question_type=q_type,
            has_diagram=has_diag,
            has_math=has_math,
            sub_parts=sub_parts,
            marks=marks,
            raw_text=q_text,
        ))

    # ── Strategy 2: fallback — trigger-word line detection ──────────────────
    if len(questions) < 3:
        for line in full_text.split("\n"):
            line = line.strip()
            if (len(line) > 35
                    and line[0].isupper()
                    and not NOISE_RE.search(line)
                    and any(kw in line.lower() for kw in TRIGGER_WORDS)):
                q_type, has_diag, has_math = classify_question(line)
                questions.append(ExtractedQuestion(
                    text=line,
                    question_type=q_type,
                    has_diagram=has_diag,
                    has_math=has_math,
                ))

    # ── Deduplicate by normalized text ──────────────────────────────────────
    seen: set = set()
    unique: List[ExtractedQuestion] = []
    for q in questions:
        key = normalize_question(q.text)
        if key and key not in seen:
            seen.add(key)
            unique.append(q)

    return unique


# ── Master pipeline ───────────────────────────────────────────────────────────

def process_pdf(pdf_bytes: bytes) -> Tuple[List[ExtractedQuestion], str, int]:
    """
    Master pipeline: bytes -> (questions, method_used, page_count)

    Decision tree:
      1. Try digital extraction (pypdf + pdfplumber, pick best)
      2. If text is sparse -> run OCR pipeline
      3. Stitch pages to handle cross-page questions
      4. Segment into individual questions
      5. Classify each question (theory/numerical/diagram)
    """
    scanned = is_scanned_pdf(pdf_bytes)

    if scanned:
        logger.info("Scanned PDF detected — using OCR pipeline")
        page_texts, n_pages = extract_text_ocr_pages(pdf_bytes)
        method = "ocr+opencv"
        if not any(page_texts):
            # Last resort: try digital anyway (some PDFs mis-classify)
            page_texts, n_pages = best_digital_extraction(pdf_bytes)
            method = "digital_fallback"
    else:
        page_texts, method = best_digital_extraction(pdf_bytes)
        n_pages = len(page_texts)
        method = f"digital_{method}"

        # Verify we got meaningful text; fall back to OCR if not
        total_chars = sum(len(p) for p in page_texts)
        if total_chars < n_pages * 80:
            logger.info("Digital extraction weak — adding OCR pass")
            ocr_pages, _ = extract_text_ocr_pages(pdf_bytes)
            # Merge: use whichever page has more text
            page_texts = [
                (ocr_pages[i] if i < len(ocr_pages) and len(ocr_pages[i]) > len(page_texts[i]) else page_texts[i])
                for i in range(n_pages)
            ]
            method = "hybrid_digital+ocr"

    # Stitch across page boundaries
    full_text = stitch_pages(page_texts)

    # Segment into questions
    questions = segment_questions_from_text(full_text)

    logger.info(
        f"process_pdf complete: {len(questions)} questions | "
        f"method={method} | pages={n_pages} | "
        f"diagrams={sum(1 for q in questions if q.has_diagram)} | "
        f"math={sum(1 for q in questions if q.has_math)}"
    )

    return questions, method, n_pages


# ── Legacy compat (used by routers) ──────────────────────────────────────────

def extract_question_type(question_text: str) -> str:
    q_type, _, _ = classify_question(question_text)
    return q_type
