'use client'
import { useState, useEffect } from 'react'
import { BookOpen, Search, Filter, X } from 'lucide-react'
import Navbar from '@/components/Navbar'
import type { PDFSubmission } from '@/lib/supabase'

const PROGRAMMES = ['All', 'B.Tech', 'M.Tech', 'Diploma', 'MCA', 'MBA']
const SEMESTERS = ['All', '1', '2', '3', '4', '5', '6', '7', '8']

export default function PapersPage() {
  const [papers, setPapers] = useState<PDFSubmission[]>([])
  const [loading, setLoading] = useState(true)
  const [totalQ, setTotalQ] = useState(0)

  const [programme, setProgramme] = useState('All')
  const [semester, setSemester] = useState('All')
  const [search, setSearch] = useState('')

  useEffect(() => {
    loadPapers()
  }, [programme, semester])

  const loadPapers = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (programme !== 'All') params.set('programme', programme)
      if (semester !== 'All') params.set('semester', semester)
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_BACKEND_URL}/search/papers?${params.toString()}`
      )
      const data = await res.json()
      setPapers(data.papers ?? [])
      setTotalQ(data.papers?.reduce((a: number, p: PDFSubmission) => a + (p.question_count ?? 0), 0) ?? 0)
    } catch {
      setPapers([])
    } finally {
      setLoading(false)
    }
  }

  const filtered = papers.filter(p =>
    !search ||
    p.subject?.toLowerCase().includes(search.toLowerCase()) ||
    p.branch?.toLowerCase().includes(search.toLowerCase()) ||
    p.subject_code?.toLowerCase().includes(search.toLowerCase())
  )

  const sessionLabel = (p: PDFSubmission) => {
    if (!p.exam_session) return ''
    return p.exam_session === 'odd' ? 'Odd Sem' : 'Even Sem'
  }

  return (
    <main className="min-h-screen">
      <Navbar />
      <div className="max-w-5xl mx-auto px-4 pt-28 pb-20">
        <div className="mb-8">
          <h1 className="font-display text-3xl md:text-4xl font-black text-ink-50 mb-2">
            Paper <span className="gold-text">Browser</span>
          </h1>
          <div className="flex items-center gap-4 text-ink-400 text-sm">
            <span className="flex items-center gap-1.5">
              <BookOpen size={13} className="text-gold-400" />
              <span className="text-gold-400 font-semibold">{papers.length}</span> papers indexed
            </span>
            <span>·</span>
            <span>
              <span className="text-gold-400 font-semibold">{totalQ.toLocaleString()}</span> questions
            </span>
          </div>
        </div>

        {/* Filters */}
        <div className="glass-strong rounded-2xl p-4 mb-6">
          <div className="flex flex-wrap gap-3 items-center">
            {/* Search */}
            <div className="relative flex-1 min-w-48">
              <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400 pointer-events-none" />
              <input
                type="text"
                placeholder="Search subject or code..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="input-field !pl-8 !py-2 text-xs"
              />
              {search && (
                <button onClick={() => setSearch('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-500 hover:text-ink-300">
                  <X size={12} />
                </button>
              )}
            </div>

            {/* Programme */}
            <div className="flex items-center gap-1.5">
              <Filter size={12} className="text-ink-500" />
              <div className="flex gap-1">
                {PROGRAMMES.map(p => (
                  <button
                    key={p}
                    onClick={() => setProgramme(p)}
                    className={`text-xs px-2.5 py-1.5 rounded-lg border transition-all ${
                      programme === p
                        ? 'bg-gold-500 text-ink-900 border-gold-500 font-medium'
                        : 'border-ink-600 text-ink-400 hover:border-gold-500/40 hover:text-gold-400 glass'
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>

            {/* Semester */}
            <div className="flex gap-1 flex-wrap">
              {SEMESTERS.map(s => (
                <button
                  key={s}
                  onClick={() => setSemester(s)}
                  className={`text-xs px-2 py-1.5 rounded-lg border transition-all ${
                    semester === s
                      ? 'bg-jade-500/80 text-ink-900 border-jade-500 font-medium'
                      : 'border-ink-600 text-ink-400 hover:border-jade-500/40 hover:text-jade-400 glass'
                  }`}
                >
                  {s === 'All' ? 'All Sem' : `Sem ${s}`}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Paper grid */}
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {Array.from({ length: 9 }).map((_, i) => (
              <div key={i} className="glass rounded-xl p-4 animate-pulse">
                <div className="h-4 bg-ink-700 rounded w-3/4 mb-3" />
                <div className="h-3 bg-ink-800 rounded w-1/2 mb-2" />
                <div className="h-3 bg-ink-800 rounded w-1/3" />
              </div>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="glass rounded-2xl p-12 text-center">
            <BookOpen size={32} className="text-ink-600 mx-auto mb-3" />
            <p className="text-ink-400 text-sm">No papers found for that filter.</p>
            <p className="text-ink-600 text-xs mt-1">Try broadening your search or changing the semester.</p>
            <a href="/contribute" className="btn-primary inline-block mt-5 text-sm">
              Contribute a paper →
            </a>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {filtered.map(paper => (
              <div key={paper.id} className="glass rounded-xl p-4 hover:bg-white/[0.05] transition-all duration-200 flex flex-col gap-2">
                <div>
                  <h3 className="text-ink-100 text-sm font-semibold leading-snug mb-1">
                    {paper.subject || 'Unknown Subject'}
                  </h3>
                  {paper.subject_code && (
                    <span className="tag-pill text-xs">{paper.subject_code}</span>
                  )}
                </div>
                <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-500 mt-1">
                  {paper.branch && <span>{paper.branch}</span>}
                  {paper.programme && <span>{paper.programme}</span>}
                  {paper.semester && <span>Sem {paper.semester}</span>}
                  {paper.year && (
                    <span className="text-gold-500/70">
                      {paper.year}–{String(paper.year + 1).slice(2)}{paper.exam_session ? ` · ${sessionLabel(paper)}` : ''}
                    </span>
                  )}
                </div>
                {(paper.question_count ?? 0) > 0 && (
                  <p className="text-jade-400 text-xs font-medium mt-auto">
                    {paper.question_count} questions indexed
                  </p>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Don't see your paper CTA */}
        <div className="mt-12 glass-strong rounded-2xl p-6 text-center">
          <p className="text-ink-300 text-sm font-medium mb-1">Don't see your paper?</p>
          <p className="text-ink-500 text-xs mb-4">
            Help us grow — upload your question paper and it'll be indexed for everyone.
          </p>
          <a href="/contribute" className="btn-primary inline-block">
            Contribute a paper →
          </a>
        </div>
      </div>
    </main>
  )
}
