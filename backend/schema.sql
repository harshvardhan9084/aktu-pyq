-- ============================================================
-- AKTU PYQ Intelligence System — Supabase Database Schema
-- Paste this entire file into Supabase SQL Editor and click Run
-- ============================================================

CREATE TABLE IF NOT EXISTS questions (
  id                      SERIAL PRIMARY KEY,
  question_text           TEXT NOT NULL,
  normalized_text         TEXT,
  subject                 TEXT,
  branch                  TEXT,
  semester                INTEGER,
  unit                    INTEGER,
  module_topic            TEXT,
  question_type           TEXT DEFAULT 'theory' CHECK (question_type IN ('theory','numerical','short','other')),
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

CREATE TABLE IF NOT EXISTS clusters (
  id                      SERIAL PRIMARY KEY,
  representative_question TEXT NOT NULL,
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
  subject         TEXT,
  branch          TEXT,
  semester        INTEGER,
  year            INTEGER,
  submitted_by    TEXT DEFAULT 'anonymous',
  status          TEXT DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  rejection_reason TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_questions_subject    ON questions(subject);
CREATE INDEX IF NOT EXISTS idx_questions_unit       ON questions(unit);
CREATE INDEX IF NOT EXISTS idx_questions_type       ON questions(question_type);
CREATE INDEX IF NOT EXISTS idx_questions_frequency  ON questions(frequency_count DESC);
CREATE INDEX IF NOT EXISTS idx_questions_importance ON questions(importance_score DESC);
CREATE INDEX IF NOT EXISTS idx_questions_cluster    ON questions(cluster_id);
CREATE INDEX IF NOT EXISTS idx_submissions_status   ON pdf_submissions(status);
CREATE INDEX IF NOT EXISTS idx_submissions_hash     ON pdf_submissions(file_hash);

-- Full-text search index
CREATE INDEX IF NOT EXISTS idx_questions_fts
  ON questions USING GIN (to_tsvector('english', question_text));

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS questions_updated_at ON questions;
CREATE TRIGGER questions_updated_at
  BEFORE UPDATE ON questions
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
