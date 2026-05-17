<p align="center">
  <img src="https://img.shields.io/badge/AKTU-PYQ%20Intelligence-e8b84b?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCI+PHBhdGggZmlsbD0iI2U4Yjg0YiIgZD0iTTEzIDIuMDVWMi4wNUExMCAxMCAwIDAgMSAyMiAxMmExMCAxMCAwIDAgMS0xMCAxMEExMCAxMCAwIDAgMSAyIDEyQTEwIDEwIDAgMCAxIDEzIDIuMDV6Ii8+PC9zdmc+" />
  <img src="https://img.shields.io/badge/Next.js-14-black?style=for-the-badge&logo=next.js" />
  <img src="https://img.shields.io/badge/FastAPI-Python%203.11-009688?style=for-the-badge&logo=fastapi" />
  <img src="https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?style=for-the-badge&logo=supabase" />
  <img src="https://img.shields.io/badge/Deployed-Vercel%20%2B%20Render-000?style=for-the-badge&logo=vercel" />
</p>

<h1 align="center">AKTU PYQ Intelligence</h1>
<p align="center"><b>Find what actually gets asked in your AKTU exams — in 10 seconds, not 10 hours.</b></p>

<p align="center">
  <a href="https://aktu-pyq.vercel.app">🌐 Live Site</a> ·
  <a href="#-features">Features</a> ·
  <a href="#-getting-started">Getting Started</a> ·
  <a href="#-tech-stack">Tech Stack</a> ·
  <a href="#-contributing">Contributing</a>
</p>

---

## What is this?

AKTU PYQ Intelligence is a semantic search engine built specifically for students of **Dr. A.P.J. Abdul Kalam Technical University (AKTU/UPTU)**. Instead of scrolling through hundreds of PDF question papers before exams, you search once — and instantly see which questions have been asked most, across how many years, and in which units.

**This is not a chatbot. It does not generate answers.** Its intelligence is in:

- Extracting every question from every uploaded AKTU question paper
- Clustering semantically similar questions across years
- Counting repetition frequency and computing importance scores
- Returning ranked results so you know what to prioritise

---

## ✨ Features

### For Students
| Feature | Description |
|---|---|
| **Natural Language Search** | "Top repeated theory questions in Basic Electrical Unit 3" |
| **Step-by-Step Filter** | Programme → Branch → Semester → Subject → Unit → Type |
| **"Seen in N exams"** | Every result shows how many exams a question has appeared in, with year range |
| **Unit-wise results** | Questions tagged by Unit 1–5 (parsed from paper headers) |
| **Must Revise flag** | Top 20% by importance score marked automatically |
| **Diagram display** | Circuit diagrams and figures cropped from original papers and shown inline |
| **WhatsApp share** | One tap to share a question to your study group |
| **"This appeared in my exam"** | Community-confirm button to strengthen frequency data |
| **Cookie memory** | Returns your branch/semester selection automatically on next visit |
| **Light/Dark theme** | System-default, smooth toggle, persists across sessions |
| **Paper browser** | Browse all indexed papers by programme, branch, semester, year |
| **Wake countdown** | Friendly status banner if backend is starting up (free-tier cold start) |

### For Contributors
| Feature | Description |
|---|---|
| **Zero-field upload** | Drop a PDF — subject, year, branch auto-extracted from paper header |
| **Instant feedback** | Told immediately if paper is already in the database, or queued successfully |
| **Auto-processing** | Student contributions go straight to the processing queue — no admin approval needed |

### For Admins
| Feature | Description |
|---|---|
| **Bulk import** | Paste aktuonline.com partial PDF names → HEAD-validated → queued |
| **Scrape worker** | Downloads, extracts, clusters, and inserts in batches of 10 |
| **Metadata auto-fill** | Upload form auto-detects subject/branch/semester from paper header |
| **Analytics dashboard** | Visitors, searches, contributors, device breakdown, top pages, top queries, scroll depth, time on page |
| **Database tools** | Recalculate scores, re-cluster, rebuild index, export, clear queue |
| **System logs** | Full processing log with colour-coded severity |

---

## 📸 Screenshots

> *(Add screenshots here after first deploy)*

---

## 🛠 Tech Stack

```
Frontend          Next.js 14 (App Router) · TypeScript · Tailwind CSS
                  Custom dark/light design system · Framer Motion · lucide-react

Backend           FastAPI · Python 3.11 · uvicorn
                  pypdf · pdfplumber · pytesseract · opencv-headless · pdf2image
                  scikit-learn TF-IDF (replaces heavy sentence-transformers)
                  ftfy · httpx

Database          Supabase (PostgreSQL)
                  Tables: questions · clusters · pdf_submissions · scrape_queue
                          analytics_events · site_counters · universities

Hosting           Vercel (frontend) · Render free tier (backend)
Storage           Supabase Storage (diagram crops · student-submitted PDFs)
```

---

## 🚀 Getting Started

### Prerequisites

- Node.js ≥ 18
- Python 3.11 (exact — set via `PYTHON_VERSION=3.11.9` on Render)
- A [Supabase](https://supabase.com) project
- A [Render](https://render.com) account (backend)
- A [Vercel](https://vercel.com) account (frontend)
- `tesseract-ocr` installed on backend server (Render includes it)
- `poppler-utils` installed on backend server (for pdf2image)

---

### 1. Clone the repository

```bash
git clone https://github.com/harshvardhan9084/aktu-pyq.git
cd aktu-pyq
```

---

### 2. Set up Supabase

1. Create a new Supabase project at [supabase.com](https://supabase.com)
2. Go to **SQL Editor** and run `backend/schema.sql` (creates all tables, indexes, views)
3. Run `backend/supabase_rpc.sql` (creates atomic counter function)
4. Create a **Storage bucket** named `diagrams` — set to **Public**
5. Create a **Storage bucket** named `pdf-uploads` — set to **Private**
6. Note your **Project URL** and **Service Role Key** (Settings → API)

---

### 3. Backend — local setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Copy and fill in your environment variables
cp .env.example .env
```

Fill in `.env`:
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
ADMIN_API_TOKEN=sha256_of_your_admin_password
ALLOWED_ORIGINS=http://localhost:3000
PYTHON_VERSION=3.11.9
```

> **How to generate ADMIN_API_TOKEN:**
> ```python
> import hashlib
> print(hashlib.sha256("your_password_here".encode()).hexdigest())
> ```
> Use the same password for the frontend `ADMIN_PASSWORD_HASH`.

```bash
uvicorn main:app --reload --port 8000
```

Backend runs at `http://localhost:8000`. Visit `/docs` for the API explorer.

---

### 4. Frontend — local setup

```bash
cd frontend
npm install

cp .env.example .env.local
```

Fill in `.env.local`:
```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
ADMIN_PASSWORD_HASH=sha256_of_your_admin_password
SESSION_SALT=any_random_string_here
```

```bash
npm run dev
```

Frontend runs at `http://localhost:3000`.

---

### 5. Deploy to Render (backend)

1. Push your code to GitHub
2. Create a new **Web Service** on Render → connect your repo → set root to `backend/`
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Set environment variables:

| Key | Value |
|---|---|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Your service role key |
| `ADMIN_API_TOKEN` | sha256 of your admin password |
| `ALLOWED_ORIGINS` | `https://your-frontend.vercel.app` |
| `PYTHON_VERSION` | `3.11.9` |

> ⚠️ **Important:** `PYTHON_VERSION` env var is the only reliable way to pin Python on Render free tier. `runtime.txt` and `render.yaml` pythonVersion are both ignored.

---

### 6. Deploy to Vercel (frontend)

1. Import your GitHub repo into Vercel → set root to `frontend/`
2. Set environment variables:

| Key | Value |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Your Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Your Supabase anon key |
| `NEXT_PUBLIC_BACKEND_URL` | Your Render backend URL |
| `ADMIN_PASSWORD_HASH` | Same sha256 hash as ADMIN_API_TOKEN |
| `SESSION_SALT` | Any random string |

> **Critical:** `ADMIN_API_TOKEN` on Render **must equal** `ADMIN_PASSWORD_HASH` on Vercel. Both must be `sha256(your_actual_password)`. Mismatch = 403 on every admin action.

---

## 🗂 Project Structure

```
aktu-pyq/
├── backend/
│   ├── main.py                    # FastAPI app, CORS middleware, lifespan
│   ├── requirements.txt
│   ├── schema.sql                 # Full Supabase schema (run first)
│   ├── supabase_rpc.sql           # Atomic counter function (run second)
│   ├── routers/
│   │   ├── admin.py               # Admin endpoints: upload, scrape, analytics, DB tools
│   │   ├── search.py              # NL search, filter search, papers browser, public stats
│   │   └── upload.py              # Student contribution endpoint → scrape_queue
│   └── services/
│       ├── pdf_processor.py       # PDF extraction, metadata parser, unit detector, diagram crop
│       ├── embedding.py           # TF-IDF vectorizer (lightweight, Render-safe)
│       ├── clustering.py          # DBSCAN clustering, trend detection, importance scoring
│       └── vector_db.py           # ChromaDB wrapper (optional)
│
└── frontend/
    ├── app/
    │   ├── page.tsx               # Homepage: search, live question count, WakeBanner
    │   ├── contribute/page.tsx    # Student PDF upload (zero form fields)
    │   ├── papers/page.tsx        # Papers browser with filters
    │   ├── layout.tsx             # ThemeProvider, AnalyticsInit, fonts
    │   ├── globals.css            # Design tokens, dark/light CSS vars, glass components
    │   └── admin/x7k2/
    │       ├── page.tsx           # Admin login (hidden URL)
    │       └── dashboard/page.tsx # Full admin dashboard
    ├── components/
    │   ├── Navbar.tsx             # Navigation + theme toggle
    │   ├── NaturalSearch.tsx      # NL query input with suggestions
    │   ├── DynamicForm.tsx        # Step-by-step filter form with cookie memory
    │   ├── ResultsList.tsx        # Question cards with seen_in_label, diagram, share
    │   ├── ThemeProvider.tsx      # System-default theme, smooth toggle, localStorage
    │   ├── WakeBanner.tsx         # Smart cold-start countdown banner
    │   └── AnalyticsInit.tsx      # Page view, scroll depth, heartbeat init
    └── lib/
        ├── supabase.ts            # Supabase client + full Question type
        ├── analytics.ts           # Rich behavioral analytics collector
        └── admin-auth.ts          # Session token helpers
```

---

## 🗄 Database Schema

The `questions` table is the core. Every row represents one unique question:

| Column | Type | Description |
|---|---|---|
| `question_text` | text | Full question text |
| `question_hash` | text | SHA-256 of normalized text — used for exact dedup |
| `subject` | text | Subject name (auto-detected from paper header) |
| `subject_code` | text | AKTU code e.g. EE-301, NAS-103 |
| `branch` | text | Engineering branch |
| `programme` | text | B.Tech / Diploma / MBA etc. |
| `semester` | int | 1–8 |
| `unit` | int | 1–5 (parsed from UNIT-I headers) |
| `unit_topic` | text | Topic label under that unit |
| `question_type` | enum | theory / numerical / short / diagram / other |
| `has_diagram` | bool | Whether question involves a figure/circuit |
| `diagram_url` | text | Supabase Storage URL of cropped diagram |
| `year_appeared` | int[] | All years this question appeared |
| `exam_sessions` | text[] | e.g. ["2022-odd", "2023-even"] |
| `frequency_count` | int | How many exams it has appeared in |
| `importance_score` | float | 0–1 composite score (frequency + trend + recency) |
| `must_revise_flag` | bool | True if importance_score ≥ 0.75 |
| `user_confirmed_count` | int | Community confirmations ("this appeared in my exam") |
| `seen_in_label` | — | Computed at query time: "Seen in 6 exams (2019–2024)" |

---

## 🔐 Admin Panel

The admin panel lives at `/admin/x7k2` — not linked anywhere on the public site.

**Authentication flow:**
1. You enter your password at the login page
2. Frontend computes `sha256(password)` and compares with `ADMIN_PASSWORD_HASH` env var
3. On match, it creates a session token: `sha256(ADMIN_PASSWORD_HASH + SESSION_SALT)`
4. Every admin API call sends this token as `X-Admin-Token` header
5. Backend verifies: `sha256(ADMIN_API_TOKEN + "session_salt_aktu_pyq")`
6. Session lasts 8 hours

> `ADMIN_API_TOKEN` on Render must equal `ADMIN_PASSWORD_HASH` on Vercel — both are `sha256(your_password)`.

---

## 📊 Analytics

All analytics are collected first-party — no Google Analytics, no external SDKs, no cookies that require consent banners.

**Collected signals:**
- Page views (with referrer, UTM params, device class, timezone, connection type)
- Time on page (on unload)
- Scroll depth milestones (25%, 50%, 75%, 100%)
- Search queries and result counts
- Question expand / share / confirm events
- Contribute attempts and outcomes
- Session heartbeat (active time every 30s)
- Return visitor detection (anonymous local ID, no PII)

All data is stored in `analytics_events` (raw) and `site_counters` (aggregated). Visible in the Analytics tab of the admin dashboard.

---

## 🤝 Contributing

### Contributing a question paper (students)

1. Visit [aktu-pyq.vercel.app/contribute](https://aktu-pyq.vercel.app/contribute)
2. Drop your PDF — no form fields to fill in
3. Subject, year, branch are auto-detected from the paper header
4. You'll immediately know if it's already in the database or queued

### Contributing code (developers)

1. Fork the repo
2. Create a branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Test locally (see [Getting Started](#-getting-started))
5. Open a pull request with a clear description

**Code rules (read before PRing):**
- All heavy Python imports (`cv2`, `pdf2image`, `pytesseract`, `pdfplumber`) must be **lazy** (imported inside functions) — server must start even if optional deps are missing
- Never pin `Pillow` to a specific version — use `Pillow>=10.3.0`
- Never use inline `(?i)` flags in joined regex patterns — use `re.IGNORECASE` at compile time
- Always sanitize `question_type` to one of `('theory','numerical','short','diagram','other')` before DB insert
- Design system: ink/gold/jade color tokens, CSS variables only — no hardcoded hex values in components
- All new components must work in both dark and light themes via CSS vars

---

## 📝 Environment Variables Reference

### Backend (`backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `SUPABASE_URL` | ✅ | Your Supabase project URL |
| `SUPABASE_SERVICE_KEY` | ✅ | Service role key (full DB access) |
| `ADMIN_API_TOKEN` | ✅ | `sha256(your_admin_password)` |
| `ALLOWED_ORIGINS` | ✅ | Frontend URL for CORS |
| `PYTHON_VERSION` | ✅ | Must be `3.11.9` on Render |
| `CHROMA_PERSIST_PATH` | ❌ | Path for ChromaDB (default: `./chroma_db`) |

### Frontend (`frontend/.env.local`)

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | ✅ | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | ✅ | Supabase anon/public key |
| `NEXT_PUBLIC_BACKEND_URL` | ✅ | Backend URL (no trailing slash) |
| `ADMIN_PASSWORD_HASH` | ✅ | `sha256(your_admin_password)` — must equal backend `ADMIN_API_TOKEN` |
| `SESSION_SALT` | ✅ | Any random string for session token |

---

## ⚠️ Known Limitations

- **Render free tier cold starts:** Backend sleeps after 15 minutes of inactivity. First request after sleep takes 30–50 seconds. The WakeBanner on the frontend handles this gracefully for users.
- **OCR quality:** Scanned/photographed PDFs extract fewer questions than digital PDFs. Quality depends on scan resolution.
- **Metadata extraction:** Subject codes not in the built-in lookup table (`SUBJECT_CODE_MAP`) may not have branch/subject auto-filled. Expand the map in `pdf_processor.py` to improve this.
- **TF-IDF vs semantic embeddings:** Using TF-IDF (not sentence-transformers) to stay within Render free tier 512MB RAM. Clustering works well for exam questions with shared vocabulary; cross-subject semantic similarity is limited.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgements

Built with ❤️ for AKTU students. Every question paper in this database was contributed by a student who wanted their classmates to study smarter.

If this saved you time before an exam, consider [supporting the project](https://aktu-pyq.vercel.app/contribute#donate) — it keeps the servers running and the database growing.

---

<p align="center">
  <a href="https://aktu-pyq.vercel.app">aktu-pyq.vercel.app</a> · Not affiliated with AKTU · For educational use only
</p>
