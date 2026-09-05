# EXTRACTION GUIDE — aktu_pyq_extractor.py (v1)

The tiered pipeline you locked in: **fuzzy parser first (free) → Gemma repairs only
what fails the gate → everything AI produces is re-validated before it touches
your database.** Hindi lines are discarded at Tier 0 (they are duplicate
alternates of the English questions — never stored, never sent to AI).

```
PDF ─► Tier 0 cleanup ─► Tier 1 fuzzy parse ─► gate (confidence ≥ 0.62)
      (chars, watermark,  (signals vote on        │pass → ACCEPTED  (0 AI tokens)
       Hindi, footers)     questions, marks,      └fail → Tier 2 Gemma repair ─► validator
                           OR-pairs, sections)          │pass → AI_REPAIRED
                                                        └fail → Tier 3 needs_review
       diagram questions ─► PNG crop (pypdfium2) ─► Supabase Storage (when --db)
```

---

## 1. Quick start (your machine, 5 minutes, zero quota)

```bash
pip install pdfplumber pypdfium2 pillow requests ftfy pytesseract
# (scanned papers need the tesseract binary too:  sudo apt install tesseract-ocr)

# put some PDFs in aktu-pyq/unstructured first (run ryzenstudy_pyq_scraper.py)
python3 aktu_pyq_extractor.py --pilot 30 --dir aktu-pyq/unstructured
```

Read the per-paper lines: `conf`, `q=` question count, `hindi=` stripped lines,
`diagrams=` crops. At the end you get `accepted / ai_repaired / review / failed`
counts. **The pilot's accepted % is the number that tells you how much AI quota
you will really need** — on our 6-paper demo: 5/5 parseable papers accepted with
mean confidence 0.96, the scanned one too (OCR path).

Raise/lower the gate with `--confidence 0.55` (more auto-accept, more noise) or
`0.70` (cleaner, more AI calls).

## 2. Outputs (folder `extraction_out/`)

| File | What it is |
|---|---|
| `outbox.jsonl` | one line per question — ready for DB import / inspection |
| `parsed/<hash>.json` | full per-paper parse: questions, marks, sections, choice groups, confidence |
| `extract_state.json` | resume checkpoint — re-running skips finished papers |
| `ai_cache/*.json` | raw Gemma responses keyed by file-hash + prompt version (re-runs are FREE) |
| `diagrams/*.png` | cropped diagram regions (`<hash>_q<n>_<label>.png`) |

## 3. Full backlog on GitHub Actions (1,396 papers)

**Where the PDFs live — the barrier nobody warns you about.** Do NOT commit the
PDFs to your PUBLIC repo (aktu-pyq): a public repo with all 1,396 PDFs is a
bulk-download gift to every scraper — the exact thing you said would kill you.
Choose one:

- **Option A (recommended): private pipeline repo.** Create a PRIVATE repo,
  put `aktu_pyq_extractor.py`, `gha_extraction.yml` (→ `.github/workflows/extraction.yml`),
  and the `aktu-pyq/unstructured/` PDFs inside. Private = invisible to the world,
  Actions is still free (2,000 min/month private tier ≫ what you need; a full
  backlog pass ≈ 4.5–7 h of compute).
- **Option B: Supabase Storage private bucket.** Upload PDFs there, add a
  download step to the workflow (signed URLs via service key). Cleaner repo, one
  more moving part. PDFs stay out of git entirely.

**Secrets to set (repo → Settings → Secrets and variables → Actions):**
- `GEMMA_API_KEY` — your Google AI Studio key. Make it in a **dedicated Google
  Cloud project** used only by the pipeline, so the future AI-chat feature of the
  website never competes with the backlog for the same 30 RPM / 16k TPM / 14.4k RPD.
- `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` — service_role key (bypasses RLS).
  Server-side only, never in the browser app.
- Optional repo *variable* `GEMMA_MODEL` — model id. The owner-reported id is
  `gemma-4-31B`; **verify what your account actually exposes:**
  `python3 aktu_pyq_extractor.py --list-models` (prints ids + token limits).

**Run:** Actions → PYQ Extraction → Run workflow → `mode=backlog`,
`shards=3`, run three dispatches with `shard=0,1,2` (each ≈ 465 papers ≈ under
the 6 h cap) — or run shards sequentially over 2 evenings. Results push straight
into Supabase; artifacts appear under the run even if something dies.

**Time math (new quota):** Tier-1 accepts ~55–70% free; the AI slice is
~420–630 papers ≈ 2.5–3.5M tokens ≈ **4.5–7 h total wall clock** at the
extractor's conservative pacing (≈2.6 s between calls). After launch, each exam
cycle adds ~150–250 papers → **under 1 h of AI per cycle**.

## 4. Barrier playbook (every failure mode, and its answer)

| Barrier | What happens | What to do |
|---|---|---|
| 6 h job cap | workflow would die mid-write | extractor exits cleanly at `--soft-deadline 300` min; re-run the same dispatch — state file resumes |
| Quota cut again mid-run (like your 60→30 RPM) | 429 storm | backoff retries up to 5×; if exhausted the paper lands in `review`, run continues; resume next day when quota resets |
| RPD exhausted (14.4k/day) | only matters for AI-first scale | hybrid needs ~2–3k; if you ever add a polish pass, split across 2 days |
| Model id wrong / renamed | 404 from Generative Language | `--list-models`, set repo variable `GEMMA_MODEL` |
| Wrong model output (JSON broken) | validator rejects | response goes to `ai_cache` anyway; paper → `review`; nothing corrupt enters DB |
| Private-repo minutes | 2,000 min/mo free tier | backlog ≈ 1,200–1,800 min for 3 shards — fits; overage is $0.008/min if it ever happens |
| Public repo temptation | corpus becomes scrapeable | keep PDFs private (section 3 Option A/B) |
| Scanned paper (no text layer) | Tier 0 finds <25 lines | auto-OCR via tesseract (installed in workflow); OCR papers skip diagram crops for now (v2) |
| Diagram crop slightly off | band between question and next question | acceptable v1; refine with drawing-object bboxes in v2 |
| Disk/bloat on Actions | artifacts big | crops are small PNGs; artifacts auto-expire in 30 days |
| You re-run the whole thing | double inserts | `file_hash` UNIQUE + `question_hash` UNIQUE make it idempotent; AI responses served from cache |
| Broken Hindi slips through | garbled Kruti-Dev text in a question | residual noise ~1–3% of chars on some papers; clustering (trigram/TF-IDF) and embeddings tolerate it; review queue catches worst cases |

## 5. Supabase setup (once)

1. Run `supabase_schema.sql` in the SQL editor (tables, indexes, coverage view, RLS).
2. Create a **public** Storage bucket named `pyq-diagrams` (Storage → New bucket).
   The extractor uploads crops and fills `questions.diagram_url` automatically
   when `--db` is on.
3. Sanity-check after a pilot push:
   `select status, count(*) from subject_coverage group by status;`

## 6. The review queue (Tier 3)

Rows with `needs_review = true` are papers where both rules AND AI failed
(expect 2–5%: heavily corrupted scans, exotic layouts). Don't build the review
UI yet — for v1 a simple query + manual fix in the Supabase table editor is
enough:
`select id, subject_code, text from questions where needs_review;`

## 7. Honest limits of v1 (measured on the 6-paper demo, not guessed)

- Stray watermark chars can survive inside words ("app2lications") on papers
  that pass the gate — ~1–3% character noise worst case. Clustering and
  semantic search tolerate it; a Gemma polish pass for accepted papers is a
  possible (quota-costing) v2 toggle.
- Marks come from section specs ("2 x 7 = 14"), printed trailing columns, or
  explicit "(7)" tokens; genuinely ambiguous rows keep `marks = null` rather
  than a guess.
- Diagram crops exist for text-layer papers only (OCR coordinates need a
  mapping pass — v2).
- Format families verified: 2020-21 (KMC tables a.–j. + Marks/CO columns),
  2021-22 (mixed), 2022-23 bilingual ("(a)" + "2 x 7 = 14" specs). Older
  2015–2019 formats parse via the numbered-question path but are **not yet
  proven** — the 30-paper pilot on your machine is what proves them.
