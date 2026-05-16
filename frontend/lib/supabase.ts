import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabase = createClient(supabaseUrl, supabaseAnonKey)

export type Question = {
  id: number
  question_text: string
  normalized_text: string | null
  question_hash: string | null
  university: string
  subject: string | null
  subject_code: string | null
  branch: string | null
  programme: string | null
  semester: number | null
  unit: number | null
  unit_topic: string | null
  question_type: 'theory' | 'numerical' | 'short' | 'diagram' | 'other'
  difficulty_level: string | null
  marks_weightage: number | null
  has_diagram: boolean
  diagram_url: string | null
  has_math: boolean
  sub_parts: string[]
  cluster_id: number | null
  year_appeared: number[]
  exam_sessions: string[]
  frequency_count: number
  first_appearance_year: number | null
  last_appearance_year: number | null
  trend_direction: string | null
  pattern_type: string | null
  primary_topic: string | null
  concept_tags: string[]
  importance_score: number
  exam_probability_score: number
  must_revise_flag: boolean
  user_views_count: number
  user_confirmed_count: number
  page_number: number | null
  created_at: string
  // Computed by backend enrich_question()
  seen_in_label: string
}

export type PDFSubmission = {
  id: number
  filename: string
  file_hash: string
  university: string
  subject: string | null
  subject_code: string | null
  branch: string | null
  programme: string | null
  semester: number | null
  year: number | null
  exam_session: string | null
  submitted_by: string
  status: 'pending' | 'approved' | 'rejected' | 'duplicate'
  rejection_reason: string | null
  question_count?: number
  created_at: string
}

export type ScrapeQueueItem = {
  id: number
  pdf_url: string
  status: 'pending' | 'processing' | 'done' | 'failed'
  error_message: string | null
  subject: string | null
  subject_code: string | null
  branch: string | null
  programme: string | null
  semester: number | null
  year: number | null
  exam_session: string | null
  questions_extracted: number
  created_at: string
  processed_at: string | null
}

export type PublicStats = {
  total_questions: number
  total_papers: number
  total_subjects: number
}
