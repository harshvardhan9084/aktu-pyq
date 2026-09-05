-- ============================================================================
-- AKTU-PYQ  ::  Supabase schema.sql  (v1)
-- ============================================================================
-- HOW TO RUN
--   1. Supabase Dashboard -> your project -> SQL Editor -> New query
--   2. Paste this whole file -> Run
--   (All statements are idempotent-safe: use IF NOT EXISTS / OR REPLACE,
--    so re-running after edits won't destroy data.)
--
-- WHAT'S INSIDE
--   - 3 extensions: pgcrypto (uuid), vector (pgvector for AI search), pg_trgm
--     (fuzzy text matching for dedupe + validation)
--   - 5 tables: subjects -> papers -> questions -> occurrences, + clusters
--   - Indexes: lookup speed, HNSW vector index (cosine), trigram fuzzy index
--   - subject_coverage VIEW: the "COMPLETE / PARTIAL / EARLY / COMING" badge
--     engine - computed from data, so it can never claim what you don't have
--   - Row Level Security: anonymous visitors can READ, only your service key
--     (pipeline/admin) can WRITE
--
-- DESIGN NOTES
--   * A question row = text + subject context. WHERE it appeared lives in
--     occurrences. Its across-years duplicates live in clusters.
--     Frequency & importance are properties of the CLUSTER (derived, re-
--     computable any time) - never stored as hand-written values.
--   * papers.file_hash UNIQUE = idempotent ingestion: re-running the pipeline
--     on the same PDF inserts nothing twice.
--   * questions.embedding = 384-dim (all-MiniLM-L6-v2). If you switch models,
--     change the dimension here AND re-embed everything.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0) EXTENSIONS
-- ----------------------------------------------------------------------------
create extension if not exists pgcrypto;   -- gen_random_uuid()
create extension if not exists vector;     -- pgvector (AI semantic search)
create extension if not exists pg_trgm;    -- fuzzy % similarity on text

-- ----------------------------------------------------------------------------
-- 1) ENUMS  (extend later, e.g. add 'Diploma' to course_t, never delete values)
-- ----------------------------------------------------------------------------
do $$ begin
  create type course_t as enum ('BTech','BPharm','MCA','BBA','BCA','MBA','Other');
exception when duplicate_object then null; end $$;

do $$ begin
  create type qtype_t as enum ('theory','numerical','short','diagram','other');
exception when duplicate_object then null; end $$;

-- ----------------------------------------------------------------------------
-- 2) TABLES
-- ----------------------------------------------------------------------------

-- 2a) SUBJECTS: one canonical row per subject code (both AKTU code schemes)
create table if not exists subjects (
  code            text primary key,            -- 'KCS-401', 'BCS401', 'BMC303'
  name            text not null,
  course          course_t not null,
  branch          text,                        -- 'CSE', 'AIML', null = common
  semester        int check (semester between 1 and 8),
  alt_codes       text[] default '{}',         -- old+new scheme cross-links
  units_json      jsonb default '[]',          -- [{"unit":1,"topic":"..."}]
  coverage_target int  default 8,              -- years expected (badge engine)
  is_active       boolean default true,        -- false = coming soon
  created_at      timestamptz default now(),
  updated_at      timestamptz default now()
);

-- 2b) PAPERS: one row per physical PDF you ingested
create table if not exists papers (
  id            uuid primary key default gen_random_uuid(),
  subject_code  text not null references subjects(code),
  year          text not null,                 -- '2022-23'
  file_hash     text not null unique,          -- sha256 of PDF -> idempotency
  storage_url   text,                          -- Supabase Storage path
  source        text default 'ryzenstudy',     -- provenance
  source_url    text,
  is_text_layer boolean default true,          -- false = scanned/OCR only
  ingested_at   timestamptz default now(),
  unique (subject_code, year, file_hash)
);

-- 2c) QUESTIONS: the "mobile question object"
create table if not exists questions (
  id                    uuid primary key default gen_random_uuid(),
  subject_code          text not null references subjects(code),
  text                  text not null,         -- cleaned question text
  text_normalized       text not null,         -- lowercase/no-punct for matching
  question_hash         text not null,         -- sha256(text_normalized)
  language              text default 'en',     -- 'en' | 'hi' | 'bi'
  question_type         qtype_t default 'other',
  marks                 int,
  unit                  int,
  unit_topic            text,
  choice_group          uuid,                  -- same group = (a) OR (b) pair
  parent_id             uuid references questions(id),  -- sub-question parent
  has_diagram           boolean default false,
  diagram_url           text,
  embedding             vector(384),           -- all-MiniLM-L6-v2
  extraction_confidence real check (extraction_confidence between 0 and 1),
  needs_review          boolean default false,
  created_at            timestamptz default now(),
  updated_at            timestamptz default now(),
  unique (subject_code, question_hash)         -- exact dedupe per subject
);

-- 2d) OCCURRENCES: "this question appeared in THAT paper, Q-no, marks"
create table if not exists occurrences (
  id                    uuid primary key default gen_random_uuid(),
  question_id           uuid not null references questions(id) on delete cascade,
  paper_id              uuid not null references papers(id) on delete cascade,
  year                  text not null,         -- denormalized from paper: fast
  q_no                  text,                  -- '2(b)' as printed on paper
  marks                 int,
  extraction_confidence real,
  created_at            timestamptz default now(),
  unique (question_id, paper_id)               -- same Q can't occur twice in 1 paper
);

-- 2e) CLUSTERS: across-years duplicates -> frequency + importance live HERE
create table if not exists clusters (
  id              uuid primary key default gen_random_uuid(),
  subject_code    text not null references subjects(code),
  label           text,                        -- short human label, optional
  member_ids      uuid[] default '{}',         -- question ids in this cluster
  freq_count      int default 0,               -- distinct years in cluster
  importance      numeric(5,2) default 0,      -- 0-100 marks+recency weighted
  method          text default 'tfidf-dbscan', -- provenance of the clustering
  model_version   text,                        -- pipeline/prompt version
  last_scored_at  timestamptz,
  created_at      timestamptz default now()
);

-- ----------------------------------------------------------------------------
-- 3) INDEXES
-- ----------------------------------------------------------------------------
create index if not exists idx_papers_subject_year   on papers (subject_code, year);
create index if not exists idx_questions_subject     on questions (subject_code);
create index if not exists idx_questions_unit        on questions (subject_code, unit);
create index if not exists idx_questions_type        on questions (question_type);
create index if not exists idx_questions_review      on questions (subject_code)
                                                     where needs_review;
create index if not exists idx_questions_group       on questions (choice_group)
                                                     where choice_group is not null;
create index if not exists idx_occurrences_question  on occurrences (question_id);
create index if not exists idx_occurrences_paper     on occurrences (paper_id);
create index if not exists idx_occurrences_year      on occurrences (year);
create index if not exists idx_clusters_subject      on clusters (subject_code);

-- Vector index (AI best-match search). HNSW = fast approximate cosine.
-- NOTE: create AFTER bulk-ingesting if you have millions of rows (faster loads);
--       fine to keep ON for a v1-sized dataset.
create index if not exists idx_questions_embedding
  on questions using hnsw (embedding vector_cosine_ops);

-- Fuzzy index: near-duplicate detection & "did the LLM invent this?" checks
create index if not exists idx_questions_trgm
  on questions using gin (text_normalized gin_trgm_ops);

-- ----------------------------------------------------------------------------
-- 4) updated_at AUTO-TOUCH
-- ----------------------------------------------------------------------------
create or replace function set_updated_at() returns trigger as $$
begin new.updated_at = now(); return new; end $$ language plpgsql;

drop trigger if exists trg_subjects_updated  on subjects;
create trigger trg_subjects_updated  before update on subjects
  for each row execute function set_updated_at();
drop trigger if exists trg_questions_updated on questions;
create trigger trg_questions_updated before update on questions
  for each row execute function set_updated_at();

-- ----------------------------------------------------------------------------
-- 5) SUBJECT_COVERAGE VIEW  <- the badge engine ("we don't claim what we lack")
-- ----------------------------------------------------------------------------
-- status logic:
--   COMING   : subject row exists, zero papers ingested
--   EARLY    : 1 year indexed            -> show "early signal" only
--   PARTIAL  : 2 .. target-1 years
--   COMPLETE : >= min(target, 7) years AND has clustered questions
-- Everything is COMPUTED - a subject can never be marked complete by hand.
-- ----------------------------------------------------------------------------
create or replace view subject_coverage as
with per_subject as (
  select
    s.code,
    s.name,
    s.course,
    s.branch,
    s.semester,
    s.coverage_target,
    s.is_active,
    coalesce(p.years_indexed, 0)                 as years_indexed,
    coalesce(p.paper_count, 0)                   as paper_count,
    coalesce(q.question_count, 0)                as question_count,
    coalesce(c.cluster_count, 0)                 as cluster_count,
    coalesce(r.repeated_question_count, 0)       as repeated_question_count,
    coalesce(o.confirmed_occurrences, 0)         as confirmed_occurrences,
    p.last_ingested
  from subjects s
  left join (
    select subject_code,
           count(distinct year)          as years_indexed,
           count(*)                      as paper_count,
           max(ingested_at)              as last_ingested
    from papers group by subject_code
  ) p on p.subject_code = s.code
  left join (
    select subject_code, count(*) as question_count
    from questions group by subject_code
  ) q on q.subject_code = s.code
  left join (
    select subject_code, count(*) as cluster_count
    from clusters group by subject_code
  ) c on c.subject_code = s.code
  left join (
    select cl.subject_code, count(*) as repeated_question_count
    from clusters cl where cl.freq_count >= 3
    group by cl.subject_code
  ) r on r.subject_code = s.code
)
select
  ps.*,
  case
    when not ps.is_active or ps.years_indexed = 0            then 'coming'
    when ps.years_indexed < 2                                then 'early'
    when ps.years_indexed >= least(ps.coverage_target, 7)
         and ps.cluster_count > 0                            then 'complete'
    else 'partial'
  end as status
from per_subject ps;

-- ----------------------------------------------------------------------------
-- 6) ROW LEVEL SECURITY
--    anon (website visitors): SELECT only
--    service_role (your pipeline/admin): full access via service key
--    -> never create anon INSERT policies unless you add rate-limited
--       endpoints in front; upload-by-form is a spam magnet.
-- ----------------------------------------------------------------------------
alter table subjects    enable row level security;
alter table papers      enable row level security;
alter table questions   enable row level security;
alter table occurrences enable row level security;
alter table clusters    enable row level security;

drop policy if exists anon_read_subjects    on subjects;
create policy anon_read_subjects on subjects    for select using (true);
drop policy if exists anon_read_papers      on papers;
create policy anon_read_papers      on papers      for select using (true);
drop policy if exists anon_read_questions   on questions;
create policy anon_read_questions   on questions   for select using (true);
drop policy if exists anon_read_occurrences on occurrences;
create policy anon_read_occurrences on occurrences for select using (true);
drop policy if exists anon_read_clusters    on clusters;
create policy anon_read_clusters    on clusters    for select using (true);

-- ----------------------------------------------------------------------------
-- 7) HANDY QUERY EXAMPLES (copy-paste into SQL editor to sanity-check)
-- ----------------------------------------------------------------------------
-- Top repeated questions of one subject:
--   select q.text, cl.freq_count, cl.importance, q.marks, q.unit
--   from clusters cl join questions q on q.id = any(cl.member_ids)
--   where cl.subject_code = 'KCS-401'
--   order by cl.importance desc limit 20;
--
-- Semantic best-match (pgvector), "questions like <student query>":
--   with q as (select '[0.1, 0.2, ...]'::vector as v)   -- from your embedder
--   select text, embedding <=> q.v as distance
--   from questions, q where subject_code = 'KCS-401'
--   order by embedding <=> q.v limit 20;
--
-- Coverage dashboard (drives the /coverage page):
--   select status, count(*) from subject_coverage group by status order by 1;
-- ============================================================================
