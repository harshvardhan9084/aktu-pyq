'use client'
import { useState } from 'react'
import { BookOpen, Star, ChevronDown, ChevronUp, Share2, ThumbsUp, Image } from 'lucide-react'
import type { Question } from '@/lib/supabase'

const TYPE_COLORS: Record<string, string> = {
  theory: 'bg-jade-500/15 text-jade-300 border-jade-500/20',
  numerical: 'bg-gold-500/15 text-gold-300 border-gold-500/20',
  short: 'bg-ink-700 text-ink-300 border-ink-600',
  diagram: 'bg-rose-500/15 text-rose-300 border-rose-500/20',
  other: 'bg-ink-700 text-ink-300 border-ink-600',
}

const TREND_ICON: Record<string, string> = {
  rising: '↑',
  consistent: '→',
  declining: '↓',
  intermittent: '~',
  insufficient_data: '',
}

function SkeletonCard() {
  return (
    <div className="glass rounded-xl p-5 animate-pulse">
      <div className="h-4 bg-ink-700 rounded w-3/4 mb-3" />
      <div className="h-3 bg-ink-700 rounded w-1/2 mb-4" />
      <div className="h-1 bg-ink-800 rounded w-full mb-3" />
      <div className="flex gap-2 mt-3">
        <div className="h-5 w-16 bg-ink-700 rounded-full" />
        <div className="h-5 w-12 bg-ink-700 rounded-full" />
        <div className="h-5 w-20 bg-ink-700 rounded-full" />
      </div>
    </div>
  )
}

function QuestionCard({ q, rank, maxFreq }: { q: Question; rank: number; maxFreq: number }) {
  const [expanded, setExpanded] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const [confirmCount, setConfirmCount] = useState(q.user_confirmed_count || 0)

  const pct = Math.round((q.frequency_count / maxFreq) * 100)
  const typeClass = TYPE_COLORS[q.question_type] ?? TYPE_COLORS.other
  const trend = q.trend_direction ? TREND_ICON[q.trend_direction] : ''

  const handleView = () => {
    setExpanded(v => {
      if (!v) {
        // Track view (fire-and-forget)
        fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/search/questions/${q.id}/view`, {
          method: 'POST',
        }).catch(() => {})
      }
      return !v
    })
  }

  const handleConfirm = async () => {
    if (confirmed) return
    setConfirmed(true)
    setConfirmCount(c => c + 1)
    await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/questions/${q.id}/confirm-appeared`, {
      method: 'POST',
    }).catch(() => {})
  }

  const handleShare = () => {
    const text = `Check this question from ${q.subject || 'AKTU'} — ${q.seen_in_label}:\n"${q.question_text.slice(0, 120)}..."\n\nFind more at https://aktu-pyq.vercel.app`
    const url = `https://wa.me/?text=${encodeURIComponent(text)}`
    window.open(url, '_blank')
  }

  return (
    <div className="glass rounded-xl p-5 hover:bg-white/[0.04] transition-all duration-200">
      {/* Header row */}
      <div className="flex items-start gap-3 mb-3">
        <span className="flex-shrink-0 w-6 h-6 rounded-full glass flex items-center justify-center text-xs text-ink-400 font-mono mt-0.5">
          {rank}
        </span>

        <p
          className="text-ink-100 text-sm leading-relaxed flex-1 font-medium cursor-pointer"
          onClick={handleView}
        >
          {q.question_text}
        </p>

        {/* Seen in N exams pill — replaces plain frequency_count display */}
        <div
          className={`flex-shrink-0 flex flex-col items-center glass px-3 py-1.5 rounded-lg border ${
            q.frequency_count >= 5 ? 'border-gold-500/30' : 'border-ink-600'
          }`}
        >
          <span className={`font-display font-bold text-lg leading-none ${q.frequency_count >= 5 ? 'text-gold-400' : 'text-ink-300'}`}>
            ×{q.frequency_count}
          </span>
          <span className="text-ink-500 text-[10px] leading-none mt-0.5 whitespace-nowrap">exams</span>
        </div>
      </div>

      {/* Frequency bar */}
      <div className="h-1 bg-ink-800 rounded-full mb-3 ml-9">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            pct >= 80
              ? 'bg-gradient-to-r from-gold-500/80 to-gold-400/60'
              : 'bg-gradient-to-r from-gold-500/40 to-gold-400/25'
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Tags row */}
      <div className="flex flex-wrap items-center gap-2 ml-9 mb-3">
        <span className={`tag-pill border ${typeClass} capitalize`}>{q.question_type}</span>

        {/* Seen in label — primary trust signal */}
        <span className="tag-pill border border-gold-500/20 text-gold-400/80 font-medium">
          {q.seen_in_label}
          {trend ? ` ${trend}` : ''}
        </span>

        {q.unit && (
          <span className="tag-pill border-jade-500/20 text-jade-400/80">
            Unit {q.unit}{q.unit_topic ? ` · ${q.unit_topic}` : ''}
          </span>
        )}

        {q.marks_weightage && <span className="tag-pill">{q.marks_weightage}M</span>}

        {q.has_math && <span className="tag-pill border-gold-500/15 text-gold-400/60">Math</span>}
        {q.has_diagram && <span className="tag-pill border-rose-500/15 text-rose-400/70 flex items-center gap-1"><Image size={9} />Diagram</span>}

        {q.must_revise_flag && (
          <span className="inline-flex items-center gap-1 tag-pill border-gold-500/30 text-gold-400">
            <Star size={9} fill="currentColor" /> Must revise
          </span>
        )}

        {q.concept_tags?.slice(0, 2).map(tag => (
          <span key={tag} className="tag-pill">{tag}</span>
        ))}

        {/* Student-confirmed count */}
        {confirmCount > 0 && (
          <span className="tag-pill border-jade-500/15 text-jade-400/70">
            {confirmCount} confirmed ✓
          </span>
        )}
      </div>

      {/* Expanded: sub-parts + diagram + actions */}
      {expanded && (
        <div className="ml-9 mt-2 space-y-3">
          {q.sub_parts && q.sub_parts.length > 0 && (
            <div className="glass rounded-lg p-3 space-y-1.5">
              {q.sub_parts.map((sp, i) => (
                <p key={i} className="text-ink-300 text-xs leading-relaxed">{sp}</p>
              ))}
            </div>
          )}

          {q.diagram_url && (
            <div className="glass rounded-lg p-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={q.diagram_url}
                alt="Diagram from question paper"
                className="max-w-full rounded-md opacity-90 hover:opacity-100 transition-opacity"
                style={{ maxHeight: 300 }}
              />
              <p className="text-ink-600 text-xs mt-1 text-center">Diagram from original paper</p>
            </div>
          )}

          {q.exam_sessions && q.exam_sessions.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {q.exam_sessions.map(s => (
                <span key={s} className="tag-pill text-[10px]">{s}</span>
              ))}
            </div>
          )}

          {/* Action row */}
          <div className="flex items-center gap-2 flex-wrap pt-1">
            <button
              onClick={handleConfirm}
              disabled={confirmed}
              className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-all ${
                confirmed
                  ? 'border-jade-500/30 text-jade-400 bg-jade-500/10'
                  : 'border-ink-600 text-ink-400 hover:border-jade-500/30 hover:text-jade-400 glass'
              } disabled:cursor-default`}
            >
              <ThumbsUp size={11} />
              {confirmed ? 'Confirmed — thanks!' : 'This appeared in my exam'}
            </button>

            <button
              onClick={handleShare}
              className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-ink-600 text-ink-400 hover:border-jade-500/30 hover:text-jade-400 glass transition-all"
            >
              <Share2 size={11} /> Share on WhatsApp
            </button>

            {q.subject && q.unit && (
              <a
                href={`/?mode=form&subject=${encodeURIComponent(q.subject)}&unit=${q.unit}`}
                className="text-xs text-gold-400/60 hover:text-gold-400 transition-colors ml-auto"
              >
                More from Unit {q.unit} →
              </a>
            )}
          </div>
        </div>
      )}

      {/* Expand toggle */}
      <button
        onClick={handleView}
        className="flex items-center gap-1 text-ink-600 hover:text-ink-400 text-xs mt-2 ml-9 transition-colors"
      >
        {expanded ? <><ChevronUp size={12} /> Less</> : <><ChevronDown size={12} /> Details &amp; actions</>}
      </button>
    </div>
  )
}

export default function ResultsList({ results, loading }: { results: Question[]; loading: boolean }) {
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
        <p className="text-ink-600 text-xs mt-1 mb-5">
          Try broadening your search, selecting &quot;All Units&quot;, or changing the subject.
        </p>
        <p className="text-ink-500 text-xs mb-2">
          We may not have papers for this subject yet. Sorry about that.
        </p>
        <div className="flex gap-2 justify-center mt-3">
          <a href="/contribute" className="btn-primary text-sm">
            Upload a paper →
          </a>
          <a href="/papers" className="btn-ghost text-sm">
            Browse what&apos;s indexed
          </a>
        </div>
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
        <span className="text-xs text-ink-500">Ranked by importance · click any question for details</span>
      </div>

      <div className="space-y-3">
        {results.map((q, i) => (
          <QuestionCard key={q.id} q={q} rank={i + 1} maxFreq={maxFreq} />
        ))}
      </div>
    </div>
  )
}
