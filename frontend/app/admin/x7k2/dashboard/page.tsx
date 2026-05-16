'use client'
import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import {
  Upload, CheckCircle, XCircle, Clock, Database,
  AlertTriangle, RefreshCw, FileText, Link2,
  Activity, Settings, Users, BookOpen, LogOut, BarChart2
} from 'lucide-react'

type Submission = {
  id: number
  filename: string
  subject: string | null
  subject_code: string | null
  branch: string | null
  semester: number | null
  year: number | null
  exam_session: string | null
  submitted_by: string
  status: 'pending' | 'approved' | 'rejected'
  created_at: string
}

type SystemStats = {
  total_questions: number
  total_clusters: number
  total_subjects: number
  total_pdfs_processed: number
  approved_papers: number
  pending_submissions: number
  scrape_pending: number
  scrape_done: number
  scrape_failed: number
  ocr_errors_today: number
  last_processed: string
  site_counters: Record<string, number>
}

type ScrapeItem = {
  id: number
  pdf_url: string
  status: string
  error_message: string | null
  subject: string | null
  questions_extracted: number
  created_at: string
  processed_at: string | null
}

export default function AdminDashboard() {
  const router = useRouter()
  const [tab, setTab] = useState<'overview' | 'submissions' | 'upload' | 'bulkimport' | 'database' | 'analytics' | 'logs'>('overview')
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [stats, setStats] = useState<SystemStats | null>(null)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadMeta, setUploadMeta] = useState({ subject: '', branch: '', semester: '', year: '', university: 'AKTU', exam_session: '', subject_code: '' })
  const [metaAutoFilled, setMetaAutoFilled] = useState(false)
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'done' | 'error' | 'duplicate'>('idle')
  const [uploadMsg, setUploadMsg] = useState('')
  const [logs, setLogs] = useState<string[]>([])
  const [verified, setVerified] = useState(false)

  // Bulk import
  const [bulkLines, setBulkLines] = useState('')
  const [bulkResult, setBulkResult] = useState<{ queued: number; not_found: number; already_queued: number } | null>(null)
  const [bulkRunning, setBulkRunning] = useState(false)
  const [scrapeItems, setScrapeItems] = useState<ScrapeItem[]>([])
  const [scrapeRunning, setScrapeRunning] = useState(false)

  // Analytics
  const [analytics, setAnalytics] = useState<{ counters: Record<string, number>; monthly_visitors: Record<string, number> } | null>(null)

  const getToken = useCallback((): string => sessionStorage.getItem('admin_token') || '', [])
  const authHeaders = useCallback((token: string) => ({ 'X-Admin-Token': token }), [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch('/api/admin/verify')
        if (!res.ok || cancelled) { router.push('/admin/x7k2'); return }
        setVerified(true)
        const token = getToken()
        await Promise.all([loadSubmissions(token), loadStats(token)])
      } catch { router.push('/admin/x7k2') }
    })()
    return () => { cancelled = true }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const loadSubmissions = async (token?: string) => {
    const t = token ?? getToken()
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/submissions`, { headers: authHeaders(t) })
      if (res.ok) setSubmissions(await res.json())
    } catch {}
  }

  const loadStats = async (token?: string) => {
    const t = token ?? getToken()
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/stats`, { headers: authHeaders(t) })
      if (res.ok) setStats(await res.json())
    } catch {}
  }

  const loadScrapeStatus = async () => {
    const t = getToken()
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/scrape/status`, { headers: authHeaders(t) })
      if (res.ok) {
        const d = await res.json()
        setScrapeItems(d.recent ?? [])
      }
    } catch {}
  }

  const loadAnalytics = async () => {
    const t = getToken()
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/analytics/summary`, { headers: authHeaders(t) })
      if (res.ok) setAnalytics(await res.json())
    } catch {}
  }

  // Auto-extract metadata when admin picks a file
  const handleFileSelect = async (f: File) => {
    setUploadFile(f)
    setUploadStatus('idle')
    setUploadMsg('')
    setMetaAutoFilled(false)
    const token = getToken()
    const fd = new FormData()
    fd.append('file', f)
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/metadata/extract`, {
        method: 'POST', headers: authHeaders(token), body: fd,
      })
      if (res.ok) {
        const d = await res.json()
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

  const handleApprove = async (id: number) => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/submissions/${id}/approve`, {
        method: 'POST', headers: authHeaders(getToken()),
      })
      if (!res.ok) { const d = await res.json().catch(() => ({})); setUploadMsg(d.detail || 'Approval failed.'); return }
      await Promise.all([loadSubmissions(), loadStats()])
    } catch { setUploadMsg('Could not reach backend.') }
  }

  const handleReject = async (id: number) => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/submissions/${id}/reject`, {
        method: 'POST', headers: authHeaders(getToken()),
      })
      if (!res.ok) { const d = await res.json().catch(() => ({})); setUploadMsg(d.detail || 'Rejection failed.'); return }
      await Promise.all([loadSubmissions(), loadStats()])
    } catch {}
  }

  const handleAdminUpload = async () => {
    if (!uploadFile) return
    setUploadStatus('uploading'); setUploadMsg('')
    const formData = new FormData()
    formData.append('file', uploadFile)
    Object.entries(uploadMeta).forEach(([k, v]) => formData.append(k, v))
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/upload`, {
        method: 'POST', headers: authHeaders(getToken()), body: formData,
      })
      const data = await res.json()
      if (res.status === 409) { setUploadStatus('duplicate'); setUploadMsg('Duplicate — already processed.') }
      else if (!res.ok) { setUploadStatus('error'); setUploadMsg(data.detail || 'Upload failed.') }
      else {
        setUploadStatus('done')
        setUploadMsg(`Done! ${data.new_questions} new questions, ${data.updated_questions} updated, ${data.clusters_formed} clusters.`)
        await loadStats()
      }
    } catch { setUploadStatus('error'); setUploadMsg('Could not reach backend.') }
  }

  const handleBulkFeed = async () => {
    const lines = bulkLines.trim().split('\n').filter(Boolean)
    if (!lines.length) return
    setBulkResult(null)
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/scrape/feed`, {
        method: 'POST',
        headers: { ...authHeaders(getToken()), 'Content-Type': 'application/json' },
        body: JSON.stringify({ lines }),
      })
      if (res.ok) setBulkResult(await res.json())
    } catch {}
    loadScrapeStatus()
  }

  const handleRunScraper = async () => {
    setScrapeRunning(true)
    try {
      await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/scrape/run`, {
        method: 'POST', headers: authHeaders(getToken()),
      })
    } catch {}
    setScrapeRunning(false)
    loadScrapeStatus()
    loadStats()
  }

  const handleDbAction = async (label: string, endpoint: string, isDanger: boolean) => {
    try {
      const method = endpoint.includes('pending') ? 'DELETE' : 'POST'
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}${endpoint}`, {
        method, headers: authHeaders(getToken()),
      })
      if (!res.ok) { const d = await res.json().catch(() => ({})); setUploadMsg(d.detail || `${label} failed.`); setUploadStatus('error'); return }
      setUploadStatus('done'); setUploadMsg(`${label} completed.`)
      await Promise.all([loadStats(), loadSubmissions()])
    } catch { setUploadStatus('error'); setUploadMsg(`Could not reach backend for: ${label}`) }
  }

  const fetchLogs = async () => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/logs`, { headers: authHeaders(getToken()) })
      if (res.ok) { const data = await res.json(); setLogs(data.logs ?? []) }
    } catch {}
  }

  const handleLogout = async () => {
    await fetch('/api/admin/logout', { method: 'POST' })
    sessionStorage.removeItem('admin_token')
    router.push('/admin/x7k2')
  }

  const TABS = [
    { id: 'overview', icon: Activity, label: 'Overview' },
    { id: 'submissions', icon: Clock, label: 'Submissions', badge: submissions.filter(s => s.status === 'pending').length },
    { id: 'upload', icon: Upload, label: 'Upload PDF' },
    { id: 'bulkimport', icon: Link2, label: 'Bulk Import' },
    { id: 'database', icon: Database, label: 'Database' },
    { id: 'analytics', icon: BarChart2, label: 'Analytics' },
    { id: 'logs', icon: FileText, label: 'Logs' },
  ]

  if (!verified) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <div className="text-ink-500 text-sm animate-pulse">Verifying access...</div>
      </main>
    )
  }

  return (
    <main className="min-h-screen">
      {/* Header */}
      <div className="glass border-b border-white/5 px-4 md:px-6 h-14 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center gap-2">
          <Settings size={15} className="text-gold-400" />
          <span className="font-display font-bold text-sm text-ink-100">Admin Panel</span>
          <span className="text-ink-600 text-xs ml-2">· AKTU PYQ v2</span>
        </div>
        <button onClick={handleLogout} className="flex items-center gap-1.5 text-xs text-ink-400 hover:text-rose-400 transition-colors">
          <LogOut size={13} /> Logout
        </button>
      </div>

      <div className="max-w-6xl mx-auto px-4 md:px-6 py-6">
        {/* Tabs */}
        <div className="flex gap-1 glass-strong rounded-xl p-1 mb-6 overflow-x-auto">
          {TABS.map(t => (
            <button key={t.id}
              onClick={() => {
                setTab(t.id as typeof tab)
                if (t.id === 'logs') fetchLogs()
                if (t.id === 'bulkimport') loadScrapeStatus()
                if (t.id === 'analytics') loadAnalytics()
              }}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap flex-shrink-0 ${tab === t.id ? 'bg-gold-500 text-ink-900' : 'text-ink-300 hover:text-ink-100'}`}
            >
              <t.icon size={14} />
              {t.label}
              {'badge' in t && (t.badge as number) > 0 && (
                <span className={`text-xs px-1.5 py-0.5 rounded-full font-bold ${tab === t.id ? 'bg-ink-900/30 text-ink-900' : 'bg-rose-500/80 text-white'}`}>{t.badge}</span>
              )}
            </button>
          ))}
        </div>

        {/* OVERVIEW */}
        {tab === 'overview' && (
          <div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
              {stats ? [
                { label: 'Total Questions', val: stats.total_questions.toLocaleString(), icon: BookOpen, color: 'text-gold-400' },
                { label: 'Clusters', val: stats.total_clusters.toLocaleString(), icon: Database, color: 'text-jade-400' },
                { label: 'Subjects', val: stats.total_subjects, icon: Users, color: 'text-gold-400' },
                { label: 'Papers Approved', val: stats.approved_papers, icon: FileText, color: 'text-jade-400' },
              ].map(s => (
                <div key={s.label} className="glass rounded-xl p-4">
                  <s.icon size={16} className={`${s.color} mb-2`} />
                  <div className={`font-display font-bold text-2xl ${s.color}`}>{s.val}</div>
                  <div className="text-ink-500 text-xs mt-0.5">{s.label}</div>
                </div>
              )) : Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="glass rounded-xl p-4 animate-pulse"><div className="h-4 w-4 bg-ink-700 rounded mb-2" /><div className="h-8 w-16 bg-ink-700 rounded mb-1" /><div className="h-3 w-20 bg-ink-800 rounded" /></div>
              ))}
            </div>
            {stats && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="glass rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2"><Clock size={14} className="text-gold-400" /><span className="text-ink-300 text-sm font-medium">Pending Reviews</span></div>
                  <span className="font-display font-bold text-3xl text-gold-400">{stats.pending_submissions}</span>
                  {stats.pending_submissions > 0 && <button onClick={() => setTab('submissions')} className="btn-primary !px-3 !py-1.5 text-xs mt-3 block">Review now</button>}
                </div>
                <div className="glass rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2"><Link2 size={14} className="text-jade-400" /><span className="text-ink-300 text-sm font-medium">Scrape Queue</span></div>
                  <div className="flex gap-3 text-sm mt-1">
                    <span className="text-gold-400 font-bold">{stats.scrape_pending}</span><span className="text-ink-500">pending</span>
                    <span className="text-jade-400 font-bold">{stats.scrape_done}</span><span className="text-ink-500">done</span>
                    <span className="text-rose-400 font-bold">{stats.scrape_failed}</span><span className="text-ink-500">failed</span>
                  </div>
                  {stats.scrape_pending > 0 && <button onClick={() => setTab('bulkimport')} className="btn-ghost !px-3 !py-1.5 text-xs mt-3 block">Run batch →</button>}
                </div>
                <div className="glass rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2"><AlertTriangle size={14} className="text-rose-400" /><span className="text-ink-300 text-sm font-medium">OCR Errors Today</span></div>
                  <span className={`font-display font-bold text-3xl ${stats.ocr_errors_today > 0 ? 'text-rose-400' : 'text-jade-400'}`}>{stats.ocr_errors_today}</span>
                  <p className="text-ink-500 text-xs mt-1">Last: {stats.last_processed ? new Date(stats.last_processed).toLocaleTimeString() : 'Never'}</p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* SUBMISSIONS */}
        {tab === 'submissions' && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-xl font-bold text-ink-100">Student Submissions</h2>
              <button onClick={() => loadSubmissions()} className="btn-ghost !px-3 !py-1.5 flex items-center gap-1.5 text-xs"><RefreshCw size={13} /> Refresh</button>
            </div>
            <p className="text-ink-500 text-xs mb-4">Student papers are now auto-queued to scrape_queue. Submissions here are the audit trail — approve to trigger processing if auto-queue failed.</p>
            <div className="space-y-3">
              {submissions.length === 0
                ? <div className="glass rounded-xl p-10 text-center text-ink-500 text-sm">No submissions yet.</div>
                : submissions.map(sub => (
                  <div key={sub.id} className="glass rounded-xl p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <FileText size={14} className="text-ink-400 shrink-0" />
                          <span className="text-ink-100 text-sm font-medium truncate">{sub.filename}</span>
                          <span className={`shrink-0 text-xs px-2 py-0.5 rounded-full font-medium ${sub.status === 'pending' ? 'bg-gold-500/15 text-gold-400' : sub.status === 'approved' ? 'bg-jade-500/15 text-jade-400' : 'bg-rose-500/15 text-rose-400'}`}>{sub.status}</span>
                        </div>
                        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-500 pl-5">
                          {sub.subject && <span>{sub.subject}</span>}
                          {sub.subject_code && <span>{sub.subject_code}</span>}
                          {sub.year && <span>{sub.year}{sub.exam_session ? ` · ${sub.exam_session}` : ''}</span>}
                          {sub.semester && <span>Sem {sub.semester}</span>}
                          <span>{new Date(sub.created_at).toLocaleDateString()}</span>
                        </div>
                      </div>
                      {sub.status === 'pending' && (
                        <div className="flex gap-2 shrink-0">
                          <button onClick={() => handleApprove(sub.id)} className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-jade-500/15 text-jade-400 border border-jade-500/20 hover:bg-jade-500/25 transition-all"><CheckCircle size={13} /> Accept</button>
                          <button onClick={() => handleReject(sub.id)} className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-rose-500/15 text-rose-400 border border-rose-500/20 hover:bg-rose-500/25 transition-all"><XCircle size={13} /> Reject</button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* UPLOAD */}
        {tab === 'upload' && (
          <div className="max-w-xl">
            <h2 className="font-display text-xl font-bold text-ink-100 mb-1">Direct PDF Upload</h2>
            <p className="text-ink-500 text-sm mb-5">Straight into the processing pipeline. Metadata auto-filled from paper header — correct if needed.</p>
            <div className="glass-strong rounded-2xl p-5 space-y-3">
              <label className={`block border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${uploadFile ? 'border-gold-500/50 bg-gold-500/5' : 'border-ink-600 hover:border-ink-400'}`}>
                <input type="file" accept=".pdf" className="hidden"
                  onChange={e => { const f = e.target.files?.[0]; if (f) handleFileSelect(f) }} />
                {uploadFile
                  ? <div className="flex items-center justify-center gap-2"><FileText size={16} className="text-gold-400" /><span className="text-gold-300 text-sm">{uploadFile.name}</span></div>
                  : <><Upload size={20} className="text-ink-500 mx-auto mb-2" /><p className="text-ink-400 text-sm">Click to select PDF</p></>}
              </label>
              {metaAutoFilled && (
                <p className="text-jade-400 text-xs flex items-center gap-1"><CheckCircle size={12} /> Metadata auto-detected — verify below</p>
              )}
              <div className="grid grid-cols-2 gap-3">
                {[
                  { key: 'subject', label: 'Subject' },
                  { key: 'subject_code', label: 'Code (EE-301)' },
                  { key: 'branch', label: 'Branch' },
                  { key: 'year', label: 'Year (2022)' },
                  { key: 'semester', label: 'Semester' },
                  { key: 'exam_session', label: 'Session (odd/even)' },
                ].map(({ key, label }) => (
                  <input key={key} placeholder={label} className="input-field text-xs"
                    value={(uploadMeta as any)[key]}
                    onChange={e => setUploadMeta({ ...uploadMeta, [key]: e.target.value })} />
                ))}
              </div>
              {uploadStatus === 'done' && <div className="text-jade-400 text-sm flex gap-2"><CheckCircle size={16} /> {uploadMsg}</div>}
              {uploadStatus === 'duplicate' && <div className="text-gold-400 text-sm flex gap-2"><AlertTriangle size={16} /> {uploadMsg}</div>}
              {uploadStatus === 'error' && <div className="text-rose-400 text-sm flex gap-2"><XCircle size={16} /> {uploadMsg}</div>}
              <button onClick={handleAdminUpload} disabled={!uploadFile || uploadStatus === 'uploading'} className="btn-primary w-full disabled:opacity-40">
                {uploadStatus === 'uploading' ? 'Processing...' : 'Upload & Process'}
              </button>
            </div>
          </div>
        )}

        {/* BULK IMPORT */}
        {tab === 'bulkimport' && (
          <div className="max-w-3xl">
            <h2 className="font-display text-xl font-bold text-ink-100 mb-1">Bulk Import — aktuonline.com</h2>
            <p className="text-ink-500 text-sm mb-5">
              Paste partial PDF names (one per line). System prepends <code className="text-gold-400 text-xs">https://www.aktuonline.com/papers/</code> and appends <code className="text-gold-400 text-xs">.pdf</code>. Direct download bypasses ad walls.
            </p>
            <div className="glass-strong rounded-2xl p-5 space-y-4 mb-6">
              <textarea
                className="input-field font-mono text-xs h-40 resize-none"
                placeholder={"btech-1-sem-electronics-engg-nec101-2022\nbtech-3-sem-electrical-engg-bee301-2022\nbtech-5-sem-cs-dbms-ncs501-2023"}
                value={bulkLines}
                onChange={e => setBulkLines(e.target.value)}
              />
              <button onClick={handleBulkFeed} className="btn-primary">
                Validate &amp; Queue URLs
              </button>
              {bulkResult && (
                <div className="glass rounded-xl px-4 py-3 text-sm">
                  <span className="text-jade-400 font-semibold">{bulkResult.queued} queued</span>
                  <span className="text-ink-500 mx-3">·</span>
                  <span className="text-rose-400">{bulkResult.not_found} not found</span>
                  <span className="text-ink-500 mx-3">·</span>
                  <span className="text-gold-400">{bulkResult.already_queued} already queued</span>
                </div>
              )}
            </div>

            <div className="flex items-center justify-between mb-3">
              <h3 className="text-ink-200 font-semibold text-sm">Scrape Queue</h3>
              <div className="flex gap-2">
                <button onClick={loadScrapeStatus} className="btn-ghost !px-3 !py-1.5 text-xs flex items-center gap-1"><RefreshCw size={12} /> Refresh</button>
                <button
                  onClick={handleRunScraper}
                  disabled={scrapeRunning}
                  className="btn-primary !px-4 !py-1.5 text-xs disabled:opacity-50"
                >
                  {scrapeRunning ? 'Running...' : 'Run Next Batch (10)'}
                </button>
              </div>
            </div>

            <div className="space-y-2 max-h-96 overflow-y-auto">
              {scrapeItems.length === 0
                ? <div className="glass rounded-xl p-6 text-center text-ink-500 text-sm">No items in queue yet.</div>
                : scrapeItems.map(item => (
                  <div key={item.id} className="glass rounded-lg px-4 py-3 flex items-center gap-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium shrink-0 ${
                      item.status === 'done' ? 'bg-jade-500/15 text-jade-400'
                      : item.status === 'failed' ? 'bg-rose-500/15 text-rose-400'
                      : item.status === 'processing' ? 'bg-gold-500/15 text-gold-400'
                      : 'bg-ink-700 text-ink-400'
                    }`}>{item.status}</span>
                    <span className="text-ink-300 text-xs truncate flex-1">{item.pdf_url.replace('https://www.aktuonline.com/papers/', '')}</span>
                    {item.status === 'done' && <span className="text-jade-400 text-xs shrink-0">{item.questions_extracted}q</span>}
                    {item.status === 'failed' && <span className="text-rose-400/70 text-xs shrink-0 max-w-32 truncate">{item.error_message}</span>}
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* DATABASE */}
        {tab === 'database' && (
          <div>
            <h2 className="font-display text-xl font-bold text-ink-100 mb-4">Database Management</h2>
            {(uploadStatus === 'done' || uploadStatus === 'error') && (
              <div className={`mb-4 glass rounded-xl px-4 py-3 text-sm flex gap-2 ${uploadStatus === 'done' ? 'text-jade-400' : 'text-rose-400'}`}>
                {uploadStatus === 'done' ? <CheckCircle size={16} /> : <XCircle size={16} />} {uploadMsg}
              </div>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[
                { label: 'Recalculate frequency & importance scores', desc: 'Updates frequency counts, trend direction, importance scores, and must_revise flags for every question.', action: 'Recalculate', danger: false, endpoint: '/admin/recalculate' },
                { label: 'Re-run clustering', desc: 'Recalculates semantic clusters. Run after bulk uploads. Takes time.', action: 'Run Clustering', danger: false, endpoint: '/admin/recluster' },
                { label: 'Rebuild search index', desc: 'Rebuilds the vector index. Run if search results seem stale.', action: 'Rebuild Index', danger: false, endpoint: '/admin/rebuild-index' },
                { label: 'Export database to JSON', desc: 'Full backup of questions, submissions, clusters, and scrape queue.', action: 'Export', danger: false, endpoint: '/admin/export' },
                { label: 'Manage subjects & syllabus map', desc: 'Add/edit subject names, units, and branch mappings.', action: 'Manage', danger: false, endpoint: '' },
                { label: 'Clear all pending submissions', desc: 'Permanently deletes all pending PDF submissions.', action: 'Clear Queue', danger: true, endpoint: '/admin/submissions/pending' },
              ].map(item => (
                <div key={item.label} className="glass rounded-xl p-4">
                  <p className="text-ink-200 text-sm font-medium mb-1">{item.label}</p>
                  <p className="text-ink-500 text-xs mb-3 leading-relaxed">{item.desc}</p>
                  <button
                    onClick={() => {
                      if (!item.endpoint) { alert('Coming soon.'); return }
                      if (item.danger && !confirm('Are you sure? This cannot be undone.')) return
                      handleDbAction(item.label, item.endpoint, item.danger)
                    }}
                    className={`text-xs px-3 py-1.5 rounded-lg border transition-all ${item.danger ? 'border-rose-500/30 text-rose-400 hover:bg-rose-500/10' : 'border-gold-500/30 text-gold-400 hover:bg-gold-500/10'}`}
                  >{item.action}</button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ANALYTICS */}
        {tab === 'analytics' && (
          <div>
            <div className="flex items-center justify-between mb-5">
              <h2 className="font-display text-xl font-bold text-ink-100">Analytics</h2>
              <button onClick={loadAnalytics} className="btn-ghost !px-3 !py-1.5 text-xs flex items-center gap-1"><RefreshCw size={12} /> Refresh</button>
            </div>
            {analytics ? (
              <>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
                  {[
                    { key: 'total_visitors', label: 'Total Visitors', color: 'text-gold-400' },
                    { key: 'total_searches', label: 'Total Searches', color: 'text-jade-400' },
                    { key: 'total_contributors', label: 'Contributors', color: 'text-gold-400' },
                    { key: 'total_questions', label: 'Questions', color: 'text-jade-400' },
                    { key: 'total_papers', label: 'Papers', color: 'text-gold-400' },
                  ].map(c => (
                    <div key={c.key} className="glass rounded-xl p-4">
                      <div className={`font-display font-bold text-2xl ${c.color}`}>
                        {(analytics.counters[c.key] || 0).toLocaleString()}
                      </div>
                      <div className="text-ink-500 text-xs mt-0.5">{c.label}</div>
                    </div>
                  ))}
                </div>
                <div className="glass-strong rounded-2xl p-5">
                  <h3 className="text-ink-200 text-sm font-semibold mb-4">Monthly Visitors</h3>
                  {Object.keys(analytics.monthly_visitors).length === 0 ? (
                    <p className="text-ink-600 text-xs">No monthly data yet — analytics are collected organically as users visit.</p>
                  ) : (
                    <div className="space-y-2">
                      {Object.entries(analytics.monthly_visitors)
                        .sort((a, b) => b[0].localeCompare(a[0]))
                        .slice(0, 12)
                        .map(([month, count]) => {
                          const max = Math.max(...Object.values(analytics.monthly_visitors))
                          const pct = Math.round((count / max) * 100)
                          return (
                            <div key={month} className="flex items-center gap-3">
                              <span className="text-ink-400 text-xs font-mono w-20 shrink-0">{month}</span>
                              <div className="flex-1 h-1.5 bg-ink-700 rounded-full">
                                <div className="h-full bg-gold-500/60 rounded-full" style={{ width: `${pct}%` }} />
                              </div>
                              <span className="text-ink-300 text-xs w-10 text-right">{count}</span>
                            </div>
                          )
                        })}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="grid grid-cols-3 gap-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="glass rounded-xl p-4 animate-pulse"><div className="h-8 bg-ink-700 rounded mb-2" /><div className="h-3 bg-ink-800 rounded w-24" /></div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* LOGS */}
        {tab === 'logs' && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-xl font-bold text-ink-100">System Logs</h2>
              <button onClick={fetchLogs} className="btn-ghost !px-3 !py-1.5 flex items-center gap-1.5 text-xs"><RefreshCw size={13} /> Refresh</button>
            </div>
            <div className="glass rounded-xl p-4 font-mono text-xs text-ink-400 space-y-1 max-h-[500px] overflow-y-auto">
              {logs.length === 0
                ? <p className="text-ink-600">No logs yet. Logs appear after PDFs are processed.</p>
                : logs.map((log, i) => (
                  <div key={i} className={log.includes('ERROR') ? 'text-rose-400' : log.includes('WARN') ? 'text-gold-400' : (log.includes('Done') || log.includes('OK')) ? 'text-jade-400' : ''}>{log}</div>
                ))}
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
