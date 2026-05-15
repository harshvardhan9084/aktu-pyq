"""
PDF Processing Service — AKTU PYQ Intelligence System
═══════════════════════════════════════════════════════
Handles every failure mode found in real AKTU papers:

  ✓ Digital (text-based) PDFs          — pypdf + pdfplumber
  ✓ Scanned PDFs                        — Tesseract OCR
  ✓ Rotated/skewed scans               — OpenCV deskew
  ✓ Shadow / low contrast / noise      — OpenCV adaptive threshold
  ✓ Questions split across pages       — cross-page stitching
  ✓ Sub-parts (a)(b)(c) under one Q   — grouped under parent
  ✓ Garbled Unicode from bad OCR      — ftfy cleanup
  ✓ Math/diagram questions            — detected & tagged
  ✓ Duplicate questions in same paper — hash dedup

NOTE ON IMPORTS: All heavy/optional libraries (cv2, ftfy, pdf2image,
pytesseract, pdfplumber) are imported LAZILY inside functions.
This means the server starts even if some optional packages are missing,
and only fails gracefully at the point of use.
"""

import hashlib
import re
import io
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass, field

# Only stdlib + guaranteed packages imported at module level
from pypdf import PdfReader

logger = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ExtractedQuestion:
    text: str
    question_type: str = "theory"        # theory | numerical | short | diagram
    has_diagram: bool = False
    has_math: bool = False
    sub_parts: List[str] = field(default_factory=list)
    page_number: int = 0
    marks: Optional[int] = None
    raw_text: str = ""


# ── Noise patterns (no inline (?i) flags — use re.IGNORECASE at compile) ──────

NOISE_PATTERNS = [
    r"note\s*:",
    r"all questions are compulsory",
    r"attempt any \w+",
    r"maximum marks\s*[:\-]?\s*\d+",
    r"time\s*(?:allowed|duration)\s*[:\-]",
    r"roll\s*no",
    r"examination\s+\d{4}",
    r"b\.?\s*tech",
    r"end\s*term\s*exam",
    r"mid\s*term\s*exam",
    r"paper\s*code\s*:",
    r"\[\s*\d+\s*(?:marks?)?\s*\]",
    r"\(\s*\d+\s*(?:marks?)?\s*\)",
    r"page\s*\d+\s*of\s*\d+",
    r"contd\.?",
    r"turn\s*over",
]
NOISE_RE = re.compile("|".join(NOISE_PATTERNS), re.IGNORECASE)

MARKS_RE = re.compile(r"\[(\d+)\]|\((\d+)\s*marks?\)", re.IGNORECASE)

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

DIAGRAM_INDICATORS = [
    r"draw|sketch|show|plot|illustrate",
    r"circuit|block\s+diagram|waveform",
    r"referring\s+to\s+(?:the\s+)?(?:circuit|figure|diagram)",
    r"from\s+the\s+(?:circuit|figure|diagram)\s+(?:shown|given)",
    r"fig(?:ure|\.)\s*\d+",
    r"as\s+shown\s+in",
]
DIAGRAM_RE = re.compile("|".join(DIAGRAM_INDICATORS), re.IGNORECASE)

MATH_INDICATORS = [
    r"derive\s+(?:the\s+)?(?:expression|equation|formula)",
    r"solve\s+(?:the\s+)?(?:differential|integral|equation)",
    r"[∫∑∏√∂∇±×÷≤≥≠∞αβγδεζηθλμπρσφψω]",
    r"laplace|fourier|z-transform",
    r"d[xy]/d[txy]",
    r"\^[{(]?\d",
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
    """Fix garbled OCR characters. Lazy import — skips if ftfy not installed."""
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


def clean_text(text: str) -> str:
    lines = [l for l in text.split("\n") if not NOISE_RE.search(l)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


# ── Image preprocessing ───────────────────────────────────────────────────────

def preprocess_image_for_ocr(pil_image):
    """
    OpenCV pipeline: grayscale → deskew → denoise → adaptive threshold.
    Lazy import — falls back to simple grayscale if cv2 not available.
    """
    try:
        import cv2
        import numpy as np

        img = cv2.cvtColor(__pil_to_numpy(pil_image), cv2.COLOR_RGB2GRAY)

        # Deskew
        coords = np.column_stack(np.where(img < 200))
        if len(coords) > 100:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = 90 + angle
            if abs(angle) > 0.5:
                (h, w) = img.shape
                M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
                img = cv2.warpAffine(img, M, (w, h),
                                     flags=cv2.INTER_CUBIC,
                                     borderMode=cv2.BORDER_REPLICATE)

        # Denoise
        img = cv2.fastNlMeansDenoising(img, h=10)

        # Adaptive threshold — handles uneven lighting and binding shadows
        img = cv2.adaptiveThreshold(
            img, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 31, 11
        )

        from PIL import Image as PILImage
        return PILImage.fromarray(img)

    except ImportError:
        logger.debug("cv2 not available — using raw grayscale for OCR")
        return pil_image.convert("L")
    except Exception as e:
        logger.warning(f"Image preprocessing error: {e}")
        return pil_image.convert("L")


def __pil_to_numpy(pil_image):
    import numpy as np
    return np.array(pil_image.convert("RGB"))


# ── PDF text extraction ───────────────────────────────────────────────────────

def extract_text_digital_pypdf(pdf_bytes: bytes) -> Tuple[List[str], int]:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        return pages, len(pages)
    except Exception as e:
        logger.warning(f"pypdf failed: {e}")
        return [], 0


def extract_text_digital_pdfplumber(pdf_bytes: bytes) -> Tuple[List[str], int]:
    """Lazy import — better for multi-column and table-heavy layouts."""
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
        return pages, len(pages)
    except ImportError:
        return [], 0
    except Exception as e:
        logger.warning(f"pdfplumber failed: {e}")
        return [], 0


def extract_text_ocr_pages(pdf_bytes: bytes) -> Tuple[List[str], int]:
    """
    Full OCR pipeline for scanned PDFs.
    Lazy imports — gracefully skipped if pdf2image/pytesseract not installed.
    """
    try:
        import pdf2image
        import pytesseract

        images = pdf2image.convert_from_bytes(pdf_bytes, dpi=300)
        pages = []
        for i, img in enumerate(images):
            try:
                preprocessed = preprocess_image_for_ocr(img)
                text = pytesseract.image_to_string(
                    preprocessed,
                    config="--psm 6 --oem 3 -l eng"
                )
                text = fix_unicode(text)
                pages.append(text)
            except Exception as e:
                logger.warning(f"OCR failed on page {i+1}: {e}")
                pages.append("")
        return pages, len(images)

    except ImportError as e:
        logger.warning(f"OCR dependencies not available: {e}")
        return [], 0
    except Exception as e:
        logger.error(f"OCR pipeline failed: {e}")
        return [], 0


def is_scanned_pdf(pdf_bytes: bytes) -> bool:
    pages, n = extract_text_digital_pypdf(pdf_bytes)
    if n == 0:
        return True
    total_chars = sum(len(p.strip()) for p in pages)
    return total_chars < n * 100


def best_digital_extraction(pdf_bytes: bytes) -> Tuple[List[str], str]:
    pypdf_pages, _ = extract_text_digital_pypdf(pdf_bytes)
    plumber_pages, _ = extract_text_digital_pdfplumber(pdf_bytes)

    pypdf_chars = sum(len(p) for p in pypdf_pages)
    plumber_chars = sum(len(p) for p in plumber_pages)

    if plumber_chars > pypdf_chars * 1.1:
        return plumber_pages, "pdfplumber"
    return pypdf_pages, "pypdf"


# ── Cross-page stitching ──────────────────────────────────────────────────────

def stitch_pages(page_texts: List[str]) -> str:
    """Join pages, detecting mid-sentence cuts at page boundaries."""
    result = []
    for page in page_texts:
        page = page.rstrip()
        if not page:
            continue
        if result:
            last_char = result[-1][-1] if result[-1] else ""
            if last_char not in ".?!:":
                result[-1] = result[-1] + " " + page.lstrip()
            else:
                result.append(page)
        else:
            result.append(page)
    return "\n\n".join(result)


# ── Question segmentation ─────────────────────────────────────────────────────

def extract_sub_parts(text: str) -> Tuple[str, List[str]]:
    sub_matches = SUB_PART_RE.findall(text)
    if len(sub_matches) >= 2:
        parent = SUB_PART_RE.sub("", text).strip()
        sub_parts = [f"({letter}) {content.strip()}" for letter, content in sub_matches]
        return parent, sub_parts
    return text, []


def classify_question(text: str) -> Tuple[str, bool, bool]:
    has_diagram = bool(DIAGRAM_RE.search(text))
    has_math = bool(MATH_RE.search(text))
    q = text.lower()

    if has_diagram:
        return "diagram", True, has_math

    if any(k in q for k in ["calculate", "find", "determine", "solve", "compute",
                              "evaluate", "derive", "prove", "show that"]) or has_math:
        return "numerical", False, True

    if any(k in q for k in ["define", "list", "state", "name", "what is",
                              "mention"]) and len(text) < 150:
        return "short", False, False

    return "theory", False, has_math


def segment_questions_from_text(full_text: str) -> List[ExtractedQuestion]:
    questions: List[ExtractedQuestion] = []
    full_text = clean_text(full_text)

    # Strategy 1: numbered questions
    matches = list(Q_NUM_RE.finditer(full_text))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        q_text = full_text[match.start(2):end].strip()
        q_text = fix_unicode(q_text)
        marks = extract_marks(q_text)
        q_text = MARKS_RE.sub("", q_text).strip()

        if len(q_text) < 15 or len(q_text) > 1200:
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

    # Strategy 2: fallback trigger-word line detection
    if len(questions) < 3:
        for line in full_text.split("\n"):
            line = line.strip()
            if (len(line) > 35
                    and line[0].isupper()
                    and not NOISE_RE.search(line)
                    and any(kw in line.lower() for kw in TRIGGER_WORDS)):
                q_type, has_diag, has_math = classify_question(line)
                questions.append(ExtractedQuestion(
                    text=line, question_type=q_type,
                    has_diagram=has_diag, has_math=has_math,
                ))

    # Deduplicate
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
    Master pipeline: bytes → (questions, method_used, page_count)

    Decision tree:
      1. Try digital extraction (pypdf vs pdfplumber, pick best)
      2. If text is sparse → run OCR pipeline
      3. Stitch pages for cross-page questions
      4. Segment and classify each question
    """
    scanned = is_scanned_pdf(pdf_bytes)

    if scanned:
        logger.info("Scanned PDF — using OCR pipeline")
        page_texts, n_pages = extract_text_ocr_pages(pdf_bytes)
        method = "ocr"
        if not any(page_texts):
            page_texts, method_d = best_digital_extraction(pdf_bytes)
            n_pages = len(page_texts)
            method = f"digital_fallback({method_d})"
    else:
        page_texts, method_d = best_digital_extraction(pdf_bytes)
        n_pages = len(page_texts)
        method = f"digital_{method_d}"

        total_chars = sum(len(p) for p in page_texts)
        if total_chars < n_pages * 80:
            logger.info("Digital extraction weak — adding OCR pass")
            ocr_pages, _ = extract_text_ocr_pages(pdf_bytes)
            page_texts = [
                (ocr_pages[i] if i < len(ocr_pages)
                 and len(ocr_pages[i]) > len(page_texts[i])
                 else page_texts[i])
                for i in range(n_pages)
            ]
            method = "hybrid"

    full_text = stitch_pages(page_texts)
    questions = segment_questions_from_text(full_text)

    logger.info(
        f"process_pdf: {len(questions)} questions | method={method} | "
        f"pages={n_pages} | diagrams={sum(1 for q in questions if q.has_diagram)} | "
        f"math={sum(1 for q in questions if q.has_math)}"
    )

    return questions, method, n_pages


def extract_question_type(question_text: str) -> str:
    """Legacy compat for routers that pass plain text."""
    q_type, _, _ = classify_question(question_text)
    return q_type