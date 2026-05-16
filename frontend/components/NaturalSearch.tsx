'use client'
import { useState } from 'react'
import { Search, Sparkles } from 'lucide-react'
import type { Question } from '@/lib/supabase'

const SUGGESTIONS = [
  'Top 5 repeated theory questions of Electrical Unit 3',
  'Most asked numerical questions in Network Theory',
  'Questions repeated more than 4 times in DBMS',
  'Important Laplace Transform questions',
  'Unit 2 short questions of Engineering Maths',
  'Must revise questions in Data Structures',
  'Diagram questions in Digital Electronics Unit 4',
]

interface Props {
  onResults: (q: Question[]) => void
  onLoading: (v: boolean) => void
}

export default function NaturalSearch({ onResults, onLoading }: Props) {
  const [query, setQuery] = useState('')
  const [parsed, setParsed] = useState<Record<string, string> | null>(null)
  const [error, setError] = useState('')

  const handleSearch = async (q = query) => {
    if (!q.trim()) return
    setError('')
    onLoading(true)
    setParsed(null)

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/search/nl`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q }),
      })
      if (!res.ok) throw new Error('Search failed')
      const data = await res.json()
      setParsed(data.parsed_intent)
      onResults(data.results)

      // Track search (fire-and-forget)
      const sid = sessionStorage.getItem('sid') || ''
      fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/analytics/event`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_type: 'search',
          page: '/',
          metadata: { query: q, mode: 'nl', parsed: data.parsed_intent },
          session_id: sid,
        }),
      }).catch(() => {})
    } catch {
      setError('Could not reach the server. Make sure the backend is running.')
      onLoading(false)
    }
  }

  return (
    <div className="glass-strong rounded-2xl p-5 md:p-6 text-left">
      <div className="relative mb-4">
        <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-ink-400 pointer-events-none" />
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSearch()}
          placeholder="Describe what you're looking for..."
          className="input-field !pl-10 !pr-28"
        />
        <button
          onClick={() => handleSearch()}
          disabled={!query.trim()}
          className="absolute right-2 top-1/2 -translate-y-1/2 btn-primary !px-4 !py-1.5 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Search
        </button>
      </div>

      <div className="mb-4">
        <p className="text-ink-500 text-xs mb-2 flex items-center gap-1">
          <Sparkles size={11} /> Try these
        </p>
        <div className="flex flex-wrap gap-2">
          {SUGGESTIONS.map(s => (
            <button
              key={s}
              onClick={() => { setQuery(s); handleSearch(s) }}
              className="text-xs glass px-3 py-1.5 rounded-full text-ink-300 hover:text-gold-400 hover:border-gold-500/30 transition-all"
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {parsed && (
        <div className="glass rounded-xl px-4 py-3 text-xs text-ink-300">
          <span className="text-ink-500 mr-2">Understood as:</span>
          {Object.entries(parsed).map(([k, v]) => (
            <span key={k} className="mr-3">
              <span className="text-gold-500/70">{k}</span>
              <span className="text-ink-500 mx-1">→</span>
              <span className="text-ink-200">{String(v)}</span>
            </span>
          ))}
        </div>
      )}

      {error && <p className="text-rose-400 text-xs mt-2">{error}</p>}
    </div>
  )
}
