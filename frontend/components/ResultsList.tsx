'use client'
import { BookOpen, Calendar, BarChart2, Star } from 'lucide-react'
import type { Question } from '@/lib/supabase'

const TYPE_COLORS: Record<string, string> = {
  theory: 'bg-jade-500/15 text-jade-300 border-jade-500/20',
  numerical: 'bg-gold-500/15 text-gold-300 border-gold-500/20',
  short: 'bg-ink-700 text-ink-300 border-ink-600',
  other: 'bg-ink-700 text-ink-300 border-ink-600',
}

function SkeletonCard() {
  return (
    <div className="glass rounded-xl p-5 animate-pulse">
      <div className="h-4 bg-ink-700 rounded w-3/4 mb-3" />
      <div className="h-3 bg-ink-700 rounded w-1/2 mb-4" />
      <div className="h-2 bg-ink-800 rounded w-full mb-1" />
      <div className="flex gap-2 mt-3">
        <div className="h-5 w-16 bg-ink-700 rounded-full" />
        <div className="h-5 w-12 bg-ink-700 rounded-full" />
        <div className="h-5 w-20 bg-ink-700 rounded-full" />
      </div>
    </div>
  )
}

export default function ResultsList({ results, loading }: { results: Question[], loading: boolean }) {
  if (loading) {
    return (
      <div className="space-y-3">
        <div className="h-6 bg-ink-800 rounded w-40 mb-5 animate-pulse" />
        {Array.from({ length: 5 }).map((_, i) => <SkeletonCard key={i} />)}
      </div>
    )
  }

  if (results.length === 0) {
    return (
      <div className="glass rounded-2xl p-10 text-center">
        <BookOpen size={32} className="text-ink-600 mx-auto mb-3" />
        <p className="text-ink-400 text-sm">No questions found for that query.</p>
        <p className="text-ink-600 text-xs mt-1">Try broadening your search or selecting "All Units".</p>
      </div>
    )
  }

  const maxFreq = Math.max(...results.map(r => r.frequency_count), 1)

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <h2 className="font-display text-xl font-bold text-ink-50">
          {results.length} question{results.length !== 1 ? 's' : ''} found
        </h2>
        <span className="text-xs text-ink-500">Ranked by repetition frequency</span>
      </div>

      <div className="space-y-3">
        {results.map((q, i) => {
          const pct = Math.round((q.frequency_count / maxFreq) * 100)
          const typeClass = TYPE_COLORS[q.question_type] ?? TYPE_COLORS.other

          return (
            <div key={q.id} className="glass rounded-xl p-5 hover:bg-white/[0.05] transition-all duration-200">
              <div className="flex items-start gap-3 mb-3">
                <span className="flex-shrink-0 w-6 h-6 rounded-full glass flex items-center justify-center text-xs text-ink-400 font-mono mt-0.5">{i + 1}</span>
                <p className="text-ink-100 text-sm leading-relaxed flex-1 font-medium">{q.question_text}</p>
                <div className="flex-shrink-0 flex flex-col items-center glass px-3 py-1.5 rounded-lg">
                  <span className="font-display font-bold text-gold-400 text-lg leading-none">×{q.frequency_count}</span>
                  <span className="text-ink-500 text-[10px] leading-none mt-0.5">asked</span>
                </div>
              </div>

              <div className="h-1 bg-ink-800 rounded-full mb-3 ml-9">
                <div className="h-full bg-gradient-to-r from-gold-500/60 to-gold-400/40 rounded-full transition-all duration-500" style={{ width: `${pct}%` }} />
              </div>

              <div className="flex flex-wrap items-center gap-2 ml-9">
                <span className={`tag-pill border ${typeClass} capitalize`}>{q.question_type}</span>
                {q.unit && <span className="tag-pill">Unit {q.unit}</span>}
                {q.marks_weightage && <span className="tag-pill">{q.marks_weightage}M</span>}
                {q.concept_tags?.slice(0, 2).map(tag => <span key={tag} className="tag-pill">{tag}</span>)}
                {q.must_revise_flag && (
                  <span className="inline-flex items-center gap-1 tag-pill border-gold-500/30 text-gold-400">
                    <Star size={9} fill="currentColor" /> Must revise
                  </span>
                )}
                <div className="ml-auto flex items-center gap-3 text-xs text-ink-500">
                  {q.first_appearance_year && q.last_appearance_year && (
                    <span className="flex items-center gap-1"><Calendar size={11} />{q.first_appearance_year}–{q.last_appearance_year}</span>
                  )}
                  {q.trend_direction && (
                    <span className="flex items-center gap-1"><BarChart2 size={11} />{q.trend_direction}</span>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
