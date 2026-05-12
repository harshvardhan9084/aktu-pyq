import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!

export const supabase = createClient(supabaseUrl, supabaseAnonKey)

export type Question = {
  id: number
  question_text: string
  subject: string
  branch: string
  semester: number | null
  unit: number | null
  question_type: 'theory' | 'numerical' | 'short' | 'other'
  difficulty_level: string | null
  marks_weightage: number | null
  cluster_id: number | null
  year_appeared: number[]
  frequency_count: number
  first_appearance_year: number | null
  last_appearance_year: number | null
  trend_direction: string | null
  pattern_type: string | null
  primary_topic: string | null
  concept_tags: string[]
  importance_score: number
  must_revise_flag: boolean
  created_at: string
}

export type PDFSubmission = {
  id: number
  filename: string
  file_hash: string
  subject: string | null
  semester: number | null
  year: number | null
  submitted_by: string
  status: 'pending' | 'approved' | 'rejected'
  rejection_reason: string | null
  created_at: string
}
