-- ============================================================
-- AKTU PYQ Intelligence System — Supabase Database Schema
-- Multi-university ready — supports AKTU and future universities
-- Paste this entire file into Supabase SQL Editor and click Run
-- ============================================================

CREATE TABLE IF NOT EXISTS universities (
  id                      SERIAL PRIMARY KEY,
  name                    TEXT NOT NULL UNIQUE,
  short_code              TEXT UNIQUE,
  country                 TEXT DEFAULT 'India',
  is_active               BOOLEAN DEFAULT TRUE,
  created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- Seed AKTU as the default university
INSERT INTO universities (name, short_code) VALUES
  ('Dr. A.P.J. Abdul Kalam Technical University', 'AKTU')
ON CONFLICT (name) DO NOTHING;

-- NOTE:
-- This schema is migration-friendly for an existing `questions` table.
-- Using only `CREATE TABLE IF NOT EXISTS ...` will NOT add missing columns
-- to a previously-created table. So we also run ALTER TABLE ... ADD COLUMN IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS questions (
  id                      SERIAL PRIMARY KEY,
  question_text           TEXT NOT NULL,
  normalized_text         TEXT,
  university              TEXT DEFAULT 'AKTU' REFERENCES universities(short_code),
  subject                 TEXT,
  branch                  TEXT,
  programme               TEXT,                 -- B.Tech, MCA, MBA, Diploma, M.Tech
  semester                INTEGER,
  unit                    INTEGER,
  module_topic            TEXT,
  question_type           TEXT DEFAULT 'theory' CHECK (question_type IN ('theory','numerical','short','other','diagram')),
  difficulty_level        TEXT,
  marks_weightage         INTEGER,
  cluster_id              INTEGER,
  year_appeared           INTEGER[] DEFAULT '{}',
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
  created_at              TIMESTAMPTZ DEFAULT NOW(),
  updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- Ensure required columns exist (fixes errors like:
--   column questions.university does not exist
--   column questions.programme does not exist)
ALTER TABLE questions ADD COLUMN IF NOT EXISTS university              TEXT DEFAULT 'AKTU';
ALTER TABLE questions ADD COLUMN IF NOT EXISTS subject                 TEXT;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS branch                  TEXT;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS programme               TEXT;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS semester                INTEGER;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS unit                    INTEGER;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS module_topic            TEXT;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS question_type           TEXT DEFAULT 'theory';
ALTER TABLE questions ADD COLUMN IF NOT EXISTS frequency_count         INTEGER DEFAULT 1;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS importance_score        FLOAT DEFAULT 0.0;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS cluster_id              INTEGER;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS year_appeared           INTEGER[] DEFAULT '{}';
ALTER TABLE questions ADD COLUMN IF NOT EXISTS first_appearance_year   INTEGER;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS last_appearance_year    INTEGER;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS trend_direction         TEXT DEFAULT 'insufficient_data';
ALTER TABLE questions ADD COLUMN IF NOT EXISTS pattern_type            TEXT;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS primary_topic           TEXT;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS concept_tags            TEXT[] DEFAULT '{}';
ALTER TABLE questions ADD COLUMN IF NOT EXISTS exam_probability_score  FLOAT DEFAULT 0.0;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS must_revise_flag        BOOLEAN DEFAULT FALSE;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS user_views_count        INTEGER DEFAULT 0;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS created_at              TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE questions ADD COLUMN IF NOT EXISTS updated_at              TIMESTAMPTZ DEFAULT NOW();


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

CREATE TABLE IF NOT EXISTS pdf_submissions (
  id              SERIAL PRIMARY KEY,
  filename        TEXT NOT NULL,
  file_hash       TEXT UNIQUE NOT NULL,
  university      TEXT DEFAULT 'AKTU',
  subject         TEXT,
  branch          TEXT,
  programme       TEXT,
  semester        INTEGER,
  year            INTEGER,
  submitted_by    TEXT DEFAULT 'anonymous',
  status          TEXT DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  rejection_reason TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_questions_university ON questions(university);
CREATE INDEX IF NOT EXISTS idx_questions_subject    ON questions(subject);
CREATE INDEX IF NOT EXISTS idx_questions_branch     ON questions(branch);
CREATE INDEX IF NOT EXISTS idx_questions_programme  ON questions(programme);
CREATE INDEX IF NOT EXISTS idx_questions_unit       ON questions(unit);
CREATE INDEX IF NOT EXISTS idx_questions_type       ON questions(question_type);
CREATE INDEX IF NOT EXISTS idx_questions_frequency  ON questions(frequency_count DESC);
CREATE INDEX IF NOT EXISTS idx_questions_importance ON questions(importance_score DESC);
CREATE INDEX IF NOT EXISTS idx_questions_cluster    ON questions(cluster_id);
CREATE INDEX IF NOT EXISTS idx_submissions_status   ON pdf_submissions(status);
CREATE INDEX IF NOT EXISTS idx_submissions_hash     ON pdf_submissions(file_hash);
CREATE INDEX IF NOT EXISTS idx_submissions_university ON pdf_submissions(university);

-- Full-text search index
CREATE INDEX IF NOT EXISTS idx_questions_fts
  ON questions USING GIN (to_tsvector('english', question_text));

-- Composite index for common search pattern: university + subject + unit
CREATE INDEX IF NOT EXISTS idx_questions_uni_sub_unit
  ON questions(university, subject, unit);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS questions_updated_at ON questions;
CREATE TRIGGER questions_updated_at
  BEFORE UPDATE ON questions
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
