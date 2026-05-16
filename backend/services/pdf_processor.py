"""
PDF Processing Service — AKTU PYQ Intelligence System v2
═══════════════════════════════════════════════════════════

NEW IN v2:
  ✓ extract_paper_metadata()  — reads AKTU header: programme, subject, code, branch, semester, year, session
  ✓ detect_unit_sections()    — splits paper into Unit 1–5 sections, tags each question with unit + topic
  ✓ question_hash             — SHA-256 of normalized_text, exact dedup (replaces ilike substring)
  ✓ extract_diagram_crop()    — crops largest non-text region from page → PNG bytes for diagrams/circuits
  ✓ sub_parts + page_number   — fully propagated through ExtractedQuestion

IMPORT RULES (do not change):
  All heavy/optional libs (cv2, ftfy, pdf2image, pytesseract, pdfplumber) are
  lazy-imported inside functions. Server starts even if packages are absent.
"""

import hashlib
import re
import io
import logging
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass, field

from pypdf import PdfReader

logger = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ExtractedQuestion:
    text: str
    question_type: str = "theory"       # theory | numerical | short | diagram | other
    has_diagram: bool = False
    has_math: bool = False
    sub_parts: List[str] = field(default_factory=list)
    page_number: int = 0
    marks: Optional[int] = None
    raw_text: str = ""
    unit: Optional[int] = None          # NEW: 1–5
    unit_topic: Optional[str] = None    # NEW: "Transmission Lines", etc.
    question_hash: Optional[str] = None # NEW: sha256 of normalized_text


@dataclass
class PaperMetadata:
    """Parsed from AKTU paper header (page 1)."""
    programme: Optional[str] = None     # B.Tech, M.Tech, Diploma, MCA, MBA
    subject_name: Optional[str] = None
    subject_code: Optional[str] = None  # e.g. EE-301
    branch: Optional[str] = None
    semester: Optional[int] = None
    year: Optional[int] = None          # academic year start, e.g. 2022 for 2022-23
    exam_session: Optional[str] = None  # odd | even
    university: str = "AKTU"


# ── Subject code lookup (expand over time) ────────────────────────────────────

SUBJECT_CODE_MAP: Dict[str, Dict] = {
    # Electrical
    "EE-301": {"subject": "Basic Electrical Engineering", "branch": "Electrical Engineering"},
    "EE-501": {"subject": "Power Systems", "branch": "Electrical Engineering"},
    "EE-601": {"subject": "Control Systems", "branch": "Electrical Engineering"},
    "EE-701": {"subject": "Power Electronics", "branch": "Electrical Engineering"},
    # Electronics & Communication
    "EC-301": {"subject": "Analog Electronics", "branch": "Electronics & Communication"},
    "EC-401": {"subject": "Digital Electronics", "branch": "Electronics & Communication"},
    "EC-501": {"subject": "Signals & Systems", "branch": "Electronics & Communication"},
    "EC-601": {"subject": "Communication Systems", "branch": "Electronics & Communication"},
    # Computer Science
    "CS-301": {"subject": "Data Structures", "branch": "Computer Science & Engineering"},
    "CS-401": {"subject": "Design & Analysis of Algorithms", "branch": "Computer Science & Engineering"},
    "CS-501": {"subject": "Database Management Systems", "branch": "Computer Science & Engineering"},
    "CS-601": {"subject": "Operating Systems", "branch": "Computer Science & Engineering"},
    "CS-701": {"subject": "Computer Networks", "branch": "Computer Science & Engineering"},
    "CS-801": {"subject": "Software Engineering", "branch": "Computer Science & Engineering"},
    # Mechanical
    "ME-301": {"subject": "Engineering Thermodynamics", "branch": "Mechanical Engineering"},
    "ME-401": {"subject": "Fluid Mechanics", "branch": "Mechanical Engineering"},
    "ME-501": {"subject": "Machine Design", "branch": "Mechanical Engineering"},
    # Civil
    "CE-301": {"subject": "Structural Analysis", "branch": "Civil Engineering"},
    "CE-401": {"subject": "Geotechnical Engineering", "branch": "Civil Engineering"},
    # Common
    "NAS-101": {"subject": "Engineering Chemistry", "branch": None},
    "NAS-103": {"subject": "Engineering Mathematics I", "branch": None},
    "NAS-203": {"subject": "Engineering Mathematics II", "branch": None},
    "NAS-303": {"subject": "Engineering Mathematics III", "branch": None},
    "NEC-101": {"subject": "Fundamentals of Electronics", "branch": None},
    "NEE-101": {"subject": "Basic Electrical Engineering", "branch": None},
    "NCS-301": {"subject": "Data Structures using C", "branch": None},
    "NCS-501": {"subject": "Database Management Systems", "branch": None},
    "NCS-601": {"subject": "Operating Systems", "branch": None},
}


# ── Noise patterns ────────────────────────────────────────────────────────────

NOISE_PATTERNS = [
    r"note\s*:",
    r"all questions are compulsory",
    r"attempt any \w+",
    r"maximum marks\s*[:\-]?\s*\d+",
    r"time\s*(?:allowed|duration)\s*[:\-]",
    r"roll\s*no",
    r"examination\s+\d{4}",
    r"end\s*term\s*exam",
    r"mid\s*term\s*exam",
    r"paper\s*code\s*:",
    r"\[\s*\d+\s*(?:marks?)?\s*\]",
    r"\(\s*\d+\s*(?:marks?)?\s*\)",
    r"page\s*\d+\s*of\s*\d+",
    r"contd\.?",
    r"turn\s*over",
    r"b\.?\s*tech",
    r"m\.?\s*tech",
    r"diploma",
    r"semester\s+exam",
]
NOISE_RE = re.compile("|".join(NOISE_PATTERNS), re.IGNORECASE)

MARKS_RE = re.compile(r"\[(\d+)\]|\((\d+)\s*marks?\)", re.IGNORECASE)

Q_NUM_RE = re.compile(
    r"(?:^|\n)\s*"
    r"(?:(?:Q(?:uestion)?\.?\s*)|(?:(?:Section|Part)\s+[A-Z]\s*[-–:]?\s*)?)?"
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
    r"fig(?:ure|\.)?\s*\d+",
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

# Unit section header patterns
UNIT_RE = re.compile(
    r"(?:^|\n)\s*UNIT[\s\-–]*([IVX1-5]+)[:\s]*([^\n]{0,60})?",
    re.IGNORECASE | re.MULTILINE,
)
ROMAN_MAP = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
             "1": 1, "2": 2, "3": 3, "4": 4, "5": 5}

# AKTU header patterns
SEMESTER_RE = re.compile(r"SEM(?:ESTER)?[\s\-–]*([IVX1-8]+)", re.IGNORECASE)
YEAR_RE = re.compile(r"(\d{4})[\s\-–/]+\d{2,4}")
SESSION_RE = re.compile(r"(ODD|EVEN)\s+SEMESTER", re.IGNORECASE)
PROGRAMME_RE = re.compile(
    r"\b(B\.?\s*Tech|M\.?\s*Tech|MBA|MCA|Diploma|B\.?\s*Pharm|M\.?\s*Pharm)\b",
    re.IGNORECASE,
)
PAPER_CODE_RE = re.compile(
    r"(?:Paper\s+Code|Subject\s+Code)[:\s]*([A-Z]{2,3}[\s\-]?\d{3,4})",
    re.IGNORECASE,
)
SUBJECT_HEADER_RE = re.compile(
    r"(?:Subject|Paper)[:\s]+([A-Z][A-Za-z &\-]+?)(?:\n|Paper Code|Roll)",
    re.IGNORECASE,
)


# ── Core utilities ─────────────────────────────────────────────────────────────

def compute_file_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def compute_question_hash(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def fix_unicode(text: str) -> str:
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


def roman_to_int(s: str) -> Optional[int]:
    return ROMAN_MAP.get(s.upper().strip())


# ── AKTU Paper Metadata Extractor ─────────────────────────────────────────────

def extract_paper_metadata(pdf_bytes: bytes) -> PaperMetadata:
    """
    Reads AKTU exam header from the first page.
    Returns PaperMetadata with all fields populated where detectable.

    AKTU header format (typical):
      B.Tech. (SEM-III) ODD SEMESTER THEORY EXAMINATION 2022-23
      BASIC ELECTRICAL ENGINEERING
      Paper Code: EE-301
    """
    meta = PaperMetadata()

    # Get first page text via multiple strategies
    page_text = ""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if reader.pages:
            page_text = reader.pages[0].extract_text() or ""
    except Exception:
        pass

    # Fallback to pdfplumber if pypdf got nothing
    if len(page_text.strip()) < 50:
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                if pdf.pages:
                    page_text = pdf.pages[0].extract_text() or ""
        except Exception:
            pass

    if not page_text.strip():
        return meta

    # --- Programme ---
    pm = PROGRAMME_RE.search(page_text)
    if pm:
        raw = pm.group(1).replace(".", "").replace(" ", "")
        prog_map = {
            "BTech": "B.Tech", "MTech": "M.Tech", "MBA": "MBA",
            "MCA": "MCA", "Diploma": "Diploma",
            "BPharm": "B.Pharm", "MPharm": "M.Pharm",
        }
        meta.programme = prog_map.get(raw, pm.group(1))

    # --- Semester ---
    sm = SEMESTER_RE.search(page_text)
    if sm:
        meta.semester = roman_to_int(sm.group(1))

    # --- Academic year ---
    ym = YEAR_RE.search(page_text)
    if ym:
        meta.year = int(ym.group(1))

    # --- Exam session ---
    sess_m = SESSION_RE.search(page_text)
    if sess_m:
        meta.exam_session = sess_m.group(1).lower()  # "odd" | "even"

    # --- Paper / subject code ---
    code_m = PAPER_CODE_RE.search(page_text)
    if code_m:
        raw_code = re.sub(r"\s+", "-", code_m.group(1).strip()).upper()
        meta.subject_code = raw_code
        # Look up canonical name + branch
        lookup = SUBJECT_CODE_MAP.get(raw_code, {})
        if lookup:
            meta.subject_name = lookup.get("subject")
            meta.branch = lookup.get("branch")

    # --- Subject name (if not from code lookup) ---
    if not meta.subject_name:
        subj_m = SUBJECT_HEADER_RE.search(page_text)
        if subj_m:
            meta.subject_name = subj_m.group(1).strip().title()

    return meta


# ── Unit Section Detector ──────────────────────────────────────────────────────

def detect_unit_sections(full_text: str) -> List[Tuple[int, Optional[str], int, int]]:
    """
    Returns list of (unit_number, topic_label, char_start, char_end) tuples.
    Used to tag each question with its unit.
    """
    matches = list(UNIT_RE.finditer(full_text))
    sections = []
    for i, m in enumerate(matches):
        unit_str = m.group(1)
        unit_num = roman_to_int(unit_str)
        if unit_num is None:
            continue
        topic = (m.group(2) or "").strip().rstrip(":").strip() or None
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        sections.append((unit_num, topic, start, end))
    return sections


def assign_unit_to_position(char_pos: int, sections: List[Tuple[int, Optional[str], int, int]]) -> Tuple[Optional[int], Optional[str]]:
    for (unit_num, topic, start, end) in sections:
        if start <= char_pos < end:
            return unit_num, topic
    return None, None


# ── Image preprocessing ────────────────────────────────────────────────────────

def preprocess_image_for_ocr(pil_image):
    try:
        import cv2
        import numpy as np

        img = cv2.cvtColor(np.array(pil_image.convert("RGB")), cv2.COLOR_RGB2GRAY)
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
        img = cv2.fastNlMeansDenoising(img, h=10)
        img = cv2.adaptiveThreshold(img, 255,
                                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY, 31, 11)
        from PIL import Image as PILImage
        return PILImage.fromarray(img)
    except ImportError:
        return pil_image.convert("L")
    except Exception as e:
        logger.warning(f"Image preprocessing error: {e}")
        return pil_image.convert("L")


# ── Diagram Crop ───────────────────────────────────────────────────────────────

def extract_diagram_crop(pdf_bytes: bytes, page_number: int, dpi: int = 200) -> Optional[bytes]:
    """
    Crops the largest non-text vertical band from a page — the diagram/circuit region.
    Returns PNG bytes or None if no significant diagram region found.
    """
    try:
        import pdf2image
        import pdfplumber
        from PIL import Image as PILImage

        images = pdf2image.convert_from_bytes(
            pdf_bytes, dpi=dpi,
            first_page=page_number + 1,
            last_page=page_number + 1,
        )
        if not images:
            return None
        img = images[0]
        img_w, img_h = img.size

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if page_number >= len(pdf.pages):
                return None
            page = pdf.pages[page_number]
            page_h_pts = float(page.height)
            page_w_pts = float(page.width)
            words = page.extract_words()

        scale_y = img_h / page_h_pts
        scale_x = img_w / page_w_pts

        text_coverage = [0] * img_h
        for w in words:
            y0 = max(0, int(w["top"] * scale_y))
            y1 = min(img_h, int(w["bottom"] * scale_y))
            x0 = int(w["x0"] * scale_x)
            x1 = int(w["x1"] * scale_x)
            span = x1 - x0
            for row in range(y0, y1):
                text_coverage[row] += span

        TEXT_THRESHOLD = img_w * 0.18
        is_text_row = [c > TEXT_THRESHOLD for c in text_coverage]
        MIN_HEIGHT = int(img_h * 0.08)

        best_start, best_end, best_len = 0, 0, 0
        run_start = None
        for row in range(img_h):
            if not is_text_row[row]:
                if run_start is None:
                    run_start = row
            else:
                if run_start is not None:
                    run_len = row - run_start
                    if run_len > best_len:
                        best_len, best_start, best_end = run_len, run_start, row
                    run_start = None
        if run_start is not None:
            run_len = img_h - run_start
            if run_len > best_len:
                best_len, best_start, best_end = run_len, run_start, img_h

        if best_len < MIN_HEIGHT:
            return None

        PAD = int(img_h * 0.01)
        crop_box = (0, max(0, best_start - PAD), img_w, min(img_h, best_end + PAD))
        cropped = img.crop(crop_box)
        buf = io.BytesIO()
        cropped.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    except ImportError as e:
        logger.warning(f"Diagram crop deps missing: {e}")
        return None
    except Exception as e:
        logger.warning(f"Diagram crop failed on page {page_number}: {e}")
        return None


# ── PDF Text Extraction ────────────────────────────────────────────────────────

def extract_text_digital_pypdf(pdf_bytes: bytes) -> Tuple[List[str], int]:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        return pages, len(pages)
    except Exception as e:
        logger.warning(f"pypdf failed: {e}")
        return [], 0


def extract_text_digital_pdfplumber(pdf_bytes: bytes) -> Tuple[List[str], int]:
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
    try:
        import pdf2image
        import pytesseract

        images = pdf2image.convert_from_bytes(pdf_bytes, dpi=300)
        pages = []
        for i, img in enumerate(images):
            try:
                preprocessed = preprocess_image_for_ocr(img)
                text = pytesseract.image_to_string(
                    preprocessed, config="--psm 6 --oem 3 -l eng"
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


def stitch_pages(page_texts: List[str]) -> str:
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


# ── Question Segmentation ──────────────────────────────────────────────────────

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


def segment_questions_from_text(
    full_text: str,
    unit_sections: Optional[List[Tuple[int, Optional[str], int, int]]] = None,
) -> List[ExtractedQuestion]:
    questions: List[ExtractedQuestion] = []
    cleaned = clean_text(full_text)

    matches = list(Q_NUM_RE.finditer(cleaned))
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(cleaned)
        q_text = cleaned[match.start(2):end].strip()
        q_text = fix_unicode(q_text)
        marks = extract_marks(q_text)
        q_text = MARKS_RE.sub("", q_text).strip()

        if len(q_text) < 15 or len(q_text) > 1200:
            continue

        parent_text, sub_parts = extract_sub_parts(q_text)
        q_type, has_diag, has_math = classify_question(parent_text)

        # Unit assignment
        unit_num, unit_topic = None, None
        if unit_sections:
            unit_num, unit_topic = assign_unit_to_position(match.start(), unit_sections)

        # Question hash
        norm = normalize_question(parent_text)
        q_hash = compute_question_hash(norm)

        questions.append(ExtractedQuestion(
            text=parent_text,
            question_type=q_type,
            has_diagram=has_diag,
            has_math=has_math,
            sub_parts=sub_parts,
            marks=marks,
            raw_text=q_text,
            unit=unit_num,
            unit_topic=unit_topic,
            question_hash=q_hash,
        ))

    # Fallback: trigger-word line detection
    if len(questions) < 3:
        for line in cleaned.split("\n"):
            line = line.strip()
            if (len(line) > 35
                    and line[0].isupper()
                    and not NOISE_RE.search(line)
                    and any(kw in line.lower() for kw in TRIGGER_WORDS)):
                q_type, has_diag, has_math = classify_question(line)
                norm = normalize_question(line)
                q_hash = compute_question_hash(norm)
                questions.append(ExtractedQuestion(
                    text=line,
                    question_type=q_type,
                    has_diagram=has_diag,
                    has_math=has_math,
                    question_hash=q_hash,
                ))

    # Deduplicate by hash
    seen: set = set()
    unique: List[ExtractedQuestion] = []
    for q in questions:
        if q.question_hash and q.question_hash not in seen:
            seen.add(q.question_hash)
            unique.append(q)
    return unique


# ── Master Pipeline ────────────────────────────────────────────────────────────

def process_pdf(pdf_bytes: bytes) -> Tuple[List[ExtractedQuestion], str, int, PaperMetadata]:
    """
    Master pipeline: bytes → (questions, method_used, page_count, paper_metadata)

    v2 changes:
      - Also runs extract_paper_metadata() on page 1
      - Detects unit sections and tags each question with unit + topic
      - Attaches question_hash to every question
    """
    # Extract paper metadata from header
    paper_meta = extract_paper_metadata(pdf_bytes)

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
                (ocr_pages[i] if i < len(ocr_pages) and len(ocr_pages[i]) > len(page_texts[i])
                 else page_texts[i])
                for i in range(n_pages)
            ]
            method = "hybrid"

    full_text = stitch_pages(page_texts)

    # Detect unit sections
    unit_sections = detect_unit_sections(full_text)

    questions = segment_questions_from_text(full_text, unit_sections)

    logger.info(
        f"process_pdf: {len(questions)} questions | method={method} | pages={n_pages} | "
        f"units_detected={len(unit_sections)} | "
        f"diagrams={sum(1 for q in questions if q.has_diagram)} | "
        f"math={sum(1 for q in questions if q.has_math)} | "
        f"subject={paper_meta.subject_name} code={paper_meta.subject_code}"
    )

    return questions, method, n_pages, paper_meta


def extract_question_type(question_text: str) -> str:
    """Legacy compat."""
    q_type, _, _ = classify_question(question_text)
    return q_type
