#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aktu_pyq_extractor.py  --  AKTU PYQ tiered extraction pipeline (v1)
=====================================================================
Pipeline per PDF:
  Tier 0  deterministic cleanup    : char filters (diagonal watermark, junk),
                                     line rebuild, ftfy mojibake fix, Hindi strip
                                     (Hindi = duplicate alternates -> discarded),
                                     header/footer strip, metadata capture
  Tier 1  fuzzy parser (no rules)  : multi-signal question segmentation, marks
                                     inference (section math / trailing cols),
                                     OR choice grouping, confidence + self-checks
  GATE                             : confidence >= threshold -> ACCEPT (0 AI tokens)
  Tier 2  AI repair (optional)     : only gate-failed papers -> Gemma strict-JSON
                                     repair, cached by (file_hash, prompt_version)
  Tier 3  review queue             : still-bad papers -> needs_review outbox

Extras: diagram detection + PNG crop (pypdfium2), Supabase push (PostgREST REST,
no SDK needed), resume state, sharding, soft-deadline (GitHub Actions 6h guard).

Usage:
  python3 aktu_pyq_extractor.py --pilot 6 --dir aktu-pyq/unstructured
  python3 aktu_pyq_extractor.py --dir aktu-pyq/unstructured --ai --db
  python3 aktu_pyq_extractor.py --list-models
  (full docs in EXTRACTION_GUIDE.md)

Env vars:
  GEMMA_API_KEY          Google AI Studio key (Tier 2)
  GEMMA_MODEL            model id (default: gemma-4-31B as reported by owner;
                         verify with --list-models)
  SUPABASE_URL           https://xxxx.supabase.co
  SUPABASE_SERVICE_KEY   service_role key (server-side only, NEVER in browser)
"""
import argparse, hashlib, json, os, re, sys, time, uuid, difflib
from collections import defaultdict
from datetime import datetime, timezone

try:
    import pdfplumber
except ImportError:
    sys.exit("pdfplumber missing: pip install pdfplumber pypdfium2 pillow requests ftfy")

try:
    import ftfy
    HAVE_FTFY = True
except ImportError:
    HAVE_FTFY = False

try:
    import requests
    HAVE_REQUESTS = True
except ImportError:
    HAVE_REQUESTS = False

try:
    import pypdfium2 as pdfium
    HAVE_PDFIUM = True
except ImportError:
    HAVE_PDFIUM = False

try:
    import pytesseract
    from pytesseract import Output
    HAVE_TESSERACT = True
except ImportError:
    HAVE_TESSERACT = False

PIL_OK = True
try:
    from PIL import Image
except ImportError:
    PIL_OK = False

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------
DEV_RANGE = re.compile(r'[\u0900-\u097F]')
CID_JUNK  = re.compile(r'\(cid:\d+\)')
MARKS_MATH = re.compile(r'(\d{1,2})\s*[xX\u00d7]\s*(\d{1,2})\s*=\s*(\d{1,3})')
SECTION_RX = re.compile(r'^\s*SECTION\s*[-.:]?\s*([A-Z])\b', re.I)
UNIT_RX    = re.compile(r'^\s*UNIT\s*[-.\s]?\s*(\d+|I{1,3}|IV|V|VI{1,3})\b', re.I)
OR_RX      = re.compile(r'^\s*(?:OR|Or|oR|0R)\s*:?\s*$')
ATTEMPT_RX = re.compile(r'^\s*(?:Q?\s*(\d{1,2})\s*[.:)]?\s*)?Attempt\s*(all|any|the)\b', re.I)
SUB_PAREN_RX = re.compile(r'^\s*\(?([a-jA-J])\s*[).:\]]\s*')          # (a) / a. / a)
MAIN_NUM_RX  = re.compile(r'^\s*(\d{1,2})\s*[.)]\s+')
VALID_MARKS  = {1,2,3,4,5,6,7,8,9,10,12,14,15,16,20}
FOOTER_PAT   = re.compile(r'(AKTU_QP|Printed Page|Printed Pages)', re.I)
PROMPT_VERSION = 'v1-gemma-repair'

# Kruti-Dev signature tokens (legacy Devanagari fonts map to latin-ish chars)
KRUTI_TOKENS = [' iz\u201d', 'iz\u201d', 'mRrj', 'fuEu', 'lHkh', 'vFkok', 'fgUnh', 'vaxzsth',
                'la{ksi', 'mi;qDr', 'iz;ksx', 'nhft,', 'dja', 'esa ', ' dk ', ' ds ',
                ' dks ', ',oa ', 'gSa', 'gks']
def _kruti_hits(s):
    t = ' ' + s + ' '
    n = 0
    for tok in set(KRUTI_TOKENS):
        n += t.count(tok)
    return n

def log(msg):
    print(msg, flush=True)

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

# ---------------------------------------------------------------------------
# Tier 0 : text cleanup
# ---------------------------------------------------------------------------
def keep_char(o):
    """Char-level surgical filter: drop diagonal-watermark letters (tall+isolated),
    zero-width junk, control chars."""
    if o.get('object_type') != 'char':
        return True
    t = o.get('text', '')
    if not t or t.isspace() or ord(t[0]) < 32:
        return False
    h = o.get('bottom', 0) - o.get('top', 0)
    return h <= 20.0 or o.get('size', 0) > 15  # big title fonts stay; tall strays go

def assemble_lines(page):
    """Words -> lines by top clustering (tol 2.8pt). Returns [(top,bottom,text)]."""
    flt = page.filter(keep_char)
    words = flt.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=1.6) \
        if hasattr(flt, 'extract_words') else page.extract_words(x_tolerance=1.6)
    if not words:
        return []
    words.sort(key=lambda w: (round(w['top'], 1), w['x0']))
    lines, cur, cur_top = [], [], None
    for w in words:
        if cur_top is None or abs(w['top'] - cur_top) <= 2.8:
            cur.append(w); cur_top = w['top'] if cur_top is None else cur_top
        else:
            cur.sort(key=lambda x: x['x0'])
            lines.append((cur[0]['top'], max(x['bottom'] for x in cur),
                          ' '.join(x['text'] for x in cur)))
            cur, cur_top = [w], w['top']
    if cur:
        cur.sort(key=lambda x: x['x0'])
        lines.append((cur[0]['top'], max(x['bottom'] for x in cur),
                      ' '.join(x['text'] for x in cur)))
    return lines

def is_hindi_line(s):
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    dev = sum(1 for c in s if DEV_RANGE.match(c))
    if dev / max(1, len(letters)) > 0.25:
        return True
    return _kruti_hits(s) >= 2

def ocr_lines(pdf_path, dpi=200):
    """Scanned-paper fallback: rasterize + tesseract. Returns same line dicts."""
    if not (HAVE_PDFIUM and HAVE_TESSERACT):
        return [], {'ocr': 'unavailable'}
    doc = pdfium.PdfDocument(pdf_path)
    out = []
    try:
        for pno in range(len(doc)):
            img = doc[pno].render(scale=dpi / 72).to_pil()
            data = pytesseract.image_to_data(img, output_type=Output.DICT)
            rows = defaultdict(list)
            for i, txt in enumerate(data['text']):
                if not txt.strip() or int(data.get('conf', ['0'])[i]) < 35:
                    continue
                key = round(data['top'][i] / (14 * dpi / 72))   # ~14pt line buckets
                rows[key].append((data['left'][i], txt))
            for key in sorted(rows):
                ws = sorted(rows[key])
                out.append({'page': pno + 1,
                            'top': key * (14 * dpi / 72),
                            'bottom': key * (14 * dpi / 72) + 14 * dpi / 72,
                            'text': ' '.join(t for _, t in ws)})
    finally:
        doc.close()
    return out, {'ocr': 'done'}

def tier0(pdf_path):
    """Extract clean lines + metadata + per-page geometry."""
    meta, pages = {}, []
    with pdfplumber.open(pdf_path) as pdf:
        n_pages = len(pdf.pages)
        for pno, page in enumerate(pdf.pages, 1):
            raw = page.extract_text() or ''
            m = re.search(r'(Sub\s*Code|Subject\s*Code)\s*[:\-]?\s*([A-Z]{2,4}[- ]?\d{3}[A-Z]?)', raw)
            if m and 'code' not in meta:
                meta['code'] = m.group(2).replace(' ', '-')
            m = re.search(r'THEORY\s+EXAMINATION\s+(\d{4}-\d{2})', raw)
            if m and 'year' not in meta:
                meta['year'] = m.group(1)
            m = re.search(r'Total\s*Marks\s*[:%]?\s*(\d+)', raw)
            if m and 'total_marks' not in meta:
                meta['total_marks'] = int(m.group(1))
            m = re.search(r'Paper\s*Id\s*[:\-]?\s*(\d+)', raw)
            if m and 'paper_id' not in meta:
                meta['paper_id'] = m.group(1)
            drawings = list(page.images) + list(page.curves) + list(page.lines) + list(page.rects)
            pages.append({'no': pno, 'lines': assemble_lines(page), 'drawings': drawings,
                          'w': page.width, 'h': page.height})
    # flatten with page tracking, drop junk lines
    out, stats = [], {'hindi': 0, 'junk': 0, 'cid': 0}
    for pg in pages:
        for (top, bot, text) in pg['lines']:
            s = CID_JUNK.sub(' ', text)
            if s != text:
                stats['cid'] += 1
            s = re.sub(r'\s+', ' ', s).strip()
            if not s:
                continue
            if FOOTER_PAT.match(s) or re.fullmatch(r'[\W\d\s]{1,4}', s):
                stats['junk'] += 1
                continue
            if is_hindi_line(s):
                stats['hindi'] += 1
                continue
            if HAVE_FTFY:
                s = ftfy.fix_text(s)
            out.append({'page': pg['no'], 'top': top, 'bottom': bot, 'text': s})
    meta['n_pages'] = n_pages
    if len(out) < 25:
        # no usable text layer -> OCR fallback (scanned papers)
        ocr, ostats = ocr_lines(pdf_path)
        if ocr:
            cleaned = []
            for l in ocr:
                s = re.sub(r'\s+', ' ', l['text']).strip()
                if not s or FOOTER_PAT.match(s) or re.fullmatch(r'[\W\d\s]{1,4}', s):
                    continue
                if is_hindi_line(s):
                    stats['hindi'] += 1
                    continue
                cleaned.append(l)
            stats.update(ostats)
            meta['is_text_layer'] = False
            return cleaned, meta, stats, pages
        stats['ocr'] = ostats.get('ocr', 'unavailable')
    return out, meta, stats, pages

# ---------------------------------------------------------------------------
# Tier 1 : fuzzy parser
# ---------------------------------------------------------------------------
def close_section(line):
    """Fuzzy SECTION-A header match (handles 'SECTIOEN B' class typos)."""
    head = line[:12].upper()
    if re.match(r'^\s*SECTION\s*[-.:]?\s*[A-Z]', line, re.I):
        return SECTION_RX.match(line).group(1).upper()
    if 'SECTI' in head and len(line) < 30:
        m = re.search(r'([A-Z])\s*$', line.strip())
        if m:
            return m.group(1)
    return None

def parse_paper(lines, meta):
    """Fuzzy multi-signal parse -> dict(paper, questions, checks, confidence)."""
    questions, sections, notes = [], [], []
    section, unit, marks_spec = None, None, None
    pending_choice = None
    pairing_open = False
    cur = None

    def flush():
        nonlocal cur, pairing_open
        if cur and len(cur['text']) >= 15:
            if pairing_open and questions and questions[-1].get('choice_group') is None \
               and cur.get('choice_group') is None \
               and questions[-1].get('section') == cur.get('section'):
                g = uuid.uuid4()
                questions[-1]['choice_group'] = g
                cur['choice_group'] = g
                pairing_open = False
            questions.append(cur)
        elif cur:
            # too short: prepend to previous question (continuation junk)
            if questions and cur['text']:
                questions[-1]['text'] = (questions[-1]['text'] + ' ' + cur['text']).strip()
        cur = None

    for ln in lines:
        s = ln['text']
        sec = close_section(s)
        if sec:
            flush(); section, marks_spec = sec, None
            sections.append(sec); continue
        um = UNIT_RX.match(s)
        if um:
            flush()
            u = um.group(1)
            unit = int(u) if u.isdigit() else {'I':1,'II':2,'III':3,'IV':4,'V':5,'VI':6,'VII':7,'VIII':8}.get(u.upper())
            continue
        if section is None and re.search(r'THEORY EXAM|B\.?\s*TECH|Time\s*:|Total Marks|'
                                         r'Sub\s*Code|Paper\s*Id|Roll\s*No|\bSEM\b', s, re.I):
            continue
        if OR_RX.match(s):
            pending_choice = uuid.uuid4()          # next question shares group w/ prev
            continue
        if re.match(r'^\s*(Note|uksV)\b', s, re.I):
            continue
        am = ATTEMPT_RX.match(s)
        if am:
            flush()
            pairing_open = 'any one' in s.lower()
            mm = MARKS_MATH.search(s)
            if mm:
                marks_spec = int(mm.group(1))       # "2 x 7 = 14" -> each part 2 marks
            notes.append(s)
            continue
        sm = re.match(r'^\s*\(([a-jA-J])\s*[).:\]]\s*(.+)$', s)          # (a) text
        sm2 = re.match(r'^\s*([a-jA-J])\s*[.:]\s+(.+)$', s) if (not sm and section) else None  # a. text
        mm = MAIN_NUM_RX.match(s)
        is_table_row = bool(re.search(r'\s(\d{1,2})\s+\d{1,2}\s*$', s)) and not sm and not sm2
        if sm or sm2:
            letter, rest = (sm.group(1), sm.group(2)) if sm else (sm2.group(1), sm2.group(2))
            rest = rest.strip()
            qmarks = None
            tn = re.search(r'\s(\d{1,2})\s+(\d{1,2})\s*$', rest)   # trailing "10 3" marks+CO cols
            if tn:
                cand = int(tn.group(1))
                if cand in VALID_MARKS:
                    qmarks, rest = cand, rest[:tn.start()].rstrip()
            flush()
            cur = {'label': letter.lower(), 'text': rest, 'marks': qmarks or marks_spec,
                   'section': section, 'unit': unit,
                   'choice_group': pending_choice, 'lines': [ln], 'page': ln['page'],
                   'top': ln['top']}
            pending_choice = None
            continue
        if mm and section and not cur:
            # main numbered question without letter (older format / FAM-3)
            cur = {'label': mm.group(1), 'text': s[mm.end():].strip(), 'marks': None,
                   'section': section, 'unit': unit, 'choice_group': None,
                   'lines': [ln], 'page': ln['page'], 'top': ln['top']}
            continue
        if cur is not None:
            # continuation of current question
            if is_table_row and len(cur['text']) > 30:
                trail = re.search(r'(\d{1,2})\s+\d{1,2}\s*$', s)
                if trail and cur.get('marks') is None:
                    cur['marks'] = int(trail.group(1))   # trailing "10 3" cols
                continue                                  # drop CO col noise
            cur['text'] += ' ' + s
            cur['lines'].append(ln)
        elif is_table_row or re.fullmatch(r'Q\s*no\.?.*Question.*Marks.*', s, re.I):
            continue                                       # table header / stray row
        elif len(s) < 25 and not any(c.isalpha() for c in s):
            continue
        else:
            # FAM-3: "1. Question text ... (2 marks)" as its own start
            m3 = re.match(r'^\s*(\d{1,2})\s*[.)]\s+(.+)$', s)
            if m3 and section and len(m3.group(2)) > 12:
                flush()
                cur = {'label': m3.group(1), 'text': m3.group(2).strip(), 'marks': None,
                       'section': section, 'unit': unit, 'choice_group': None,
                       'lines': [ln], 'page': ln['page'], 'top': ln['top']}
                mm3 = re.search(r'[\(\[]\s*(\d{1,2})\s*(?:marks?|mks?)?\s*[\)\]]', s, re.I)
                if mm3:
                    cur['marks'] = int(mm3.group(1))
    flush()

    # ---- self checks + confidence ----
    n = len(questions)
    with_marks = [q for q in questions if q['marks'] in VALID_MARKS]
    frac_marks = len(with_marks) / n if n else 0.0
    count_ok = 5 <= n <= 60
    len_ok = sum(1 for q in questions if len(q['text']) >= 15) / n if n else 0
    sec_ok = 1.0 if sections else 0.0
    conf = round(0.40 * frac_marks + 0.25 * (1.0 if count_ok else max(0, 1 - abs(n - 20) / 40))
                 + 0.20 * len_ok + 0.15 * sec_ok, 3)
    checks = {'questions': n, 'frac_marks': round(frac_marks, 2), 'count_ok': count_ok,
              'len_ok': round(len_ok, 2), 'sections': sections, 'notes': len(notes)}
    return {'questions': questions, 'checks': checks, 'confidence': conf,
            'meta': meta, 'notes': notes}

def infer_diagram_flags(parsed, lines_by_page):
    """Keyword heuristic -> has_diagram; keep per-question band for cropping."""
    KW = re.compile(r'\b(draw|sketch|figure|diagram|graph|circuit|waveform|plot|'
                    r'characteristic curve|block diagram|flow ?chart|label)\b', re.I)
    for q in parsed['questions']:
        q['has_diagram'] = bool(KW.search(q['text']))
    return parsed

# ---------------------------------------------------------------------------
# Tier 2 : Gemma repair (Google AI Studio / Generative Language REST)
# ---------------------------------------------------------------------------
GEMMA_BASE = 'https://generativelanguage.googleapis.com/v1beta'

def list_models(api_key):
    if not HAVE_REQUESTS:
        sys.exit('requests missing')
    r = requests.get(f'{GEMMA_BASE}/models', params={'key': api_key}, timeout=30)
    r.raise_for_status()
    for m in r.json().get('models', []):
        if 'generateContent' in m.get('supportedGenerationMethods', []):
            print(f"  {m['name']}   input={m.get('inputTokenLimit','?')} output={m.get('outputTokenLimit','?')}")

def gemma_repair(text, api_key, model, rpm=24, min_interval=2.6):
    """One paper -> strict JSON. Retries with backoff on 429/5xx."""
    prompt = f"""You are given text extracted from an AKTU university exam paper. Some text is noisy (stray digits/letters from watermarks, broken words). Hindi lines were already removed on purpose - ignore any remaining Hindi.
Reconstruct the list of exam QUESTIONS as strict JSON only, no markdown, schema:
{{"questions":[{{"label":"<as printed: 1, 2, a, b...>","text":"<clean English question text, broken words repaired, meaning unchanged>","marks":<int or null>,"choice_group":"<same letter token if this question is an OR-alternative of another, else null>","has_diagram":<bool>}}]}}
Rules: marks only when printed or clearly inferable (AKTU sections use 2/7/10/15); NEVER invent marks or questions; do not translate anything; do not merge OR-alternatives.
PAPER TEXT:
{text[:26000]}"""
    body = {'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {'temperature': 0.1, 'maxOutputTokens': 8192}}
    delay = min_interval
    for attempt in range(5):
        try:
            r = requests.post(f'{GEMMA_BASE}/models/{model}:generateContent',
                              params={'key': api_key}, json=body, timeout=180)
            if r.status_code in (429, 500, 503):
                wait = int(r.headers.get('Retry-After', 0)) or delay
                log(f"    [ai] {r.status_code}, backing off {wait:.0f}s")
                time.sleep(wait); delay = min(delay * 2, 120); continue
            r.raise_for_status()
            txt = r.json()['candidates'][0]['content']['parts'][0]['text']
            txt = re.sub(r'^```(json)?|```$', '', txt.strip(), flags=re.M).strip()
            return json.loads(txt)
        except (requests.RequestException, KeyError, json.JSONDecodeError) as e:
            log(f"    [ai] attempt {attempt+1} failed: {e}")
            time.sleep(delay); delay = min(delay * 2, 120)
    return None

def validate_ai_result(ai_json, parsed):
    """AI output must pass the SAME checks or it goes to review (anti-hallucination)."""
    if not ai_json or 'questions' not in ai_json:
        return None
    qs = []
    for q in ai_json['questions'][:60]:
        t = re.sub(r'\s+', ' ', str(q.get('text', ''))).strip()
        if len(t) < 15:
            continue
        marks = q.get('marks')
        if not isinstance(marks, int) or marks not in VALID_MARKS:
            marks = None
        qs.append({'label': str(q.get('label') or '')[:6], 'text': t, 'marks': marks,
                   'section': None, 'unit': None, 'choice_group': None,
                   'has_diagram': bool(q.get('has_diagram')), 'page': None, 'top': None})
    n = len(qs)
    frac = sum(1 for q in qs if q['marks']) / n if n else 0
    if n < 5 or frac < 0.4:
        return None
    return qs

# ---------------------------------------------------------------------------
# Diagram cropping
# ---------------------------------------------------------------------------
def crop_diagrams(pdf_path, parsed, outdir, file_hash):
    if not (HAVE_PDFIUM and PIL_OK):
        return 0
    if not parsed['meta'].get('is_text_layer', True):
        return 0          # OCR'd papers: line coords are pixels, not points (v2 feature)
    saved = 0
    doc = pdfium.PdfDocument(pdf_path)
    try:
        for idx, q in enumerate(parsed['questions']):
            if not q.get('has_diagram') or q.get('top') is None:
                continue
            try:
                pg_no = q.get('page')
                if not pg_no or pg_no > len(doc):
                    continue
                page = doc[pg_no - 1]
                nxt = None
                for q2 in parsed['questions'][idx + 1:]:
                    if q2.get('page') == pg_no and q2.get('top') is not None:
                        nxt = q2['top']; break
                band_h = (nxt - q['top']) if nxt else 160
                if not (30 <= band_h <= 700):
                    continue
                img = page.render(scale=2.0).to_pil()
                x0, x1 = 60, min(img.width - 30, int(0.92 * img.width))
                top_px = max(0, int(q['top'] * 2) - 6)
                bot_px = min(img.height, int((q['top'] + band_h) * 2))
                if bot_px - top_px < 40:
                    continue
                crop = img.crop((x0, top_px, x1, bot_px))
                # skip near-blank crops
                g = crop.convert('L').resize((80, 60))
                if sum(1 for p in g.getdata() if p < 128) < 40:
                    continue
                fname = f"{file_hash[:12]}_q{idx}_{q['label']}.png"
                crop.save(os.path.join(outdir, fname))
                q['diagram_file'] = fname
                saved += 1
            except Exception:
                continue
    finally:
        doc.close()
    return saved

# ---------------------------------------------------------------------------
# Supabase push (PostgREST + Storage REST)
# ---------------------------------------------------------------------------
class Supabase:
    def __init__(self, url, key):
        if not HAVE_REQUESTS:
            sys.exit('requests missing for --db')
        self.url, self.key = url.rstrip('/'), key
        self.hdr = {'apikey': key, 'Authorization': f'Bearer {key}',
                    'Content-Type': 'application/json'}

    def upsert(self, table, rows, on_conflict, returns=True):
        h = dict(self.hdr)
        h['Prefer'] = ('resolution=merge-duplicates,return=representation' if returns
                       else 'resolution=merge-duplicates')
        r = requests.post(f'{self.url}/rest/v1/{table}', headers=h,
                          params={'on_conflict': on_conflict}, data=json.dumps(rows), timeout=60)
        r.raise_for_status()
        return r.json() if returns else None

    def upload_diagram(self, bucket, path, file_path):
        with open(file_path, 'rb') as f:
            r = requests.post(f'{self.url}/storage/v1/object/{bucket}/{path}',
                              headers={'Authorization': f'Bearer {self.key}',
                                       'x-upsert': 'true', 'Content-Type': 'image/png'},
                              data=f.read(), timeout=60)
            if r.status_code >= 300:
                log(f"    [storage] {path}: {r.status_code} {r.text[:80]}")
                return None
            return f'{self.url}/storage/v1/object/public/{bucket}/{path}'

def push_paper(sb, fname, file_hash, parsed, mark_review):
    """Upsert subject, paper, questions, occurrences. Returns paper id."""
    meta = parsed['meta']
    code = meta.get('code')
    if not code:
        return None
    name = parsed.get('subject_name') or code
    sb.upsert('subjects', [{'code': code, 'name': name,
                            'course': meta.get('course', 'BTech'),
                            'semester': meta.get('semester'), 'is_active': True}], 'code')
    pr = sb.upsert('papers', [{'subject_code': code, 'year': meta.get('year'),
                               'file_hash': file_hash, 'source_url': meta.get('source_url'),
                               'source': 'ryzenstudy', 'is_text_layer': meta.get('is_text_layer', True)}],
                   'file_hash')
    paper_id = pr[0]['id'] if pr else None
    if not paper_id:
        return None
    for q in parsed['questions']:
        norm = re.sub(r'[^\w\s]', '', q['text'].lower())
        norm = re.sub(r'\s+', ' ', norm).strip()
        qh = hashlib.sha256(norm.encode()).hexdigest()
        row = {'subject_code': code, 'text': q['text'], 'text_normalized': norm,
               'question_hash': qh, 'language': 'en',
               'question_type': 'other',
               'marks': q.get('marks'), 'unit': q.get('unit'),
               'choice_group': q.get('choice_group'),
               'has_diagram': bool(q.get('has_diagram')),
               'extraction_confidence': parsed['confidence'],
               'needs_review': mark_review}
        qr = sb.upsert('questions', [row], 'subject_code,question_hash')
        qid = qr[0]['id'] if qr else None
        if qid:
            occ = {'question_id': qid, 'paper_id': paper_id, 'year': meta.get('year'),
                   'q_no': str(q.get('label') or ''), 'marks': q.get('marks'),
                   'extraction_confidence': parsed['confidence']}
            sb.upsert('occurrences', [occ], 'question_id,paper_id', returns=False)
    return paper_id

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def parse_filename(fname):
    """Course__SemNN__year__CODE__slug.pdf"""
    base = os.path.splitext(os.path.basename(fname))[0]
    parts = base.split('__')
    out = {}
    if len(parts) >= 5:
        out['course'] = parts[0].upper().replace('BTECH', 'BTech').replace('BPHARM', 'BPharm')
        out['semester'] = int(re.sub(r'\D', '', parts[1]) or 0) or None
        out['year'] = parts[2]
        out['code'] = parts[3]
        out['subject_name'] = parts[4].replace('-', ' ').title()
    return out

def find_pdfs(root):
    if os.path.isfile(root):
        return [root]
    found = []
    for dirpath, _, files in os.walk(root):
        for f in sorted(files):
            if f.lower().endswith('.pdf'):
                found.append(os.path.join(dirpath, f))
    return found

def main():
    ap = argparse.ArgumentParser(description='AKTU PYQ tiered extractor')
    ap.add_argument('--dir', default='aktu-pyq/unstructured')
    ap.add_argument('--out', default='extraction_out')
    ap.add_argument('--pilot', type=int, metavar='N', help='run on first N PDFs, report only')
    ap.add_argument('--confidence', type=float, default=0.62)
    ap.add_argument('--ai', action='store_true', help='enable Tier-2 Gemma repair')
    ap.add_argument('--db', action='store_true', help='push results to Supabase')
    ap.add_argument('--no-crop', action='store_true', help='disable diagram PNG crops')
    ap.add_argument('--limit', type=int), ap.add_argument('--offset', type=int, default=0)
    ap.add_argument('--shard', type=int, default=0), ap.add_argument('--shards', type=int, default=1)
    ap.add_argument('--soft-deadline', type=int, default=320, help='minutes; exit cleanly before GHA 6h kill')
    ap.add_argument('--list-models', action='store_true')
    args = ap.parse_args()

    api_key = os.environ.get('GEMMA_API_KEY', '')
    model = os.environ.get('GEMMA_MODEL', 'gemma-4-31B')
    if args.list_models:
        list_models(api_key or 'YOUR_KEY'); return

    os.makedirs(args.out, exist_ok=True)
    os.makedirs(os.path.join(args.out, 'diagrams'), exist_ok=True)
    os.makedirs(os.path.join(args.out, 'ai_cache'), exist_ok=True)
    os.makedirs(os.path.join(args.out, 'parsed'), exist_ok=True)
    sb = Supabase(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY']) \
        if args.db and os.environ.get('SUPABASE_URL') else None
    if args.db and not sb:
        log('[!] --db set but SUPABASE_URL/SUPABASE_SERVICE_KEY missing -> local output only')

    pdfs = find_pdfs(args.dir)
    pdfs = [p for i, p in enumerate(pdfs) if i % args.shards == args.shard]
    if args.offset: pdfs = pdfs[args.offset:]
    if args.limit: pdfs = pdfs[:args.limit]
    if args.pilot: pdfs = pdfs[:args.pilot]
    log(f'[i] {len(pdfs)} PDFs in scope (shard {args.shard}/{args.shards})')

    state_path = os.path.join(args.out, 'extract_state.json')
    state = {}
    if os.path.exists(state_path):
        state = json.load(open(state_path))
    t0 = time.time()
    summary = []
    outbox = open(os.path.join(args.out, 'outbox.jsonl'), 'a', encoding='utf-8')

    for i, path in enumerate(pdfs):
        if (time.time() - t0) > args.soft_deadline * 60:
            log(f'[!] soft deadline reached at paper {i}; checkpoint and exit')
            break
        fname = os.path.basename(path)
        if state.get(fname, {}).get('status') in ('accepted', 'ai_repaired') or \
           (state.get(fname, {}).get('status') == 'review' and not args.ai):
            summary.append((fname, state[fname]['status'], state[fname].get('conf')))
            continue
        fhash = sha256(path)
        try:
            lines, meta0, stats, pages = tier0(path)
            fmap = parse_filename(path)
            meta = {**fmap, **{k: v for k, v in meta0.items() if v is not None}}
            meta.setdefault('is_text_layer', len(lines) > 30)
            parsed = parse_paper(lines, meta)
            parsed['subject_name'] = fmap.get('subject_name')
            infer_diagram_flags(parsed, pages)
            conf = parsed['confidence']
            status, mark_review = ('accepted', False) if conf >= args.confidence else ('gate_fail', False)

            # Tier 2
            if status == 'gate_fail' and args.ai and api_key:
                cache_f = os.path.join(args.out, 'ai_cache', fhash[:16] + '.json')
                if os.path.exists(cache_f):
                    ai = json.load(open(cache_f))
                else:
                    raw_text = '\n'.join(l['text'] for l in lines)
                    ai = gemma_repair(raw_text, api_key, model)
                    if ai:
                        json.dump(ai, open(cache_f, 'w'))
                qs = validate_ai_result(ai, parsed)
                if qs:
                    parsed['questions'] = qs
                    status, mark_review = 'ai_repaired', False
                else:
                    status, mark_review = 'review', True
            elif status == 'gate_fail':
                status, mark_review = 'review', True

            crops = 0
            if not args.no_crop:
                crops = crop_diagrams(path, parsed, os.path.join(args.out, 'diagrams'), fhash)

            json.dump(parsed, open(os.path.join(args.out, 'parsed',
                      fhash[:16] + '.json'), 'w'), ensure_ascii=False, default=str)
            for q in parsed['questions']:
                outbox.write(json.dumps({'file': fname, 'file_hash': fhash, 'status': status,
                                         'subject_code': meta.get('code'),
                                         'year': meta.get('year'),
                                         'label': q.get('label'), 'text': q['text'],
                                         'marks': q.get('marks'),
                                         'has_diagram': q.get('has_diagram', False),
                                         'needs_review': mark_review,
                                         'confidence': conf}, ensure_ascii=False) + '\n')
            if sb:
                push_paper(sb, fname, fhash, parsed, mark_review)
            state[fname] = {'status': status, 'conf': conf, 'hash': fhash,
                            'at': datetime.now(timezone.utc).isoformat()}
            summary.append((fname, status, conf))
            log(f'  [{i+1}/{len(pdfs)}] {status:12} conf={conf:.2f} q={parsed["checks"]["questions"]:2} '
                f'hindi={stats["hindi"]:2} diagrams={crops}  {fname[:52]}')
        except Exception as e:
            state[fname] = {'status': 'failed', 'error': str(e)[:200]}
            summary.append((fname, 'failed', None))
            log(f'  [{i+1}/{len(pdfs)}] FAILED {type(e).__name__}: {str(e)[:90]} | {fname[:48]}')
        json.dump(state, open(state_path, 'w'))
    outbox.close()

    log('\n===== SUMMARY =====')
    from collections import Counter
    cnt = Counter(s for _, s, _ in summary)
    log(f'total={len(summary)} ' + ' '.join(f'{k}={v}' for k, v in cnt.items()))
    if summary:
        acc = [c for _, s, c in summary if s == 'accepted' and c is not None]
        if acc:
            log(f'mean confidence (accepted) = {sum(acc)/len(acc):.3f}')
    log(f'outputs: {args.out}/parsed, outbox.jsonl, extract_state.json, diagrams/')

if __name__ == '__main__':
    main()
