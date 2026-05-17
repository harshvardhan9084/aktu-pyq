'use client'
import { useState, useRef, useEffect } from 'react'
import { Search, SlidersHorizontal, Zap, BookOpen } from 'lucide-react'
import Navbar from '@/components/Navbar'
import NaturalSearch from '@/components/NaturalSearch'
import DynamicForm from '@/components/DynamicForm'
import ResultsList from '@/components/ResultsList'
import WakeBanner, { useBackendWake } from '@/components/WakeBanner'
import type { Question } from '@/lib/supabase'
import { startResultsTimer, stopResultsTimer } from '@/lib/analytics'

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || ''

export default function Home() {
  const [mode, setMode] = useState<'nl' | 'form'>('nl')
  const [results, setResults] = useState<Question[]>([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const [totalQuestions, setTotalQuestions] = useState<number | null>(null)
  const resultsRef = useRef<HTMLDivElement>(null)

  const {
    showBanner,
    bannerElapsed,
    totalWait,
    startSearchTimer,
    stopSearchTimer,
  } = useBackendWake(BACKEND)

  // Fetch real question count
  useEffect(() => {
    fetch(`${BACKEND}/search/stats/public`)
      .then(r => r.json())
      .then(d => setTotalQuestions(d.total_questions ?? null))
      .catch(() => {})
  }, [])

  const handleLoading = (v: boolean) => {
    setLoading(v)
    if (v) {
      startSearchTimer()
      startResultsTimer()
    }
  }

  const handleResults = (data: Question[]) => {
    setResults(data)
    setSearched(true)
    setLoading(false)
    stopSearchTimer()
    stopResultsTimer(data.length)
    setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100)
  }

  return (
    <main className="min-h-screen">
      <Navbar />

      <section className="pt-28 pb-16 px-4 md:px-6 max-w-4xl mx-auto text-center">
        {/* Badge */}
        <div
          className="inline-flex items-center gap-2 glass px-3 py-1.5 rounded-full text-xs mb-6 animate-fade-in"
          style={{ color: 'var(--gold-500)' }}
        >
          <Zap size={11} />
          <span>AKTU previous-year question papers — analysed &amp; ranked</span>
        </div>

        {/* Hero — student-outcome language, not tech language */}
        <h1
          className="font-display text-4xl md:text-6xl font-black leading-[1.05] mb-4 animate-fade-up"
          style={{ color: 'var(--text-primary)' }}
        >
          Study smarter,<br />
          <span className="gold-text">not harder</span>
        </h1>

        <p
          className="text-base md:text-lg max-w-xl mx-auto leading-relaxed mb-5 animate-fade-up"
          style={{ animationDelay: '0.1s', opacity: 0, color: 'var(--text-muted)' }}
        >
          Every AKTU exam question — clustered, ranked by how many times it has appeared.
          You see which questions you <em>must</em> prepare, and which ones you can skip.
        </p>

        {/* Value micro-copy — three outcomes */}
        <div
          className="flex flex-wrap justify-center gap-4 mb-10 animate-fade-up"
          style={{ animationDelay: '0.15s', opacity: 0 }}
        >
          {[
            { emoji: '🔁', text: 'See questions repeated across years' },
            { emoji: '📌', text: 'Know which units get asked most' },
            { emoji: '⏱', text: 'Prioritise in 10 seconds, not 10 hours' },
          ].map(({ emoji, text }) => (
            <div key={text} className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-faint)' }}>
              <span>{emoji}</span>
              <span>{text}</span>
            </div>
          ))}
        </div>

        {/* Live question count — real data only */}
        <div
          className="flex items-center justify-center gap-2 mb-12 animate-fade-up"
          style={{ animationDelay: '0.2s', opacity: 0 }}
        >
          <BookOpen size={14} style={{ color: 'var(--gold-500)' }} />
          {totalQuestions !== null ? (
            <span
              className="font-display font-bold text-lg"
              style={{ color: 'var(--gold-500)' }}
            >
              {totalQuestions.toLocaleString()}
            </span>
          ) : (
            <span className="w-20 h-5 rounded animate-pulse inline-block" style={{ background: 'var(--bg-secondary)' }} />
          )}
          <span className="text-sm" style={{ color: 'var(--text-faint)' }}>questions indexed</span>
        </div>

        {/* Search mode toggle */}
        <div
          id="search"
          className="glass-strong rounded-2xl p-1 inline-flex gap-1 mb-6 animate-fade-up"
          style={{ animationDelay: '0.25s', opacity: 0 }}
        >
          <button
            onClick={() => setMode('nl')}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${mode === 'nl' ? 'btn-primary !px-5 !py-2.5' : ''}`}
            style={mode !== 'nl' ? { color: 'var(--text-dim)' } : {}}
          >
            <Search size={14} /> Natural language
          </button>
          <button
            onClick={() => setMode('form')}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${mode === 'form' ? 'btn-primary !px-5 !py-2.5' : ''}`}
            style={mode !== 'form' ? { color: 'var(--text-dim)' } : {}}
          >
            <SlidersHorizontal size={14} /> Step-by-step filters
          </button>
        </div>

        <div className="animate-fade-up" style={{ animationDelay: '0.3s', opacity: 0 }}>
          {mode === 'nl'
            ? <NaturalSearch onResults={handleResults} onLoading={handleLoading} />
            : <DynamicForm onResults={handleResults} onLoading={handleLoading} />}
        </div>
      </section>

      <div ref={resultsRef}>
        {(searched || loading) && (
          <section className="max-w-4xl mx-auto px-4 md:px-6 pb-20">
            <ResultsList results={results} loading={loading} />
          </section>
        )}
      </div>

      {/* Wake banner — shown only when backend sleeping + user searched */}
      <WakeBanner
        active={showBanner}
        elapsed={bannerElapsed}
        totalWait={totalWait}
        onDismiss={stopSearchTimer}
      />

      <footer
        className="border-t py-8 px-4 text-center text-xs"
        style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-ghost)' }}
      >
        <p>
          Built for AKTU students ·{' '}
          <a href="/contribute" className="transition-colors hover:underline" style={{ color: 'var(--gold-500)' }}>Contribute a paper</a>
          {' · '}
          <a href="/papers" className="transition-colors hover:underline" style={{ color: 'var(--gold-500)' }}>Browse papers</a>
          {' · '}
          <a href="/contribute#donate" className="transition-colors hover:underline" style={{ color: 'var(--gold-500)' }}>Support the project</a>
        </p>
        <p className="mt-1" style={{ color: 'var(--text-ghost)' }}>Not affiliated with AKTU. For educational use only.</p>
      </footer>
    </main>
  )
}
