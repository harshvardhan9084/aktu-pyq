'use client'
import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import {
  Upload, CheckCircle, XCircle, Clock, Database,
  AlertTriangle, RefreshCw, FileText,
  Activity, Settings, Users, BookOpen, LogOut
} from 'lucide-react'

type Submission = {
  id: number
  filename: string
  subject: string | null
  semester: number | null
  year: number | null
  submitted_by: string
  status: 'pending' | 'approved' | 'rejected'
  created_at: string
}

type SystemStats = {
  total_questions: number
  total_clusters: number
  total_subjects: number
  total_pdfs_processed: number
  pending_submissions: number
  ocr_errors_today: number
  last_processed: string
}

export default function AdminDashboard() {
  const router = useRouter()
  const [tab, setTab] = useState<'overview' | 'submissions' | 'upload' | 'database' | 'logs'>('overview')
  const [submissions, setSubmissions] = useState<Submission[]>([])
  const [stats, setStats] = useState<SystemStats | null>(null)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadMeta, setUploadMeta] = useState({ subject: '', branch: '', semester: '', year: '', university: 'AKTU' })
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'done' | 'error' | 'duplicate'>('idle')
  const [uploadMsg, setUploadMsg] = useState('')
  const [logs, setLogs] = useState<string[]>([])
  const [verified, setVerified] = useState(false)

  const getToken = useCallback((): string => {
    return sessionStorage.getItem('admin_token') || ''
  }, [])

  const authHeaders = useCallback((token: string) => ({ 'X-Admin-Token': token }), [])

  // Verify auth FIRST, then load data only if verified
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch('/api/admin/verify')
        if (!res.ok || cancelled) {
          router.push('/admin/x7k2')
          return
        }
        setVerified(true)
        const token = getToken()
        await Promise.all([
          loadSubmissions(token),
          loadStats(token),
        ])
      } catch {
        router.push('/admin/x7k2')
      }
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

  const handleApprove = async (id: number) => {
    try {
      const token = getToken()
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/submissions/${id}/approve`, {
        method: 'POST',
        headers: authHeaders(token),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setUploadStatus('error')
        setUploadMsg(data.detail || 'Approval failed.')
        return
      }
      await loadSubmissions()
      await loadStats()
    } catch {
      setUploadStatus('error')
      setUploadMsg('Could not reach backend.')
    }
  }

  const handleReject = async (id: number) => {
    try {
      const token = getToken()
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/submissions/${id}/reject`, {
        method: 'POST',
        headers: authHeaders(token),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setUploadStatus('error')
        setUploadMsg(data.detail || 'Rejection failed.')
        return
      }
      await loadSubmissions()
      await loadStats()
    } catch {
      setUploadStatus('error')
      setUploadMsg('Could not reach backend.')
    }
  }

  const handleAdminUpload = async () => {
    if (!uploadFile) return
    setUploadStatus('uploading')
    setUploadMsg('')
    const formData = new FormData()
    formData.append('file', uploadFile)
    Object.entries(uploadMeta).forEach(([k, v]) => formData.append(k, v))

    try {
      const token = getToken()
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/upload`, {
        method: 'POST',
        headers: authHeaders(token),
        body: formData,
      })
      const data = await res.json()
      if (res.status === 409) { setUploadStatus('duplicate'); setUploadMsg('Duplicate paper — already in database.') }
      else if (!res.ok) { setUploadStatus('error'); setUploadMsg(data.detail || 'Upload failed.') }
      else { setUploadStatus('done'); setUploadMsg(`Done! ${data.questions_extracted} questions extracted, ${data.clusters_formed} clusters formed.`); await loadStats() }
    } catch { setUploadStatus('error'); setUploadMsg('Could not reach backend.') }
  }

  const fetchLogs = async () => {
    try {
      const token = getToken()
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/logs`, { headers: authHeaders(token) })
      if (res.ok) { const data = await res.json(); setLogs(data.logs ?? []) }
    } catch {}
  }

  const handleDbAction = async (label: string, endpoint: string, isDanger: boolean) => {
    try {
      const token = getToken()
      const method = endpoint.includes('pending') ? 'DELETE' : 'POST'
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}${endpoint}`, {
        method,
        headers: authHeaders(token),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setUploadStatus('error')
        setUploadMsg(data.detail || `${label} failed.`)
        return
      }
      setUploadStatus('done')
      setUploadMsg(`${label} completed successfully.`)
      await loadStats()
      await loadSubmissions()
    } catch {
      setUploadStatus('error')
      setUploadMsg(`Could not reach backend for: ${label}`)
    }
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
    { id: 'database', icon: Database, label: 'Database' },
    { id: 'logs', icon: FileText, label: 'Logs' },
  ]

  // Don't render dashboard until auth is verified
  if (!verified) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <div className="text-ink-500 text-sm animate-pulse">Verifying access...</div>
      </main>
    )
  }

  return (
    <main className="min-h-screen">
      <div className="glass border-b border-white/5 px-4 md:px-6 h-14 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center gap-2">
          <Settings size={15} className="text-gold-400" />
          <span className="font-display font-bold text-sm text-ink-100">Admin Panel</span>
          <span className="text-ink-600 text-xs ml-2">· AKTU PYQ</span>
        </div>
        <button onClick={handleLogout} className="flex items-center gap-1.5 text-xs text-ink-400 hover:text-rose-400 transition-colors">
          <LogOut size={13} /> Logout
        </button>
      </div>

      <div className="max-w-6xl mx-auto px-4 md:px-6 py-6">
        <div className="flex gap-1 glass-strong rounded-xl p-1 mb-6 overflow-x-auto">
          {TABS.map(t => (
            <button key={t.id} onClick={() => { setTab(t.id as any); if (t.id === 'logs') fetchLogs() }}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap flex-shrink-0 ${tab === t.id ? 'bg-gold-500 text-ink-900' : 'text-ink-300 hover:text-ink-100'}`}>
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
                { label: 'PDFs Processed', val: stats.total_pdfs_processed, icon: FileText, color: 'text-jade-400' },
              ].map(s => (
                <div key={s.label} className="glass rounded-xl p-4">
                  <s.icon size={16} className={`${s.color} mb-2`} />
                  <div className={`font-display font-bold text-2xl ${s.color}`}>{s.val}</div>
                  <div className="text-ink-500 text-xs mt-0.5">{s.label}</div>
                </div>
              )) : Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="glass rounded-xl p-4 animate-pulse">
                  <div className="h-4 w-4 bg-ink-700 rounded mb-2" /><div className="h-8 w-16 bg-ink-700 rounded mb-1" /><div className="h-3 w-20 bg-ink-800 rounded" />
                </div>
              ))}
            </div>
            {stats && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="glass rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2"><Clock size={14} className="text-gold-400" /><span className="text-ink-300 text-sm font-medium">Pending Reviews</span></div>
                  <span className="font-display font-bold text-3xl text-gold-400">{stats.pending_submissions}</span>
                  <p className="text-ink-500 text-xs mt-1">submissions waiting for your review</p>
                  {stats.pending_submissions > 0 && <button onClick={() => setTab('submissions')} className="btn-primary !px-3 !py-1.5 text-xs mt-3">Review now</button>}
                </div>
                <div className="glass rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-2"><AlertTriangle size={14} className="text-rose-400" /><span className="text-ink-300 text-sm font-medium">OCR Errors Today</span></div>
                  <span className={`font-display font-bold text-3xl ${stats.ocr_errors_today > 0 ? 'text-rose-400' : 'text-jade-400'}`}>{stats.ocr_errors_today}</span>
                  <p className="text-ink-500 text-xs mt-1">Last processed: {stats.last_processed ? new Date(stats.last_processed).toLocaleString() : 'Never'}</p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* SUBMISSIONS */}
        {tab === 'submissions' && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-xl font-bold text-ink-100">User Submissions</h2>
              <button onClick={() => loadSubmissions()} className="btn-ghost !px-3 !py-1.5 flex items-center gap-1.5 text-xs"><RefreshCw size={13} /> Refresh</button>
            </div>
            <div className="space-y-3">
              {submissions.length === 0
                ? <div className="glass rounded-xl p-10 text-center text-ink-500 text-sm">No submissions yet.</div>
                : submissions.map(sub => (
                  <div key={sub.id} className="glass rounded-xl p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <FileText size={14} className="text-ink-400 flex-shrink-0" />
                          <span className="text-ink-100 text-sm font-medium truncate">{sub.filename}</span>
                          <span className={`flex-shrink-0 text-xs px-2 py-0.5 rounded-full font-medium ${sub.status === 'pending' ? 'bg-gold-500/15 text-gold-400' : sub.status === 'approved' ? 'bg-jade-500/15 text-jade-400' : 'bg-rose-500/15 text-rose-400'}`}>{sub.status}</span>
                        </div>
                        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-500 pl-5">
                          {sub.subject && <span>Subject: {sub.subject}</span>}
                          {sub.year && <span>Year: {sub.year}</span>}
                          {sub.semester && <span>Sem: {sub.semester}</span>}
                          <span>By: {sub.submitted_by}</span>
                          <span>{new Date(sub.created_at).toLocaleDateString()}</span>
                        </div>
                      </div>
                      {sub.status === 'pending' && (
                        <div className="flex gap-2 flex-shrink-0">
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
            <p className="text-ink-500 text-sm mb-5">Goes straight into the processing pipeline — no review needed.</p>
            <div className="glass-strong rounded-2xl p-5 space-y-3">
              <label className={`block border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${uploadFile ? 'border-gold-500/50 bg-gold-500/5' : 'border-ink-600 hover:border-ink-400'}`}>
                <input type="file" accept=".pdf" className="hidden" onChange={e => { setUploadFile(e.target.files?.[0] ?? null); setUploadStatus('idle'); setUploadMsg('') }} />
                {uploadFile
                  ? <div className="flex items-center justify-center gap-2"><FileText size={16} className="text-gold-400" /><span className="text-gold-300 text-sm">{uploadFile.name}</span></div>
                  : <><Upload size={20} className="text-ink-500 mx-auto mb-2" /><p className="text-ink-400 text-sm">Click to select PDF</p></>}
              </label>
              <div className="grid grid-cols-2 gap-3">
                {(['university', 'branch', 'subject', 'year', 'semester'] as const).map(field => (
                  <input key={field} placeholder={field.charAt(0).toUpperCase() + field.slice(1)} className="input-field text-xs"
                    value={uploadMeta[field]} onChange={e => setUploadMeta({ ...uploadMeta, [field]: e.target.value })} />
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

        {/* DATABASE */}
        {tab === 'database' && (
          <div>
            <h2 className="font-display text-xl font-bold text-ink-100 mb-4">Database Management</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[
                { label: 'Re-run clustering on all questions', desc: 'Recalculates all semantic clusters. Takes ~10 mins. Run after bulk uploads.', action: 'Run Clustering', danger: false, endpoint: '/admin/recluster' },
                { label: 'Rebuild search index', desc: 'Rebuilds the ChromaDB vector index. Run if search results seem off.', action: 'Rebuild Index', danger: false, endpoint: '/admin/rebuild-index' },
                { label: 'Recalculate frequency & importance scores', desc: 'Updates frequency counts and importance scores for all questions.', action: 'Recalculate', danger: false, endpoint: '/admin/recalculate' },
                { label: 'Export database to JSON', desc: 'Download a full backup of all questions and metadata.', action: 'Export', danger: false, endpoint: '/admin/export' },
                { label: 'Manage subjects & syllabus map', desc: 'Add/edit subject names, units, and branch mappings.', action: 'Manage', danger: false, endpoint: '' },
                { label: 'Clear all pending submissions', desc: 'Permanently deletes all pending PDF submissions from the queue.', action: 'Clear Queue', danger: true, endpoint: '/admin/submissions/pending' },
              ].map(item => (
                <div key={item.label} className="glass rounded-xl p-4">
                  <p className="text-ink-200 text-sm font-medium mb-1">{item.label}</p>
                  <p className="text-ink-500 text-xs mb-3 leading-relaxed">{item.desc}</p>
                  <button
                    onClick={() => {
                      if (!item.endpoint) { alert('Coming soon — this feature is under development.'); return }
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

        {/* LOGS */}
        {tab === 'logs' && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-xl font-bold text-ink-100">System Logs</h2>
              <button onClick={fetchLogs} className="btn-ghost !px-3 !py-1.5 flex items-center gap-1.5 text-xs"><RefreshCw size={13} /> Refresh</button>
            </div>
            <div className="glass rounded-xl p-4 font-mono text-xs text-ink-400 space-y-1 max-h-96 overflow-y-auto">
              {logs.length === 0
                ? <p className="text-ink-600">No logs yet. Logs appear here after PDFs are processed.</p>
                : logs.map((log, i) => (
                  <div key={i} className={log.includes('ERROR') ? 'text-rose-400' : log.includes('WARN') ? 'text-gold-400' : log.includes('OK') || log.includes('SUCCESS') ? 'text-jade-400' : ''}>{log}</div>
                ))}
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
