-- ============================================================
-- AKTU PYQ Intelligence System — v2 Schema
-- Run entire file in Supabase SQL Editor
-- ============================================================

-- Universities
CREATE TABLE IF NOT EXISTS universities (
  id          SERIAL PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  short_code  TEXT UNIQUE,
  country     TEXT DEFAULT 'India',
  is_active   BOOLEAN DEFAULT TRUE,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO universities (name, short_code) VALUES
  ('Dr. A.P.J. Abdul Kalam Technical University', 'AKTU')
ON CONFLICT (name) DO NOTHING;

-- Questions (master table)
CREATE TABLE IF NOT EXISTS questions (
  id                      SERIAL PRIMARY KEY,
  question_text           TEXT NOT NULL,
  normalized_text         TEXT,
  question_hash           TEXT,                -- SHA-256 of normalized_text, for exact dedup
  university              TEXT DEFAULT 'AKTU' REFERENCES universities(short_code),
  subject                 TEXT,
  subject_code            TEXT,                -- e.g. EE-301, CS-501
  branch                  TEXT,
  programme               TEXT,
  semester                INTEGER,
  unit                    INTEGER,             -- 1–5 parsed from "UNIT-I" header
  unit_topic              TEXT,                -- topic label from unit header if present
  module_topic            TEXT,
  question_type           TEXT DEFAULT 'theory'
                            CHECK (question_type IN ('theory','numerical','short','diagram','other')),
  difficulty_level        TEXT,
  marks_weightage         INTEGER,
  has_diagram             BOOLEAN DEFAULT FALSE,
  diagram_url             TEXT,                -- Supabase Storage public URL
  has_math                BOOLEAN DEFAULT FALSE,
  sub_parts               TEXT[] DEFAULT '{}',
  cluster_id              INTEGER,
  year_appeared           INTEGER[] DEFAULT '{}',
  exam_sessions           TEXT[] DEFAULT '{}', -- e.g. ['2022-odd','2023-even']
  frequency_count         INTEGER DEFAULT 1,
  first_appearance_year   INTEGER,
  last_appearance_year    INTEGER,
  trend_direction         TEXT DEFAULT 'insufficient_data',
  pattern_type            TEXT,
  primary_topic           TEXT,
  concept_tags            TEXT[] DEFAULT '{}',
  importance_score        FLOAT DEFAULT 0.0,
  exam_probability_score  FLOAT DEFAULT 0.0,
  must_revise_flag        BOOLEAN DEFAULT FALSE,
  user_views_count        INTEGER DEFAULT 0,
  user_confirmed_count    INTEGER DEFAULT 0,   -- "this appeared in my exam" clicks
  page_number             INTEGER,
  created_at              TIMESTAMPTZ DEFAULT NOW(),
  updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- Safe add columns for existing tables
ALTER TABLE questions ADD COLUMN IF NOT EXISTS question_hash           TEXT;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS subject_code            TEXT;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS unit                    INTEGER;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS unit_topic              TEXT;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS has_diagram             BOOLEAN DEFAULT FALSE;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS diagram_url             TEXT;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS has_math                BOOLEAN DEFAULT FALSE;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS sub_parts               TEXT[] DEFAULT '{}';
ALTER TABLE questions ADD COLUMN IF NOT EXISTS exam_sessions           TEXT[] DEFAULT '{}';
ALTER TABLE questions ADD COLUMN IF NOT EXISTS user_confirmed_count    INTEGER DEFAULT 0;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS page_number             INTEGER;

-- Unique constraint on hash to prevent duplicate inserts
ALTER TABLE questions DROP CONSTRAINT IF EXISTS questions_question_hash_key;
ALTER TABLE questions ADD CONSTRAINT questions_question_hash_key UNIQUE (question_hash);

-- Fix question_type constraint to include diagram
ALTER TABLE questions DROP CONSTRAINT IF EXISTS questions_question_type_check;
ALTER TABLE questions ADD CONSTRAINT questions_question_type_check
  CHECK (question_type IN ('theory','numerical','short','diagram','other'));

-- Clusters
CREATE TABLE IF NOT EXISTS clusters (
  id                      SERIAL PRIMARY KEY,
  representative_question TEXT NOT NULL,
  university              TEXT DEFAULT 'AKTU',
  subject                 TEXT,
  unit                    INTEGER,
  frequency               INTEGER DEFAULT 0,
  years                   INTEGER[] DEFAULT '{}',
  canonical_question      TEXT,
  created_at              TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE clusters ADD COLUMN IF NOT EXISTS unit INTEGER;

-- PDF submissions (student queue)
CREATE TABLE IF NOT EXISTS pdf_submissions (
  id               SERIAL PRIMARY KEY,
  filename         TEXT NOT NULL,
  file_hash        TEXT UNIQUE NOT NULL,
  university       TEXT DEFAULT 'AKTU',
  subject          TEXT,
  subject_code     TEXT,
  branch           TEXT,
  programme        TEXT,
  semester         INTEGER,
  year             INTEGER,
  exam_session     TEXT,
  submitted_by     TEXT DEFAULT 'anonymous',
  status           TEXT DEFAULT 'pending'
                     CHECK (status IN ('pending','approved','rejected','duplicate')),
  rejection_reason TEXT,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE pdf_submissions ADD COLUMN IF NOT EXISTS subject_code  TEXT;
ALTER TABLE pdf_submissions ADD COLUMN IF NOT EXISTS exam_session   TEXT;

-- Scrape queue (bulk import pipeline)
CREATE TABLE IF NOT EXISTS scrape_queue (
  id            SERIAL PRIMARY KEY,
  pdf_url       TEXT UNIQUE NOT NULL,
  status        TEXT DEFAULT 'pending'
                  CHECK (status IN ('pending','processing','done','failed')),
  error_message TEXT,
  subject       TEXT,
  subject_code  TEXT,
  branch        TEXT,
  programme     TEXT,
  semester      INTEGER,
  year          INTEGER,
  exam_session  TEXT,
  questions_extracted INTEGER DEFAULT 0,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  processed_at  TIMESTAMPTZ
);

-- Analytics / visitor tracking
CREATE TABLE IF NOT EXISTS analytics_events (
  id          BIGSERIAL PRIMARY KEY,
  event_type  TEXT NOT NULL,  -- 'page_view','search','contribute','question_view','confirm_appeared'
  page        TEXT,
  metadata    JSONB DEFAULT '{}',
  session_id  TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Aggregate counters (updated by triggers or backend jobs — cheap to query)
CREATE TABLE IF NOT EXISTS site_counters (
  key         TEXT PRIMARY KEY,
  value       BIGINT DEFAULT 0,
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);
INSERT INTO site_counters (key, value) VALUES
  ('total_visitors', 0),
  ('total_searches', 0),
  ('total_contributors', 0),
  ('total_questions', 0),
  ('total_papers', 0)
ON CONFLICT (key) DO NOTHING;

-- ── Indexes ──────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_questions_university    ON questions(university);
CREATE INDEX IF NOT EXISTS idx_questions_subject       ON questions(subject);
CREATE INDEX IF NOT EXISTS idx_questions_subject_code  ON questions(subject_code);
CREATE INDEX IF NOT EXISTS idx_questions_branch        ON questions(branch);
CREATE INDEX IF NOT EXISTS idx_questions_programme     ON questions(programme);
CREATE INDEX IF NOT EXISTS idx_questions_unit          ON questions(unit);
CREATE INDEX IF NOT EXISTS idx_questions_type          ON questions(question_type);
CREATE INDEX IF NOT EXISTS idx_questions_frequency     ON questions(frequency_count DESC);
CREATE INDEX IF NOT EXISTS idx_questions_importance    ON questions(importance_score DESC);
CREATE INDEX IF NOT EXISTS idx_questions_cluster       ON questions(cluster_id);
CREATE INDEX IF NOT EXISTS idx_questions_hash          ON questions(question_hash);
CREATE INDEX IF NOT EXISTS idx_questions_semester      ON questions(semester);
CREATE INDEX IF NOT EXISTS idx_questions_fts           ON questions USING GIN (to_tsvector('english', question_text));
CREATE INDEX IF NOT EXISTS idx_questions_uni_sub_unit  ON questions(university, subject, unit);
CREATE INDEX IF NOT EXISTS idx_submissions_status      ON pdf_submissions(status);
CREATE INDEX IF NOT EXISTS idx_submissions_hash        ON pdf_submissions(file_hash);
CREATE INDEX IF NOT EXISTS idx_scrape_status           ON scrape_queue(status);
CREATE INDEX IF NOT EXISTS idx_analytics_type          ON analytics_events(event_type);
CREATE INDEX IF NOT EXISTS idx_analytics_created       ON analytics_events(created_at DESC);

-- ── Auto-update updated_at ────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS questions_updated_at ON questions;
CREATE TRIGGER questions_updated_at
  BEFORE UPDATE ON questions
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── Helper view: paper_context (joins question back to its paper header) ───
-- Use this to show full context for any question
CREATE OR REPLACE VIEW question_with_context AS
SELECT
  q.*,
  -- Derived: "Seen in N exams" label
  CASE
    WHEN q.frequency_count >= 6 THEN 'Seen in ' || q.frequency_count || '+ exams 🔥'
    WHEN q.frequency_count >= 3 THEN 'Seen in ' || q.frequency_count || ' exams'
    WHEN q.frequency_count = 2  THEN 'Seen in 2 exams'
    ELSE 'Seen in 1 exam'
  END AS seen_in_label,
  -- Year range label
  CASE
    WHEN q.first_appearance_year IS NOT NULL AND q.last_appearance_year IS NOT NULL
    THEN q.first_appearance_year::TEXT || '–' || q.last_appearance_year::TEXT
    ELSE NULL
  END AS year_range_label
FROM questions q;
