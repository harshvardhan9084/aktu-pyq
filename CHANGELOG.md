# AKTU PYQ — Version 2 Changelog

## What's New in v2

### Backend

**pdf_processor.py**
- `extract_paper_metadata()` — reads AKTU paper header (page 1) via regex; detects programme, subject name, subject code (EE-301 etc.), branch, semester, year, exam session (odd/even). Subject code lookup dict for ~30 common codes.
- `detect_unit_sections()` — finds UNIT-I through UNIT-V headers in full text, tags every question with its `unit` (int) and `unit_topic`.
- `compute_question_hash()` — SHA-256 of normalized_text. Used for exact dedup (replaces buggy 80-char ilike).
- `extract_diagram_crop()` — renders page via pdf2image, builds text density map via pdfplumber word bboxes, finds largest non-text band, returns PNG bytes.
- `ExtractedQuestion` now carries: `unit`, `unit_topic`, `question_hash`, `sub_parts`, `page_number`, `has_math`.

**routers/admin.py**
- `process_and_insert()` — hash-based dedup (no more frequency_count inflation). Auto-fills subject/branch/semester/programme/session from paper metadata when admin fields are blank. Uploads diagram crops to Supabase Storage, saves `diagram_url`. Updates `frequency_count`, `year_appeared`, `exam_sessions` arrays on duplicates. Computes `importance_score` + `must_revise_flag`.
- `POST /admin/metadata/extract` — lightweight endpoint called on file-select in admin upload form; returns auto-detected metadata before full processing.
- `POST /admin/scrape/feed` — accepts list of partial aktuonline.com PDF names, validates via HEAD, inserts into scrape_queue.
- `POST /admin/scrape/run` — processes up to N pending scrape_queue items. Downloads PDF via httpx, runs full pipeline, marks done/failed.
- `GET /admin/scrape/status` — recent queue items with counts.
- `POST /admin/analytics/event` — receives page_view, search, contribute events from frontend.
- `GET /admin/analytics/summary` — counters + monthly visitor breakdown.
- `POST /admin/questions/{id}/confirm-appeared` — increments `user_confirmed_count`.
- `POST /admin/recalculate` — recalculates importance_score + trend for all questions.

**routers/upload.py (student contribute)**
- No form fields. PDF only. Auto-extracts metadata from paper header.
- Checks for duplicate by file_hash AND by (subject_code, year, exam_session).
- On duplicate: returns `{duplicate: true, message: "..."}` with subject hint — no error.
- On new paper: inserts `pdf_submissions` record + adds to `scrape_queue` for automatic processing (no admin review required for processing).
- Tracks `analytics_events` + increments `total_contributors` counter.

**routers/search.py**
- `run_search()` — now selects all columns including `unit`, `unit_topic`, `subject_code`, `has_diagram`, `diagram_url`, `has_math`, `sub_parts`, `exam_sessions`, `user_confirmed_count`.
- `enrich_question()` — adds computed `seen_in_label` ("Seen in 6 exams (2019–2024)") to every result.
- `GET /search/subjects` — dynamic subject list from DB filtered by branch+semester. Powers DynamicForm dropdown.
- `GET /search/papers` — papers browser; returns approved pdf_submissions with question counts.
- `GET /search/stats/public` — total_questions, total_papers, total_subjects for homepage counter.
- `POST /search/questions/{id}/view` — increments user_views_count.
- Unit filter now wired in both NL and filter search.

**schema.sql**
- New columns: `question_hash` (UNIQUE), `subject_code`, `unit`, `unit_topic`, `has_math`, `sub_parts`, `exam_sessions`, `user_confirmed_count`, `diagram_url`, `page_number`.
- New tables: `scrape_queue`, `analytics_events`, `site_counters`.
- New view: `question_with_context` with `seen_in_label` and `year_range_label`.
- `diagram` added to question_type check constraint.

**supabase_rpc.sql** — run separately for atomic `increment_counter()` function.

### Frontend

**page.tsx (homepage)**
- Live question count from `/search/stats/public` — real data, no hardcoded numbers.
- Page-view analytics tracking on mount.
- Footer now includes Papers link.

**contribute/page.tsx**
- Zero form fields — only the PDF file input.
- Immediate feedback: "Paper received — processing now" with auto-detected metadata shown (subject, year, session). No admin step required.
- Duplicate: shows helpful message with subject + links to `/papers`.
- Drag-and-drop on drop zone.

**papers/page.tsx (NEW)**
- Full papers browser listing all approved PDFs as cards.
- Filters: Programme, Semester, text search (subject/branch/code).
- Shows question count per paper.
- "Don't see your paper?" CTA at bottom.

**ResultsList.tsx**
- `seen_in_label` shown prominently ("Seen in 6 exams (2019–2024) ↑").
- Unit badge with topic ("Unit 3 · Transmission Lines").
- Diagram image rendered inline if `diagram_url` present.
- Sub-parts shown in expanded view.
- "This appeared in my exam" confirm button → increments `user_confirmed_count`.
- WhatsApp share button.
- "More from Unit N →" link in expanded view.
- View tracking on expand.
- Empty state links to /contribute and /papers.

**DynamicForm.tsx**
- Cookie personalization: after first use, programme/branch/semester pre-filled on return. Summary pill with "Search everything ⟷ My branch" toggle.
- ← Back button on every step.
- Subject dropdown fetched from DB for the selected branch+semester (dynamic, not hardcoded).
- Diagram question type added.
- "No subjects yet" state with link to /contribute.

**NaturalSearch.tsx**
- Search analytics tracking.
- Added "Must revise" and "Diagram" suggestions.

**Navbar.tsx**
- Papers link added between Search and Contribute.

**Admin dashboard**
- New "Bulk Import" tab: textarea for PDF partial names, validate & queue, scrape queue table, "Run Next Batch" button.
- New "Analytics" tab: site counters (visitors, searches, contributors, questions, papers), monthly visitors bar chart.
- Admin upload form: auto-populates metadata fields on file select via `/admin/metadata/extract`.
- Submissions tab now explains auto-queue flow.

## Supabase Actions Required
1. Run `backend/schema.sql` in Supabase SQL Editor.
2. Run `backend/supabase_rpc.sql` in Supabase SQL Editor (for atomic counters).
3. Create a Supabase Storage bucket named `diagrams` (public).

## No changes needed
- `backend/main.py` — only version bump.
- `backend/services/embedding.py` — unchanged.
- `backend/services/clustering.py` — unchanged.
- `backend/services/vector_db.py` — unchanged.
- `frontend/app/layout.tsx` — unchanged.
- `frontend/app/globals.css` — unchanged.
- `frontend/tailwind.config.js` — unchanged.
- `frontend/app/admin/x7k2/page.tsx` — unchanged.
- `frontend/app/api/admin/*` — unchanged.
- `frontend/lib/admin-auth.ts` — unchanged.
