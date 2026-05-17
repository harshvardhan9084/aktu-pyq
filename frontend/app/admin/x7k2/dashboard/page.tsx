'use client'
import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import {
  Upload, CheckCircle, XCircle, Clock, Database,
  AlertTriangle, RefreshCw, FileText, Link2,
  Activity, Settings, Users, BookOpen, LogOut,
  BarChart2, TrendingUp, Eye, Share2, Search,
  Monitor, Smartphone, Tablet
} from 'lucide-react'

/* ─── Types ─────────────────────────────────────────────────────────────────── */
type TabId = 'overview' | 'submissions' | 'upload' | 'bulkimport' | 'database' | 'analytics' | 'logs'

type Submission = {
  id: number; filename: string; subject: string | null; subject_code: string | null
  branch: string | null; semester: number | null; year: number | null
  exam_session: string | null; submitted_by: string
  status: 'pending' | 'approved' | 'rejected'; created_at: string
}

type SystemStats = {
  total_questions: number; total_clusters: number; total_subjects: number
  total_pdfs_processed: number; approved_papers: number; pending_submissions: number
  scrape_pending: number; scrape_done: number; scrape_failed: number
  ocr_errors_today: number; last_processed: string
  site_counters: Record<string, number>
}

type AnalyticsSummary = {
  counters: Record<string, number>
  monthly_visitors: Record<string, number>
  device_breakdown: Record<string, number>
  top_pages: [string, number][]
  top_search_queries: { query: string; count: number }[]
  avg_scroll_depth_pct: number
  avg_time_on_page_sec: number
  total_shares: number
}

type ScrapeItem = {
  id: number; pdf_url: string; status: string; error_message: string | null
  subject: string | null; questions_extracted: number
  created_at: string; processed_at: string | null
}

/* ─── Mini components ────────────────────────────────────────────────────────── */
function StatCard({ icon: Icon, label, value, color, sub }: {
  icon: any; label: string; value: string | number; color: string; sub?: string
}) {
  return (
    <div className="glass rounded-xl p-4">
      <Icon size={16} className={`${color} mb-2`} />
      <div className={`font-display font-bold text-2xl ${color}`}>{value}</div>
      <div className="text-xs mt-0.5" style={{ color: 'var(--text-faint)' }}>{label}</div>
      {sub && <div className="text-xs mt-1" style={{ color: 'var(--text-ghost)' }}>{sub}</div>}
    </div>
  )
}

function BarRow({ label, value, max, color = 'var(--gold-500)' }: {
  label: string; value: number; max: number; color?: string
}) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs font-mono w-32 shrink-0 truncate" style={{ color: 'var(--text-dim)' }}>{label}</span>
      <div className="flex-1 h-1.5 rounded-full" style={{ background: 'var(--bg-secondary)' }}>
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="text-xs w-8 text-right shrink-0" style={{ color: 'var(--text-muted)' }}>{value}</span>
    </div>
  )
}

function Skeleton() {
  return <div className="glass rounded-xl p-4 animate-pulse">
    <div className="h-4 w-4 rounded mb-2" style={{ background: 'var(--bg-secondary)' }} />
    <div className="h-8 w-16 rounded mb-1" style={{ background: 'var(--bg-secondary)' }} />
    <div className="h-3 w-20 rounded" style={{ background: 'var(--text-ghost)' }} />
  </div>
}

/* ─── Main dashboard ─────────────────────────────────────────────────────────── */
export default function AdminDashboard() {
  const router = useRouter()
  const [tab, setTab] = useState<TabId>('overview')
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [stats, setStats] = useState<SystemStats | null>(null)
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null)
  const [logs, setLogs] = useState<string[]>([])
  const [verified, setVerified] = useState(false)
  const [actionMsg, setActionMsg] = useState<{ type: 'ok' | 'err'; text: string } | null>(null)

  // Upload tab state
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadMeta, setUploadMeta] = useState({
    subject: '', branch: '', programme: '', semester: '', year: '',
    university: 'AKTU', exam_session: '', subject_code: '',
  })
  const [metaAutoFilled, setMetaAutoFilled] = useState(false)
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'done' | 'error' | 'duplicate'>('idle')
  const [uploadMsg, setUploadMsg] = useState('')

  // Bulk import state
  const [bulkLines, setBulkLines] = useState('')
  const [bulkResult, setBulkResult] = useState<{ queued: number; not_found: number; already_queued: number } | null>(null)
  const [scrapeItems, setScrapeItems] = useState<ScrapeItem[]>([])
  const [scrapeRunning, setScrapeRunning] = useState(false)

  const getToken = useCallback(() => sessionStorage.getItem('admin_token') || '', [])
  const authH = useCallback((t: string) => ({ 'X-Admin-Token': t }), [])
  const B = process.env.NEXT_PUBLIC_BACKEND_URL || ''

  // Auth check
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch('/api/admin/verify')
        if (!res.ok || cancelled) { router.push('/admin/x7k2'); return }
        setVerified(true)
        const t = getToken()
        await Promise.all([loadSubmissions(t), loadStats(t)])
      } catch { router.push('/admin/x7k2') }
    })()
    return () => { cancelled = true }
  }, []) // eslint-disable-line

  const loadSubmissions = async (t?: string) => {
    const tok = t ?? getToken()
    try {
      const r = await fetch(`${B}/admin/submissions`, { headers: authH(tok) })
      if (r.ok) setSubmissions(await r.json())
    } catch {}
  }

  const loadStats = async (t?: string) => {
    const tok = t ?? getToken()
    try {
      const r = await fetch(`${B}/admin/stats`, { headers: authH(tok) })
      if (r.ok) setStats(await r.json())
    } catch {}
  }

  const loadAnalytics = async () => {
    try {
      const r = await fetch(`${B}/admin/analytics/summary`, { headers: authH(getToken()) })
      if (r.ok) setAnalytics(await r.json())
    } catch {}
  }

  const loadScrapeStatus = async () => {
    try {
      const r = await fetch(`${B}/admin/scrape/status`, { headers: authH(getToken()) })
      if (r.ok) { const d = await r.json(); setScrapeItems(d.recent ?? []) }
    } catch {}
  }

  const fetchLogs = async () => {
    try {
      const r = await fetch(`${B}/admin/logs`, { headers: authH(getToken()) })
      if (r.ok) { const d = await r.json(); setLogs(d.logs ?? []) }
    } catch {}
  }

  // Auto-extract metadata on file select
  const handleFileSelect = async (f: File) => {
    setUploadFile(f); setUploadStatus('idle'); setUploadMsg(''); setMetaAutoFilled(false)
    const fd = new FormData(); fd.append('file', f)
    try {
      const r = await fetch(`${B}/admin/metadata/extract`, { method: 'POST', headers: authH(getToken()), body: fd })
      if (r.ok) {
        const d = await r.json()
        setUploadMeta(prev => ({
          ...prev,
          subject: d.subject_name || prev.subject,
          branch: d.branch || prev.branch,
          semester: d.semester ? String(d.semester) : prev.semester,
          year: d.year ? String(d.year) : prev.year,
          exam_session: d.exam_session || prev.exam_session,
          subject_code: d.subject_code || prev.subject_code,
        }))
        setMetaAutoFilled(true)
      }
    } catch {}
  }

  const handleAdminUpload = async () => {
    if (!uploadFile) return
    setUploadStatus('uploading'); setUploadMsg('')
    const fd = new FormData(); fd.append('file', uploadFile)
    Object.entries(uploadMeta).forEach(([k, v]) => fd.append(k, v))
    try {
      const r = await fetch(`${B}/admin/upload`, { method: 'POST', headers: authH(getToken()), body: fd })
      const d = await r.json()
      if (r.status === 409) { setUploadStatus('duplicate'); setUploadMsg('Already processed.') }
      else if (!r.ok) { setUploadStatus('error'); setUploadMsg(d.detail || 'Upload failed.') }
      else {
        setUploadStatus('done')
        setUploadMsg(`${d.new_questions} new · ${d.updated_questions} updated · ${d.clusters_formed} clusters`)
        await loadStats()
      }
    } catch { setUploadStatus('error'); setUploadMsg('Could not reach backend.') }
  }

  const handleApprove = async (id: number) => {
    try {
      const r = await fetch(`${B}/admin/submissions/${id}/approve`, { method: 'POST', headers: authH(getToken()) })
      const d = await r.json()
      if (!r.ok) { setActionMsg({ type: 'err', text: d.detail || 'Approval failed.' }); return }
      setActionMsg({ type: 'ok', text: `Submission ${id} approved and processed.` })
      await Promise.all([loadSubmissions(), loadStats()])
    } catch { setActionMsg({ type: 'err', text: 'Could not reach backend.' }) }
  }

  const handleReject = async (id: number) => {
    const reason = prompt('Rejection reason (optional):') || ''
    try {
      const fd = new FormData(); fd.append('reason', reason)
      await fetch(`${B}/admin/submissions/${id}/reject`, { method: 'POST', headers: authH(getToken()), body: fd })
      setActionMsg({ type: 'ok', text: `Submission ${id} rejected.` })
      await loadSubmissions()
    } catch {}
  }

  const handleBulkFeed = async () => {
    const lines = bulkLines.trim().split('\n').filter(Boolean)
    if (!lines.length) return
    setBulkResult(null)
    try {
      const r = await fetch(`${B}/admin/scrape/feed`, {
        method: 'POST',
        headers: { ...authH(getToken()), 'Content-Type': 'application/json' },
        body: JSON.stringify({ lines }),
      })
      if (r.ok) setBulkResult(await r.json())
    } catch {}
    loadScrapeStatus()
  }

  const handleRunScraper = async () => {
    setScrapeRunning(true)
    try {
      await fetch(`${B}/admin/scrape/run`, { method: 'POST', headers: authH(getToken()) })
    } catch {}
    setScrapeRunning(false)
    loadScrapeStatus(); loadStats()
  }

  const handleDbAction = async (label: string, endpoint: string, method: 'POST' | 'DELETE' = 'POST', confirm_msg?: string) => {
    if (confirm_msg && !confirm(confirm_msg)) return
    setActionMsg(null)
    try {
      const r = await fetch(`${B}${endpoint}`, { method, headers: authH(getToken()) })
      const d = await r.json().catch(() => ({}))
      if (!r.ok) { setActionMsg({ type: 'err', text: d.detail || `${label} failed.` }); return }
      setActionMsg({ type: 'ok', text: d.message || d.updated ? `${label}: ${d.updated ?? ''} records updated.` : `${label} completed.` })
      await Promise.all([loadStats(), loadSubmissions()])
    } catch { setActionMsg({ type: 'err', text: 'Could not reach backend.' }) }
  }

  const handleLogout = async () => {
    await fetch('/api/admin/logout', { method: 'POST' })
    sessionStorage.removeItem('admin_token')
    router.push('/admin/x7k2')
  }

  const TABS: { id: TabId; icon: any; label: string; badge?: number }[] = [
    { id: 'overview',    icon: Activity,  label: 'Overview' },
    { id: 'submissions', icon: Clock,     label: 'Submissions', badge: submissions.filter(s => s.status === 'pending').length },
    { id: 'upload',      icon: Upload,    label: 'Upload PDF' },
    { id: 'bulkimport',  icon: Link2,     label: 'Bulk Import' },
    { id: 'database',    icon: Database,  label: 'Database' },
    { id: 'analytics',   icon: BarChart2, label: 'Analytics' },
    { id: 'logs',        icon: FileText,  label: 'Logs' },
  ]

  if (!verified) return (
    <main className="min-h-screen flex items-center justify-center">
      <div className="text-sm animate-pulse" style={{ color: 'var(--text-faint)' }}>Verifying access…</div>
    </main>
  )

  return (
    <main className="min-h-screen" style={{ background: 'var(--bg-primary)' }}>
      {/* Header */}
      <div className="glass border-b px-4 md:px-6 h-14 flex items-center justify-between sticky top-0 z-50"
           style={{ borderColor: 'var(--border-subtle)' }}>
        <div className="flex items-center gap-2">
          <Settings size={15} style={{ color: 'var(--gold-500)' }} />
          <span className="font-display font-bold text-sm" style={{ color: 'var(--text-primary)' }}>Admin Panel</span>
          <span className="text-xs ml-2" style={{ color: 'var(--text-ghost)' }}>· AKTU PYQ v2</span>
        </div>
        <button onClick={handleLogout}
          className="flex items-center gap-1.5 text-xs transition-colors"
          style={{ color: 'var(--text-faint)' }}
          onMouseEnter={e => e.currentTarget.style.color = 'var(--rose-500)'}
          onMouseLeave={e => e.currentTarget.style.color = 'var(--text-faint)'}
        >
          <LogOut size={13} /> Logout
        </button>
      </div>

      <div className="max-w-6xl mx-auto px-4 md:px-6 py-6">
        {/* Tab bar */}
        <div className="flex gap-1 glass-strong rounded-xl p-1 mb-6 overflow-x-auto">
          {TABS.map(t => (
            <button key={t.id}
              onClick={() => {
                setTab(t.id); setActionMsg(null)
                if (t.id === 'logs') fetchLogs()
                if (t.id === 'bulkimport') loadScrapeStatus()
                if (t.id === 'analytics') loadAnalytics()
              }}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap flex-shrink-0 ${tab === t.id ? 'btn-primary !px-4 !py-2' : ''}`}
              style={tab !== t.id ? { color: 'var(--text-dim)' } : {}}
            >
              <t.icon size={14} />
              {t.label}
              {t.badge != null && t.badge > 0 && (
                <span className={`text-xs px-1.5 py-0.5 rounded-full font-bold ${tab === t.id ? 'bg-black/20' : 'bg-rose-500/80 text-white'}`}>
                  {t.badge}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Global action feedback */}
        {actionMsg && (
          <div className={`mb-4 glass rounded-xl px-4 py-3 text-sm flex items-center gap-2 ${actionMsg.type === 'ok' ? 'text-jade-400' : 'text-rose-400'}`}
               style={{ borderColor: actionMsg.type === 'ok' ? 'var(--jade-500)' : 'var(--rose-500)', border: '1px solid' }}>
            {actionMsg.type === 'ok' ? <CheckCircle size={15} /> : <XCircle size={15} />}
            {actionMsg.text}
            <button onClick={() => setActionMsg(null)} className="ml-auto text-xs opacity-50 hover:opacity-100">✕</button>
          </div>
        )}

        {/* ── OVERVIEW ─────────────────────────────────────────────────── */}
        {tab === 'overview' && (
          <div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
              {stats ? [
                { label: 'Total Questions', value: stats.total_questions.toLocaleString(), icon: BookOpen, color: 'text-gold-400' },
                { label: 'Clusters', value: stats.total_clusters.toLocaleString(), icon: Database, color: 'text-jade-400' },
                { label: 'Subjects', value: stats.total_subjects, icon: Users, color: 'text-gold-400' },
                { label: 'Papers Approved', value: stats.approved_papers, icon: FileText, color: 'text-jade-400' },
              ].map(s => <StatCard key={s.label} {...s} />)
              : Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} />)}
            </div>
            {stats && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="glass rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Clock size={14} style={{ color: 'var(--gold-500)' }} />
                    <span className="text-sm font-medium" style={{ color: 'var(--text-muted)' }}>Pending Reviews</span>
                  </div>
                  <span className="font-display font-bold text-3xl text-gold-400">{stats.pending_submissions}</span>
                  {stats.pending_submissions > 0 && (
                    <button onClick={() => setTab('submissions')} className="btn-primary !px-3 !py-1.5 text-xs mt-3 block">
                      Review now →
                    </button>
                  )}
                </div>
                <div className="glass rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Link2 size={14} style={{ color: 'var(--jade-500)' }} />
                    <span className="text-sm font-medium" style={{ color: 'var(--text-muted)' }}>Scrape Queue</span>
                  </div>
                  <div className="flex gap-3 text-sm">
                    <span className="text-gold-400 font-bold">{stats.scrape_pending}</span><span style={{ color: 'var(--text-ghost)' }}>pending</span>
                    <span className="text-jade-400 font-bold">{stats.scrape_done}</span><span style={{ color: 'var(--text-ghost)' }}>done</span>
                    <span className="text-rose-400 font-bold">{stats.scrape_failed}</span><span style={{ color: 'var(--text-ghost)' }}>failed</span>
                  </div>
                  {stats.scrape_pending > 0 && (
                    <button onClick={() => setTab('bulkimport')} className="btn-ghost !px-3 !py-1.5 text-xs mt-3 block">
                      Run batch →
                    </button>
                  )}
                </div>
                <div className="glass rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <AlertTriangle size={14} style={{ color: stats.ocr_errors_today > 0 ? 'var(--rose-500)' : 'var(--jade-500)' }} />
                    <span className="text-sm font-medium" style={{ color: 'var(--text-muted)' }}>OCR Errors Today</span>
                  </div>
                  <span className={`font-display font-bold text-3xl ${stats.ocr_errors_today > 0 ? 'text-rose-400' : 'text-jade-400'}`}>
                    {stats.ocr_errors_today}
                  </span>
                  <p className="text-xs mt-1" style={{ color: 'var(--text-ghost)' }}>
                    Last sync: {stats.last_processed ? new Date(stats.last_processed).toLocaleTimeString() : 'Never'}
                  </p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── SUBMISSIONS ───────────────────────────────────────────────── */}
        {tab === 'submissions' && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-xl font-bold" style={{ color: 'var(--text-primary)' }}>Student Submissions</h2>
              <button onClick={() => loadSubmissions()} className="btn-ghost !px-3 !py-1.5 flex items-center gap-1.5 text-xs">
                <RefreshCw size={13} /> Refresh
              </button>
            </div>
            <p className="text-xs mb-4" style={{ color: 'var(--text-faint)' }}>
              Student PDFs go to scrape_queue automatically. This is the audit trail. Approve manually only if auto-processing failed.
            </p>
            <div className="space-y-3">
              {submissions.length === 0 ? (
                <div className="glass rounded-xl p-10 text-center text-sm" style={{ color: 'var(--text-faint)' }}>No submissions yet.</div>
              ) : submissions.map(sub => (
                <div key={sub.id} className="glass rounded-xl p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <FileText size={13} style={{ color: 'var(--text-faint)' }} className="shrink-0" />
                        <span className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>{sub.filename}</span>
                        <span className={`shrink-0 text-xs px-2 py-0.5 rounded-full font-medium ${sub.status === 'pending' ? 'bg-gold-500/15 text-gold-400' : sub.status === 'approved' ? 'bg-jade-500/15 text-jade-400' : 'bg-rose-500/15 text-rose-400'}`}>
                          {sub.status}
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs pl-5" style={{ color: 'var(--text-ghost)' }}>
                        {sub.subject && <span>{sub.subject}</span>}
                        {sub.subject_code && <span>{sub.subject_code}</span>}
                        {sub.year && <span>{sub.year}{sub.exam_session ? ` · ${sub.exam_session}` : ''}</span>}
                        {sub.semester && <span>Sem {sub.semester}</span>}
                        <span>{new Date(sub.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                    {sub.status === 'pending' && (
                      <div className="flex gap-2 shrink-0">
                        <button onClick={() => handleApprove(sub.id)} className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-jade-500/15 text-jade-400 border border-jade-500/20 hover:bg-jade-500/25 transition-all">
                          <CheckCircle size={13} /> Approve
                        </button>
                        <button onClick={() => handleReject(sub.id)} className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-rose-500/15 text-rose-400 border border-rose-500/20 hover:bg-rose-500/25 transition-all">
                          <XCircle size={13} /> Reject
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── UPLOAD PDF ─────────────────────────────────────────────────── */}
        {tab === 'upload' && (
          <div className="max-w-xl">
            <h2 className="font-display text-xl font-bold mb-1" style={{ color: 'var(--text-primary)' }}>Direct PDF Upload</h2>
            <p className="text-sm mb-5" style={{ color: 'var(--text-faint)' }}>Straight into the processing pipeline. Metadata auto-filled from paper header.</p>
            <div className="glass-strong rounded-2xl p-5 space-y-3">
              <label className={`block border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${uploadFile ? 'border-jade-500/50 bg-jade-500/5' : 'border-ink-600 hover:border-ink-400'}`}
                     style={{ borderColor: uploadFile ? 'var(--jade-500)' : 'var(--text-ghost)' }}>
                <input type="file" accept=".pdf" className="hidden"
                       onChange={e => { const f = e.target.files?.[0]; if (f) handleFileSelect(f) }} />
                {uploadFile ? (
                  <div className="flex items-center justify-center gap-2">
                    <FileText size={16} style={{ color: 'var(--jade-500)' }} />
                    <span className="text-sm" style={{ color: 'var(--jade-400)' }}>{uploadFile.name}</span>
                  </div>
                ) : (
                  <>
                    <Upload size={20} className="mx-auto mb-2" style={{ color: 'var(--text-ghost)' }} />
                    <p className="text-sm" style={{ color: 'var(--text-faint)' }}>Click to select PDF</p>
                  </>
                )}
              </label>
              {metaAutoFilled && (
                <p className="text-xs flex items-center gap-1 text-jade-400"><CheckCircle size={12} /> Metadata auto-detected — verify below</p>
              )}
              <div className="grid grid-cols-2 gap-3">
                {[
                  { key: 'subject',      label: 'Subject' },
                  { key: 'subject_code', label: 'Code (EE-301)' },
                  { key: 'branch',       label: 'Branch' },
                  { key: 'year',         label: 'Year (2022)' },
                  { key: 'semester',     label: 'Semester' },
                  { key: 'exam_session', label: 'Session (odd/even)' },
                ].map(({ key, label }) => (
                  <input key={key} placeholder={label} className="input-field text-xs"
                    value={(uploadMeta as any)[key]}
                    onChange={e => setUploadMeta({ ...uploadMeta, [key]: e.target.value })} />
                ))}
              </div>
              {uploadStatus === 'done'      && <div className="text-jade-400 text-sm flex gap-2 items-start"><CheckCircle size={15} className="shrink-0 mt-0.5" />{uploadMsg}</div>}
              {uploadStatus === 'duplicate' && <div className="text-gold-400 text-sm flex gap-2 items-start"><AlertTriangle size={15} className="shrink-0 mt-0.5" />{uploadMsg}</div>}
              {uploadStatus === 'error'     && <div className="text-rose-400 text-sm flex gap-2 items-start"><XCircle size={15} className="shrink-0 mt-0.5" />{uploadMsg}</div>}
              <button onClick={handleAdminUpload} disabled={!uploadFile || uploadStatus === 'uploading'}
                      className="btn-primary w-full disabled:opacity-40 disabled:cursor-not-allowed">
                {uploadStatus === 'uploading' ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="w-3.5 h-3.5 border-2 border-black/30 border-t-black rounded-full animate-spin" />
                    Processing…
                  </span>
                ) : 'Upload & Process'}
              </button>
            </div>
          </div>
        )}

        {/* ── BULK IMPORT ────────────────────────────────────────────────── */}
        {tab === 'bulkimport' && (
          <div className="max-w-3xl">
            <h2 className="font-display text-xl font-bold mb-1" style={{ color: 'var(--text-primary)' }}>Bulk Import — aktuonline.com</h2>
            <p className="text-sm mb-5" style={{ color: 'var(--text-faint)' }}>
              Paste partial PDF names (one per line). Auto-prepends base URL and appends .pdf.
              Direct download bypasses ad walls.
            </p>
            <div className="glass-strong rounded-2xl p-5 space-y-4 mb-6">
              <textarea className="input-field font-mono text-xs h-40 resize-none"
                placeholder={"btech-1-sem-electronics-engg-nec101-2022\nbtech-3-sem-electrical-engg-bee301-2022"}
                value={bulkLines} onChange={e => setBulkLines(e.target.value)} />
              <button onClick={handleBulkFeed} className="btn-primary">Validate &amp; Queue URLs</button>
              {bulkResult && (
                <div className="glass rounded-xl px-4 py-3 text-sm flex gap-4">
                  <span className="text-jade-400 font-semibold">{bulkResult.queued} queued</span>
                  <span className="text-rose-400">{bulkResult.not_found} not found</span>
                  <span className="text-gold-400">{bulkResult.already_queued} already queued</span>
                </div>
              )}
            </div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold" style={{ color: 'var(--text-muted)' }}>Scrape Queue</h3>
              <div className="flex gap-2">
                <button onClick={loadScrapeStatus} className="btn-ghost !px-3 !py-1.5 text-xs flex items-center gap-1"><RefreshCw size={12} /> Refresh</button>
                <button onClick={handleRunScraper} disabled={scrapeRunning} className="btn-primary !px-4 !py-1.5 text-xs disabled:opacity-50">
                  {scrapeRunning ? 'Running…' : 'Run Next Batch (10)'}
                </button>
              </div>
            </div>
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {scrapeItems.length === 0
                ? <div className="glass rounded-xl p-6 text-center text-sm" style={{ color: 'var(--text-faint)' }}>No items in queue.</div>
                : scrapeItems.map(item => (
                  <div key={item.id} className="glass rounded-lg px-4 py-3 flex items-center gap-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium shrink-0 ${
                      item.status === 'done' ? 'bg-jade-500/15 text-jade-400'
                      : item.status === 'failed' ? 'bg-rose-500/15 text-rose-400'
                      : item.status === 'processing' ? 'bg-gold-500/15 text-gold-400'
                      : 'text-ink-400'}`} style={item.status === 'pending' ? { background: 'var(--bg-secondary)' } : {}}>
                      {item.status}
                    </span>
                    <span className="text-xs truncate flex-1" style={{ color: 'var(--text-dim)' }}>
                      {item.pdf_url.replace('https://www.aktuonline.com/papers/', '').replace('internal://submissions/', '[student] ')}
                    </span>
                    {item.status === 'done' && <span className="text-jade-400 text-xs shrink-0">{item.questions_extracted}q</span>}
                    {item.status === 'failed' && <span className="text-rose-400/70 text-xs shrink-0 max-w-32 truncate" title={item.error_message || ''}>{item.error_message?.slice(0, 40)}</span>}
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* ── DATABASE ──────────────────────────────────────────────────── */}
        {tab === 'database' && (
          <div>
            <h2 className="font-display text-xl font-bold mb-5" style={{ color: 'var(--text-primary)' }}>Database Management</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[
                {
                  label: 'Recalculate importance scores',
                  desc: 'Updates frequency trend, importance score, and must_revise flag for every question based on year_appeared data.',
                  action: 'Recalculate', endpoint: '/admin/recalculate', method: 'POST' as const, danger: false,
                },
                {
                  label: 'Re-cluster all questions',
                  desc: 'Re-runs TF-IDF embedding + DBSCAN clustering on every question. Updates cluster_id. Run after bulk imports.',
                  action: 'Run Clustering', endpoint: '/admin/recluster', method: 'POST' as const, danger: false,
                },
                {
                  label: 'Rebuild search index',
                  desc: 'Resets the TF-IDF vectorizer. It re-fits on the next search or embed call. Run if search feels stale.',
                  action: 'Rebuild Index', endpoint: '/admin/rebuild-index', method: 'POST' as const, danger: false,
                },
                {
                  label: 'Export full database to JSON',
                  desc: 'Downloads all questions, submissions, clusters, and scrape queue as a JSON backup.',
                  action: 'Export', endpoint: '/admin/export', method: 'POST' as const, danger: false,
                },
                {
                  label: 'Clear all pending submissions',
                  desc: 'Permanently deletes all pdf_submissions rows with status=pending. Irreversible.',
                  action: 'Clear Queue', endpoint: '/admin/submissions/pending', method: 'DELETE' as const, danger: true,
                },
              ].map(item => (
                <div key={item.label} className="glass rounded-xl p-4">
                  <p className="text-sm font-medium mb-1" style={{ color: 'var(--text-secondary)' }}>{item.label}</p>
                  <p className="text-xs mb-3 leading-relaxed" style={{ color: 'var(--text-faint)' }}>{item.desc}</p>
                  <button
                    onClick={() => handleDbAction(
                      item.action, item.endpoint, item.method,
                      item.danger ? 'Are you sure? This cannot be undone.' : undefined,
                    )}
                    className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${
                      item.danger
                        ? 'border-rose-500/30 text-rose-400 hover:bg-rose-500/10'
                        : 'border-gold-500/30 text-gold-400 hover:bg-gold-500/10'
                    }`}
                  >{item.action}</button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── ANALYTICS ────────────────────────────────────────────────── */}
        {tab === 'analytics' && (
          <div>
            <div className="flex items-center justify-between mb-5">
              <h2 className="font-display text-xl font-bold" style={{ color: 'var(--text-primary)' }}>Analytics</h2>
              <button onClick={loadAnalytics} className="btn-ghost !px-3 !py-1.5 text-xs flex items-center gap-1">
                <RefreshCw size={12} /> Refresh
              </button>
            </div>
            {analytics ? (
              <div className="space-y-5">
                {/* Counter grid */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <StatCard icon={Eye}      label="Total Visitors"  value={(analytics.counters.total_visitors || 0).toLocaleString()}    color="text-gold-400" />
                  <StatCard icon={Search}   label="Total Searches"  value={(analytics.counters.total_searches || 0).toLocaleString()}    color="text-jade-400" />
                  <StatCard icon={Users}    label="Contributors"    value={(analytics.counters.total_contributors || 0).toLocaleString()} color="text-gold-400" />
                  <StatCard icon={Share2}   label="Shares"          value={(analytics.counters.total_shares || 0).toLocaleString()}      color="text-jade-400" />
                  <StatCard icon={BookOpen} label="Questions"       value={(analytics.counters.total_questions || 0).toLocaleString()}   color="text-gold-400" />
                  <StatCard icon={FileText} label="Papers"          value={(analytics.counters.total_papers || 0).toLocaleString()}      color="text-jade-400" />
                  <StatCard icon={TrendingUp} label="Avg Scroll Depth" value={`${analytics.avg_scroll_depth_pct}%`}                     color="text-gold-400" />
                  <StatCard icon={Activity} label="Avg Time on Page"   value={`${analytics.avg_time_on_page_sec}s`}                     color="text-jade-400" />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  {/* Monthly visitors */}
                  <div className="glass-strong rounded-2xl p-5">
                    <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-muted)' }}>Monthly Visitors</h3>
                    {Object.keys(analytics.monthly_visitors).length === 0 ? (
                      <p className="text-xs" style={{ color: 'var(--text-ghost)' }}>No data yet — grows organically as users visit.</p>
                    ) : (
                      <div className="space-y-2">
                        {Object.entries(analytics.monthly_visitors)
                          .sort((a, b) => b[0].localeCompare(a[0])).slice(0, 12)
                          .map(([month, count]) => (
                            <BarRow key={month} label={month} value={count}
                              max={Math.max(...Object.values(analytics.monthly_visitors))}
                              color="var(--gold-500)" />
                          ))}
                      </div>
                    )}
                  </div>

                  {/* Device breakdown */}
                  <div className="glass-strong rounded-2xl p-5">
                    <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-muted)' }}>Device Breakdown</h3>
                    {Object.keys(analytics.device_breakdown).length === 0 ? (
                      <p className="text-xs" style={{ color: 'var(--text-ghost)' }}>No data yet.</p>
                    ) : (
                      <div className="space-y-3">
                        {[
                          { key: 'mobile',  icon: Smartphone, label: 'Mobile' },
                          { key: 'tablet',  icon: Tablet,     label: 'Tablet' },
                          { key: 'desktop', icon: Monitor,    label: 'Desktop' },
                        ].map(({ key, icon: Icon, label }) => {
                          const val = analytics.device_breakdown[key] || 0
                          const total = Object.values(analytics.device_breakdown).reduce((a, b) => a + b, 0)
                          const pct = total > 0 ? Math.round((val / total) * 100) : 0
                          return (
                            <div key={key} className="flex items-center gap-3">
                              <Icon size={14} style={{ color: 'var(--text-faint)' }} className="shrink-0" />
                              <span className="text-xs w-16 shrink-0" style={{ color: 'var(--text-dim)' }}>{label}</span>
                              <div className="flex-1 h-1.5 rounded-full" style={{ background: 'var(--bg-secondary)' }}>
                                <div className="h-full rounded-full" style={{ width: `${pct}%`, background: 'var(--jade-500)' }} />
                              </div>
                              <span className="text-xs w-12 text-right shrink-0" style={{ color: 'var(--text-muted)' }}>{val} ({pct}%)</span>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>

                  {/* Top pages */}
                  <div className="glass-strong rounded-2xl p-5">
                    <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-muted)' }}>Top Pages</h3>
                    {analytics.top_pages.length === 0 ? (
                      <p className="text-xs" style={{ color: 'var(--text-ghost)' }}>No data yet.</p>
                    ) : (
                      <div className="space-y-2">
                        {analytics.top_pages.map(([page, count]) => (
                          <BarRow key={page} label={page || '/'} value={count}
                            max={analytics.top_pages[0]?.[1] || 1}
                            color="var(--gold-500)" />
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Top search queries */}
                  <div className="glass-strong rounded-2xl p-5">
                    <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-muted)' }}>Top Search Queries</h3>
                    {analytics.top_search_queries.length === 0 ? (
                      <p className="text-xs" style={{ color: 'var(--text-ghost)' }}>No searches yet.</p>
                    ) : (
                      <div className="space-y-2">
                        {analytics.top_search_queries.slice(0, 10).map(({ query, count }) => (
                          <BarRow key={query} label={query} value={count}
                            max={analytics.top_search_queries[0]?.count || 1}
                            color="var(--jade-500)" />
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} />)}
              </div>
            )}
          </div>
        )}

        {/* ── LOGS ─────────────────────────────────────────────────────── */}
        {tab === 'logs' && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-xl font-bold" style={{ color: 'var(--text-primary)' }}>System Logs</h2>
              <button onClick={fetchLogs} className="btn-ghost !px-3 !py-1.5 flex items-center gap-1.5 text-xs">
                <RefreshCw size={13} /> Refresh
              </button>
            </div>
            <div className="glass rounded-xl p-4 font-mono text-xs space-y-1 max-h-[500px] overflow-y-auto"
                 style={{ color: 'var(--text-dim)' }}>
              {logs.length === 0
                ? <p style={{ color: 'var(--text-ghost)' }}>No logs yet. Process a PDF to generate logs.</p>
                : logs.map((entry, i) => (
                  <div key={i} style={{
                    color: entry.includes('ERROR') ? 'var(--rose-500)'
                         : entry.includes('WARN') ? 'var(--gold-500)'
                         : (entry.includes('Done') || entry.includes('saved') || entry.includes('approved')) ? 'var(--jade-500)'
                         : 'var(--text-dim)',
                  }}>
                    {entry}
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
