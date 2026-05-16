'use client'
import { useState, useRef, useEffect } from 'react'
import { Search, SlidersHorizontal, Zap, BookOpen } from 'lucide-react'
import Navbar from '@/components/Navbar'
import NaturalSearch from '@/components/NaturalSearch'
import DynamicForm from '@/components/DynamicForm'
import ResultsList from '@/components/ResultsList'
import type { Question } from '@/lib/supabase'

export default function Home() {
  const [mode, setMode] = useState<'nl' | 'form'>('nl')
  const [results, setResults] = useState<Question[]>([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const [totalQuestions, setTotalQuestions] = useState<number | null>(null)
  const resultsRef = useRef<HTMLDivElement>(null)

  // Wake Render backend + fetch real question count
  useEffect(() => {
    fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/health`).catch(() => {})
    fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/search/stats/public`)
      .then(r => r.json())
      .then(d => setTotalQuestions(d.total_questions ?? null))
      .catch(() => {})

    // Track page view (fire-and-forget)
    const sid = sessionStorage.getItem('sid') || Math.random().toString(36).slice(2)
    sessionStorage.setItem('sid', sid)
    fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/analytics/event`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ event_type: 'page_view', page: '/', session_id: sid }),
    }).catch(() => {})
  }, [])

  const handleResults = (data: Question[]) => {
    setResults(data)
    setSearched(true)
    setLoading(false)
    setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100)
  }

  return (
    <main className="min-h-screen">
      <Navbar />

      <section className="pt-28 pb-16 px-4 md:px-6 max-w-4xl mx-auto text-center">
        <div className="inline-flex items-center gap-2 glass px-3 py-1.5 rounded-full text-xs text-gold-400 mb-6 animate-fade-in">
          <Zap size={11} />
          <span>Semantic search over AKTU previous-year papers</span>
        </div>

        <h1 className="font-display text-4xl md:text-6xl font-black text-ink-50 leading-[1.05] mb-4 animate-fade-up">
          Find What Actually<br />
          <span className="gold-text">Gets Asked</span>
        </h1>

        <p
          className="text-ink-300 text-base md:text-lg max-w-xl mx-auto leading-relaxed mb-10 animate-fade-up"
          style={{ animationDelay: '0.1s', opacity: 0 }}
        >
          Stop scrolling through PDFs. We've processed every AKTU question paper,
          clustered repeated questions, and ranked them by frequency — so you study what matters.
        </p>

        {/* Live question count — only this one stat, real data */}
        <div
          className="flex items-center justify-center gap-2 mb-12 animate-fade-up"
          style={{ animationDelay: '0.2s', opacity: 0 }}
        >
          <BookOpen size={14} className="text-gold-400" />
          {totalQuestions !== null ? (
            <span className="font-display font-bold text-gold-400 text-lg">
              {totalQuestions.toLocaleString()}
            </span>
          ) : (
            <span className="w-20 h-5 bg-ink-700 rounded animate-pulse inline-block" />
          )}
          <span className="text-ink-400 text-sm">questions indexed</span>
        </div>

        {/* Search mode toggle */}
        <div
          id="search"
          className="glass-strong rounded-2xl p-1 inline-flex gap-1 mb-6 animate-fade-up"
          style={{ animationDelay: '0.25s', opacity: 0 }}
        >
          <button
            onClick={() => setMode('nl')}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${mode === 'nl' ? 'bg-gold-500 text-ink-900' : 'text-ink-300 hover:text-ink-100'}`}
          >
            <Search size={14} /> Natural language
          </button>
          <button
            onClick={() => setMode('form')}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${mode === 'form' ? 'bg-gold-500 text-ink-900' : 'text-ink-300 hover:text-ink-100'}`}
          >
            <SlidersHorizontal size={14} /> Step-by-step filters
          </button>
        </div>

        <div className="animate-fade-up" style={{ animationDelay: '0.3s', opacity: 0 }}>
          {mode === 'nl'
            ? <NaturalSearch onResults={handleResults} onLoading={setLoading} />
            : <DynamicForm onResults={handleResults} onLoading={setLoading} />}
        </div>
      </section>

      <div ref={resultsRef}>
        {(searched || loading) && (
          <section className="max-w-4xl mx-auto px-4 md:px-6 pb-20">
            <ResultsList results={results} loading={loading} />
          </section>
        )}
      </div>

      <footer className="border-t border-white/5 py-8 px-4 text-center text-ink-500 text-xs">
        <p>
          Built for AKTU students ·{' '}
          <a href="/contribute" className="text-gold-500/70 hover:text-gold-400 transition-colors">Contribute a paper</a>
          {' · '}
          <a href="/papers" className="text-gold-500/70 hover:text-gold-400 transition-colors">Browse papers</a>
          {' · '}
          <a href="/contribute#donate" className="text-gold-500/70 hover:text-gold-400 transition-colors">Support the project</a>
        </p>
        <p className="mt-1 text-ink-600">Not affiliated with AKTU. For educational use only.</p>
      </footer>
    </main>
  )
}
