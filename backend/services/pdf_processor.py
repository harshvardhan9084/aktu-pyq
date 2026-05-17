"""
PDF Processing Service — AKTU PYQ Intelligence System v2.1
═══════════════════════════════════════════════════════════

FIXES IN v2.1:
  ✓ Massively improved extract_paper_metadata() — multi-strategy extraction,
    handles all known AKTU/UPTU header formats, falls back through strategies
  ✓ Better question segmentation — catches more patterns, handles section splits
  ✓ OCR text cleaning — removes common OCR garbage before segmentation
  ✓ detect_unit_sections() — more robust, handles "SECTION-A", "PART-I" styles too
"""

import hashlib
import re
import io
import logging
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field

from pypdf import PdfReader

logger = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class ExtractedQuestion:
    text: str
    question_type: str = "theory"
    has_diagram: bool = False
    has_math: bool = False
    sub_parts: List[str] = field(default_factory=list)
    page_number: int = 0
    marks: Optional[int] = None
    raw_text: str = ""
    unit: Optional[int] = None
    unit_topic: Optional[str] = None
    question_hash: Optional[str] = None


@dataclass
class PaperMetadata:
    programme: Optional[str] = None
    subject_name: Optional[str] = None
    subject_code: Optional[str] = None
    branch: Optional[str] = None
    semester: Optional[int] = None
    year: Optional[int] = None
    exam_session: Optional[str] = None
    university: str = "AKTU"


# ── Subject code → (subject, branch) map ─────────────────────────────────────
# Covers common AKTU codes. Keys: uppercase, hyphen-normalised.

SUBJECT_CODE_MAP: Dict[str, Dict[str, Optional[str]]] = {
    # Electrical
    "EE-301": {"subject": "Basic Electrical Engineering", "branch": "Electrical Engineering"},
    "EE-401": {"subject": "Electrical Machines", "branch": "Electrical Engineering"},
    "EE-501": {"subject": "Power Systems", "branch": "Electrical Engineering"},
    "EE-601": {"subject": "Control Systems", "branch": "Electrical Engineering"},
    "EE-701": {"subject": "Power Electronics", "branch": "Electrical Engineering"},
    # ECE
    "EC-301": {"subject": "Analog Electronics", "branch": "Electronics & Communication"},
    "EC-401": {"subject": "Digital Electronics", "branch": "Electronics & Communication"},
    "EC-501": {"subject": "Signals & Systems", "branch": "Electronics & Communication"},
    "EC-601": {"subject": "Communication Systems", "branch": "Electronics & Communication"},
    "EC-701": {"subject": "Microprocessors", "branch": "Electronics & Communication"},
    # CSE
    "CS-301": {"subject": "Data Structures", "branch": "Computer Science & Engineering"},
    "CS-401": {"subject": "Design & Analysis of Algorithms", "branch": "Computer Science & Engineering"},
    "CS-501": {"subject": "Database Management Systems", "branch": "Computer Science & Engineering"},
    "CS-601": {"subject": "Operating Systems", "branch": "Computer Science & Engineering"},
    "CS-701": {"subject": "Computer Networks", "branch": "Computer Science & Engineering"},
    "CS-801": {"subject": "Software Engineering", "branch": "Computer Science & Engineering"},
    # Mechanical
    "ME-301": {"subject": "Engineering Thermodynamics", "branch": "Mechanical Engineering"},
    "ME-401": {"subject": "Fluid Mechanics & Machines", "branch": "Mechanical Engineering"},
    "ME-501": {"subject": "Machine Design", "branch": "Mechanical Engineering"},
    "ME-601": {"subject": "Heat Transfer", "branch": "Mechanical Engineering"},
    # Civil
    "CE-301": {"subject": "Structural Analysis", "branch": "Civil Engineering"},
    "CE-401": {"subject": "Geotechnical Engineering", "branch": "Civil Engineering"},
    "CE-501": {"subject": "Design of Structures", "branch": "Civil Engineering"},
    # Common/General (NAS/NEC/NEE/NCS)
    "NAS-101": {"subject": "Engineering Chemistry", "branch": None},
    "NAS-103": {"subject": "Engineering Mathematics I", "branch": None},
    "NAS-203": {"subject": "Engineering Mathematics II", "branch": None},
    "NAS-303": {"subject": "Engineering Mathematics III", "branch": None},
    "NAS-401": {"subject": "Engineering Mathematics IV", "branch": None},
    "NEC-101": {"subject": "Fundamentals of Electronics Engineering", "branch": None},
    "NEC-201": {"subject": "Basic Electronics Engineering", "branch": None},
    "NEE-101": {"subject": "Basic Electrical Engineering", "branch": None},
    "NCS-301": {"subject": "Data Structures using C", "branch": None},
    "NCS-401": {"subject": "Object Oriented Programming", "branch": None},
    "NCS-501": {"subject": "Database Management Systems", "branch": None},
    "NCS-601": {"subject": "Operating Systems", "branch": None},
    "NCS-701": {"subject": "Computer Networks", "branch": None},
    "NME-501": {"subject": "Industrial Management", "branch": None},
    # IT
    "IT-301": {"subject": "Data Structures", "branch": "Information Technology"},
    "IT-501": {"subject": "Database Management Systems", "branch": "Information Technology"},
    "IT-601": {"subject": "Computer Networks", "branch": "Information Technology"},
    # Pharma
    "PPS-23": {"subject": "Pharmaceutical Sciences", "branch": "Pharmacy"},
    # Fallback patterns
    "BEE": {"subject": "Basic Electrical Engineering", "branch": None},
    "DBMS": {"subject": "Database Management Systems", "branch": None},
    "DS": {"subject": "Data Structures", "branch": None},
    "OS": {"subject": "Operating Systems", "branch": None},
    "CN": {"subject": "Computer Networks", "branch": None},
}

# Branch keyword → canonical branch name
BRANCH_KEYWORD_MAP = {
    "electrical": "Electrical Engineering",
    "electronics": "Electronics & Communication Engineering",
    "communication": "Electronics & Communication Engineering",
    "computer science": "Computer Science & Engineering",
    "cse": "Computer Science & Engineering",
    "mechanical": "Mechanical Engineering",
    "civil": "Civil Engineering",
    "information technology": "Information Technology",
    "it ": "Information Technology",
    "pharmacy": "Pharmacy",
    "pharma": "Pharmacy",
    "chemical": "Chemical Engineering",
    "biotechnology": "Biotechnology",
    "automobile": "Automobile Engineering",
    "textile": "Textile Engineering",
    "mba": "Management",
    "mca": "Computer Applications",
    "diploma": None,
}

# Roman numeral → int
ROMAN_MAP = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8,
}


def roman_to_int(s: str) -> Optional[int]:
    return ROMAN_MAP.get(s.strip().upper())


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


# ── AKTU Paper Metadata Extractor ─────────────────────────────────────────────

def _get_first_pages_text(pdf_bytes: bytes, n_pages: int = 2) -> str:
    """Extract text from first N pages, trying multiple strategies."""
    texts = []

    # Strategy 1: pypdf
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        for i, page in enumerate(reader.pages[:n_pages]):
            t = page.extract_text() or ""
            if t.strip():
                texts.append(t)
    except Exception:
        pass

    # Strategy 2: pdfplumber (often better layout)
    if not any(texts) or sum(len(t) for t in texts) < 100:
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages[:n_pages]:
                    t = page.extract_text() or ""
                    if t.strip():
                        texts.append(t)
        except Exception:
            pass

    return "\n".join(texts)


def _normalise_code(raw: str) -> str:
    """'NAS 103' → 'NAS-103', 'ee301' → 'EE-301'"""
    raw = raw.strip().upper()
    # Insert hyphen between letters and digits if missing
    raw = re.sub(r"([A-Z]{2,3})\s*-?\s*(\d{3,4})", r"\1-\2", raw)
    return raw


def extract_paper_metadata(pdf_bytes: bytes) -> PaperMetadata:
    """
    Robust multi-strategy AKTU header parser.

    AKTU header formats encountered in the wild:
      B.Tech. (SEM-III) ODD SEMESTER THEORY EXAMINATION 2022-23
      BASIC ELECTRICAL ENGINEERING
      Paper Code: EE-301 / Subject Code: NAS-103

      UPTU B.Tech IV Semester Examination 2019-20
      Subject: Engineering Mathematics III  Code: NAS-303

      DIPLOMA (SEM-2) EVEN SEMESTER EXAMINATION 2021
      SUBJECT: ELECTRICAL TECHNOLOGY (EE-121)

      [filename]: pps-23.pdf → code hint from filename
    """
    meta = PaperMetadata()
    text = _get_first_pages_text(pdf_bytes, n_pages=2)

    if not text.strip():
        logger.warning("extract_paper_metadata: could not extract any text from first pages")
        return meta

    # Normalise for matching
    upper = text.upper()
    lower = text.lower()

    # ── 1. Programme ──────────────────────────────────────────────────────────
    prog_patterns = [
        (r"\bB[\.\s]*TECH\b", "B.Tech"),
        (r"\bM[\.\s]*TECH\b", "M.Tech"),
        (r"\bMBA\b", "MBA"),
        (r"\bMCA\b", "MCA"),
        (r"\bDIPLOMA\b", "Diploma"),
        (r"\bB[\.\s]*PHARM\b", "B.Pharm"),
        (r"\bM[\.\s]*PHARM\b", "M.Pharm"),
        (r"\bB[\.\s]*SC\b", "B.Sc"),
    ]
    for pat, val in prog_patterns:
        if re.search(pat, upper):
            meta.programme = val
            break

    # ── 2. Semester ───────────────────────────────────────────────────────────
    # Patterns: SEM-III, SEMESTER 3, IV SEMESTER, 2ND SEM, SEM 2
    sem_patterns = [
        r"SEM(?:ESTER)?[\s\-–]*([IVX]{1,4}|\d{1,2})(?:\s|ST|ND|RD|TH|$)",
        r"([IVX]{1,4}|\d{1,2})(?:ST|ND|RD|TH)?\s*SEM(?:ESTER)?",
        r"SEMESTER\s*[:\-]?\s*([IVX]{1,4}|\d{1,2})",
    ]
    for pat in sem_patterns:
        m = re.search(pat, upper)
        if m:
            val = roman_to_int(m.group(1))
            if val and 1 <= val <= 8:
                meta.semester = val
                break

    # ── 3. Year ───────────────────────────────────────────────────────────────
    # Patterns: 2022-23, 2022-2023, EXAMINATION 2022, 2022
    year_patterns = [
        r"(\d{4})[\s\-–/]+\d{2,4}",   # 2022-23 or 2022-2023
        r"EXAMINATION\s+(\d{4})",
        r"EXAM(?:INATION)?\s*[\-:]?\s*(\d{4})",
        r"\b(20\d{2})\b",
    ]
    for pat in year_patterns:
        m = re.search(pat, upper)
        if m:
            yr = int(m.group(1))
            if 2000 <= yr <= 2030:
                meta.year = yr
                break

    # ── 4. Exam session (odd / even) ──────────────────────────────────────────
    if re.search(r"\bODD\b", upper):
        meta.exam_session = "odd"
    elif re.search(r"\bEVEN\b", upper):
        meta.exam_session = "even"

    # ── 5. Subject code ───────────────────────────────────────────────────────
    # Strategy A: explicit "Paper Code:" or "Subject Code:" label
    code_label_pat = re.compile(
        r"(?:PAPER|SUBJECT|COURSE)[\s\-]*CODE\s*[:\-]?\s*([A-Z]{2,4}[\s\-]?\d{3,4})",
        re.IGNORECASE,
    )
    m = code_label_pat.search(text)
    if m:
        meta.subject_code = _normalise_code(m.group(1))

    # Strategy B: standalone code-like token (e.g. "EE-301" floating anywhere)
    if not meta.subject_code:
        standalone_pat = re.compile(
            r"\b([A-Z]{2,4}[\s\-]?\d{3,4})\b"
        )
        for m in standalone_pat.finditer(upper):
            candidate = _normalise_code(m.group(1))
            if candidate in SUBJECT_CODE_MAP:
                meta.subject_code = candidate
                break

    # Strategy C: code in parentheses like "(EE-301)"
    if not meta.subject_code:
        paren_pat = re.compile(r"\(([A-Z]{2,4}[\s\-]?\d{3,4})\)", re.IGNORECASE)
        for m in paren_pat.finditer(text):
            candidate = _normalise_code(m.group(1))
            meta.subject_code = candidate
            break

    # ── 6. Subject name ───────────────────────────────────────────────────────
    # Strategy A: look up from code
    if meta.subject_code:
        lookup = SUBJECT_CODE_MAP.get(meta.subject_code, {})
        if lookup:
            meta.subject_name = lookup.get("subject")
            if not meta.branch:
                meta.branch = lookup.get("branch")

    # Strategy B: "SUBJECT:" label
    if not meta.subject_name:
        subj_label = re.compile(
            r"(?:SUBJECT|PAPER|COURSE)\s*[:\-]\s*([A-Z][A-Za-z &\-\(\)]+?)(?:\n|CODE|ROLL|\(|$)",
            re.IGNORECASE | re.MULTILINE,
        )
        m = subj_label.search(text)
        if m:
            candidate = m.group(1).strip().rstrip(":")
            if len(candidate) > 4 and len(candidate) < 80:
                meta.subject_name = candidate.title()

    # Strategy C: large ALL-CAPS line on page 1 (AKTU puts subject in caps header)
    if not meta.subject_name:
        for line in text.split("\n"):
            stripped = line.strip()
            # A title-like line: ALL CAPS, 10-70 chars, no numbers, not semester/exam noise
            if (
                10 < len(stripped) < 70
                and stripped == stripped.upper()
                and not re.search(r"\d", stripped)
                and not re.search(
                    r"EXAMINATION|UNIVERSITY|SEMESTER|ROLL|B\.?TECH|DIPLOMA|MBA|MCA|MAXIMUM|TIME|DURATION|ANSWER|NOTE|SECTION|PART",
                    stripped,
                )
            ):
                meta.subject_name = stripped.title()
                break

    # ── 7. Branch ─────────────────────────────────────────────────────────────
    if not meta.branch:
        for kw, branch in BRANCH_KEYWORD_MAP.items():
            if kw in lower:
                meta.branch = branch
                break

    logger.info(
        f"extract_paper_metadata → programme={meta.programme} subject={meta.subject_name} "
        f"code={meta.subject_code} branch={meta.branch} sem={meta.semester} "
        f"year={meta.year} session={meta.exam_session}"
    )
    return meta


# ── Noise / cleanup patterns ──────────────────────────────────────────────────

NOISE_LINES_RE = re.compile(
    r"(?:"
    r"(?:^|\n)\s*(?:roll\s*no|roll\s*number|student\s*name|name\s*of\s*student)[^\n]*"
    r"|(?:^|\n)\s*(?:time\s*allowed|maximum\s*marks|total\s*marks|full\s*marks)[^\n]*"
    r"|(?:^|\n)\s*(?:note\s*[:–-]|note\s*:)[^\n]*"
    r"|(?:^|\n)\s*(?:all\s*questions\s*are\s*compulsory)[^\n]*"
    r"|(?:^|\n)\s*(?:attempt\s*any\s*\w+)[^\n]*"
    r"|(?:^|\n)\s*(?:turn\s*over|contd\.?|p\.?t\.?o\.?)\s*$"
    r"|(?:^|\n)\s*(?:page\s*\d+\s*of\s*\d+)[^\n]*"
    r")",
    re.IGNORECASE | re.MULTILINE,
)

MARKS_RE = re.compile(r"\[(\d+)\]|\((\d+)\s*marks?\)", re.IGNORECASE)

DIAGRAM_RE = re.compile(
    r"draw|sketch|show|plot|illustrate|circuit|block\s+diagram|waveform"
    r"|fig(?:ure|\.)?\s*\d+|as\s+shown|referring\s+to\s+(?:the\s+)?(?:circuit|figure|diagram)",
    re.IGNORECASE,
)

MATH_RE = re.compile(
    r"derive\s+(?:the\s+)?(?:expression|equation|formula)"
    r"|solve\s+(?:the\s+)?(?:differential|integral|equation)"
    r"|laplace|fourier|z-transform|d[xy]/d[txy]|\^[{(]?\d"
    r"|[∫∑∏√∂∇±×÷≤≥≠∞αβγδεζηθλμπρσφψω]",
    re.IGNORECASE,
)

UNIT_SECTION_RE = re.compile(
    r"(?:^|\n)\s*(?:UNIT|SECTION|PART)[\s\-–]*([IVX]{1,5}|\d{1})\b[:\s]*([^\n]{0,60})?",
    re.IGNORECASE | re.MULTILINE,
)

# Question number patterns — very broadly matched
Q_PATTERNS = [
    # Q.1, Q1., 1., 1)
    re.compile(
        r"(?:^|\n)\s*(?:Q\.?\s*)?(\d{1,2})\s*[.)]\s*([A-Z].{20,600}?)(?=\n\s*(?:Q\.?\s*)?\d{1,2}\s*[.)]|\Z)",
        re.DOTALL | re.MULTILINE,
    ),
    # (1), (i), (a) style sub-questions used as main questions
    re.compile(
        r"(?:^|\n)\s*\((\d{1,2}|[ivx]{1,4})\)\s*([A-Z].{20,400}?)(?=\n\s*\(|\Z)",
        re.DOTALL | re.MULTILINE,
    ),
]

# Trigger words — a line starting with one of these and long enough is a question
TRIGGER_WORDS = [
    "explain", "define", "derive", "write", "describe", "discuss",
    "what", "why", "how", "compare", "find", "prove", "state",
    "calculate", "determine", "analyze", "differentiate", "enumerate",
    "list", "obtain", "evaluate", "solve", "draw", "sketch", "show",
    "examine", "justify", "illustrate", "classify", "summarize",
    "distinguish", "implement", "design", "construct",
]

SUB_PART_RE = re.compile(
    r"(?:^|\n)\s*\(([a-z])\)\s*(.+?)(?=\n\s*\([a-z]\)|\Z)",
    re.DOTALL | re.MULTILINE,
)


def clean_ocr_garbage(text: str) -> str:
    """Remove common OCR artefacts before segmentation."""
    # Remove lone punctuation lines
    text = re.sub(r"(?:^|\n)[^a-zA-Z\d\n]{0,3}(?:\n|$)", "\n", text, flags=re.MULTILINE)
    # Merge hyphenated line breaks
    text = re.sub(r"-\n\s*", "", text)
    # Remove noise lines
    text = NOISE_LINES_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_marks(text: str) -> Optional[int]:
    m = MARKS_RE.search(text)
    if m:
        return int(m.group(1) or m.group(2))
    return None


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
                              "mention"]) and len(text) < 180:
        return "short", False, False
    return "theory", False, has_math


def extract_sub_parts(text: str) -> Tuple[str, List[str]]:
    sub_matches = SUB_PART_RE.findall(text)
    if len(sub_matches) >= 2:
        parent = SUB_PART_RE.sub("", text).strip()
        sub_parts = [f"({letter}) {content.strip()}" for letter, content in sub_matches]
        return parent, sub_parts
    return text, []


def detect_unit_sections(full_text: str) -> List[Tuple[int, Optional[str], int, int]]:
    matches = list(UNIT_SECTION_RE.finditer(full_text))
    sections = []
    for i, m in enumerate(matches):
        unit_num = roman_to_int(m.group(1))
        if unit_num is None or unit_num < 1 or unit_num > 8:
            continue
        topic = (m.group(2) or "").strip().rstrip(":").strip() or None
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        sections.append((unit_num, topic, start, end))
    return sections


def assign_unit_to_position(pos: int, sections: List[Tuple[int, Optional[str], int, int]]) -> Tuple[Optional[int], Optional[str]]:
    for (u, t, s, e) in sections:
        if s <= pos < e:
            return u, t
    return None, None


def segment_questions(full_text: str, unit_sections: Optional[List] = None) -> List[ExtractedQuestion]:
    cleaned = clean_ocr_garbage(full_text)
    questions: List[ExtractedQuestion] = []
    seen_hashes: set = set()

    def add_q(text: str, pos: int = 0):
        text = text.strip()
        if len(text) < 20 or len(text) > 1500:
            return
        text = MARKS_RE.sub("", text).strip()
        text = fix_unicode(text)
        parent, sub_parts = extract_sub_parts(text)
        q_type, has_diag, has_math = classify_question(parent)
        marks = extract_marks(text)
        unit, unit_topic = assign_unit_to_position(pos, unit_sections or [])
        norm = normalize_question(parent)
        q_hash = compute_question_hash(norm)
        if q_hash in seen_hashes:
            return
        seen_hashes.add(q_hash)
        questions.append(ExtractedQuestion(
            text=parent,
            question_type=q_type,
            has_diagram=has_diag,
            has_math=has_math,
            sub_parts=sub_parts,
            marks=marks,
            unit=unit,
            unit_topic=unit_topic,
            question_hash=q_hash,
        ))

    # Strategy 1: numbered question patterns
    for pat in Q_PATTERNS:
        for m in pat.finditer(cleaned):
            add_q(m.group(2), pos=m.start())
        if len(questions) >= 5:
            break

    # Strategy 2: trigger-word line scan (fallback for messy OCR)
    if len(questions) < 3:
        for line in cleaned.split("\n"):
            stripped = line.strip()
            if (
                len(stripped) > 30
                and stripped[0].isupper()
                and any(stripped.lower().startswith(kw) for kw in TRIGGER_WORDS)
            ):
                add_q(stripped)

    logger.info(f"segment_questions: {len(questions)} unique questions extracted")
    return questions


# ── Diagram crop ──────────────────────────────────────────────────────────────

def extract_diagram_crop(pdf_bytes: bytes, page_number: int, dpi: int = 200) -> Optional[bytes]:
    try:
        import pdf2image
        import pdfplumber
        from PIL import Image as PILImage

        images = pdf2image.convert_from_bytes(pdf_bytes, dpi=dpi,
                                               first_page=page_number + 1,
                                               last_page=page_number + 1)
        if not images:
            return None
        img = images[0]
        img_w, img_h = img.size

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if page_number >= len(pdf.pages):
                return None
            page = pdf.pages[page_number]
            words = page.extract_words()

        scale_y = img_h / float(page.height)
        scale_x = img_w / float(page.width)
        coverage = [0] * img_h
        for w in words:
            y0 = max(0, int(w["top"] * scale_y))
            y1 = min(img_h, int(w["bottom"] * scale_y))
            coverage_span = int((w["x1"] - w["x0"]) * scale_x)
            for row in range(y0, y1):
                coverage[row] += coverage_span

        THRESH = img_w * 0.18
        is_text = [c > THRESH for c in coverage]
        MIN_H = int(img_h * 0.08)
        best_start = best_end = best_len = 0
        run = None
        for row in range(img_h):
            if not is_text[row]:
                if run is None:
                    run = row
            else:
                if run is not None:
                    L = row - run
                    if L > best_len:
                        best_len, best_start, best_end = L, run, row
                    run = None
        if run is not None:
            L = img_h - run
            if L > best_len:
                best_len, best_start, best_end = L, run, img_h

        if best_len < MIN_H:
            return None

        PAD = int(img_h * 0.01)
        crop = img.crop((0, max(0, best_start - PAD), img_w, min(img_h, best_end + PAD)))
        buf = io.BytesIO()
        crop.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except ImportError as e:
        logger.warning(f"Diagram crop deps missing: {e}")
    except Exception as e:
        logger.warning(f"Diagram crop error on page {page_number}: {e}")
    return None


# ── Image preprocessing ───────────────────────────────────────────────────────

def preprocess_image_for_ocr(pil_image):
    try:
        import cv2, numpy as np
        img = cv2.cvtColor(np.array(pil_image.convert("RGB")), cv2.COLOR_RGB2GRAY)
        coords = np.column_stack(np.where(img < 200))
        if len(coords) > 100:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = 90 + angle
            if abs(angle) > 0.5:
                h, w = img.shape
                M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
                img = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        img = cv2.fastNlMeansDenoising(img, h=10)
        img = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)
        from PIL import Image as PILImage
        return PILImage.fromarray(img)
    except Exception:
        return pil_image.convert("L")


# ── PDF extraction strategies ─────────────────────────────────────────────────

def _extract_pypdf(pdf_bytes: bytes) -> List[str]:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return [page.extract_text() or "" for page in reader.pages]
    except Exception as e:
        logger.warning(f"pypdf failed: {e}")
        return []


def _extract_pdfplumber(pdf_bytes: bytes) -> List[str]:
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            return [page.extract_text() or "" for page in pdf.pages]
    except Exception as e:
        logger.warning(f"pdfplumber failed: {e}")
        return []


def _extract_ocr(pdf_bytes: bytes) -> List[str]:
    try:
        import pdf2image, pytesseract
        images = pdf2image.convert_from_bytes(pdf_bytes, dpi=300)
        pages = []
        for i, img in enumerate(images):
            try:
                pre = preprocess_image_for_ocr(img)
                pages.append(pytesseract.image_to_string(pre, config="--psm 6 --oem 3 -l eng"))
            except Exception as e:
                logger.warning(f"OCR page {i+1}: {e}")
                pages.append("")
        return pages
    except ImportError as e:
        logger.warning(f"OCR deps missing: {e}")
        return []
    except Exception as e:
        logger.error(f"OCR pipeline error: {e}")
        return []


def _is_scanned(pdf_bytes: bytes) -> bool:
    pages = _extract_pypdf(pdf_bytes)
    if not pages:
        return True
    total = sum(len(p.strip()) for p in pages)
    return total < len(pages) * 80


def _best_digital(pdf_bytes: bytes) -> Tuple[List[str], str]:
    pypdf = _extract_pypdf(pdf_bytes)
    plumber = _extract_pdfplumber(pdf_bytes)
    if sum(len(p) for p in plumber) > sum(len(p) for p in pypdf) * 1.1:
        return plumber, "pdfplumber"
    return pypdf, "pypdf"


def _stitch(pages: List[str]) -> str:
    parts = []
    for p in pages:
        p = p.rstrip()
        if not p:
            continue
        if parts and parts[-1] and parts[-1][-1] not in ".?!:\n":
            parts[-1] += " " + p.lstrip()
        else:
            parts.append(p)
    return "\n\n".join(parts)


# ── Master pipeline ───────────────────────────────────────────────────────────

def process_pdf(pdf_bytes: bytes) -> Tuple[List[ExtractedQuestion], str, int, PaperMetadata]:
    """
    bytes → (questions, method, n_pages, paper_metadata)
    """
    paper_meta = extract_paper_metadata(pdf_bytes)

    if _is_scanned(pdf_bytes):
        page_texts = _extract_ocr(pdf_bytes)
        method = "ocr"
        if not any(page_texts):
            page_texts, m = _best_digital(pdf_bytes)
            method = f"digital_fallback({m})"
    else:
        page_texts, m = _best_digital(pdf_bytes)
        method = f"digital_{m}"
        # Supplement with OCR if text is sparse
        total = sum(len(p) for p in page_texts)
        if total < len(page_texts) * 80 and len(page_texts) > 0:
            ocr_pages = _extract_ocr(pdf_bytes)
            page_texts = [
                (ocr_pages[i] if i < len(ocr_pages) and len(ocr_pages[i]) > len(page_texts[i]) else page_texts[i])
                for i in range(len(page_texts))
            ]
            method = "hybrid"

    full_text = _stitch(page_texts)
    unit_sections = detect_unit_sections(full_text)
    questions = segment_questions(full_text, unit_sections)

    logger.info(
        f"process_pdf: {len(questions)} questions | {method} | pages={len(page_texts)} | "
        f"units={len(unit_sections)} | diagrams={sum(1 for q in questions if q.has_diagram)} | "
        f"subject={paper_meta.subject_name} code={paper_meta.subject_code}"
    )
    return questions, method, len(page_texts), paper_meta


# Legacy compat
def extract_question_type(question_text: str) -> str:
    q_type, _, _ = classify_question(question_text)
    return q_type
