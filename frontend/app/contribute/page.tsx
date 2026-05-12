'use client'
import { useState } from 'react'
import { Upload, Heart, CheckCircle, AlertCircle, FileText } from 'lucide-react'
import Navbar from '@/components/Navbar'

export default function ContributePage() {
  const [file, setFile] = useState<File | null>(null)
  const [meta, setMeta] = useState({ subject: '', semester: '', year: '', name: '' })
  const [status, setStatus] = useState<'idle' | 'uploading' | 'success' | 'error' | 'duplicate'>('idle')
  const [message, setMessage] = useState('')

  const handleUpload = async () => {
    if (!file) return
    setStatus('uploading')
    const formData = new FormData()
    formData.append('file', file)
    formData.append('subject', meta.subject)
    formData.append('semester', meta.semester)
    formData.append('year', meta.year)
    formData.append('submitted_by', meta.name || 'anonymous')

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/submit/pdf`, {
        method: 'POST',
        body: formData,
      })
      const data = await res.json()
      if (res.status === 409) {
        setStatus('duplicate')
        setMessage('This exact paper is already in our database. Thank you anyway!')
      } else if (!res.ok) {
        setStatus('error')
        setMessage(data.detail || 'Upload failed. Please try again.')
      } else {
        setStatus('success')
        setMessage('Paper submitted! An admin will review and add it to the system.')
        setFile(null)
      }
    } catch {
      setStatus('error')
      setMessage('Could not connect to server. Please try again later.')
    }
  }

  return (
    <main className="min-h-screen">
      <Navbar />
      <div className="max-w-2xl mx-auto px-4 pt-28 pb-20">
        <h1 className="font-display text-3xl md:text-4xl font-black text-ink-50 mb-2">
          Help Build the <span className="gold-text">Database</span>
        </h1>
        <p className="text-ink-400 text-sm mb-10 leading-relaxed">
          This system runs on student contributions. Every paper you upload makes it smarter for everyone.
        </p>

        {/* Upload PDF */}
        <div className="glass-strong rounded-2xl p-6 mb-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 rounded-xl bg-jade-500/15 border border-jade-500/20 flex items-center justify-center">
              <Upload size={16} className="text-jade-400" />
            </div>
            <div>
              <h2 className="text-ink-100 font-semibold text-base">Contribute a Question Paper</h2>
              <p className="text-ink-500 text-xs">Upload a PDF → admin reviews → added to the system</p>
            </div>
          </div>

          <label className={`block border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200 mb-4 ${file ? 'border-jade-500/50 bg-jade-500/5' : 'border-ink-600 hover:border-ink-400 hover:bg-white/[0.02]'}`}>
            <input type="file" accept=".pdf" className="hidden" onChange={e => setFile(e.target.files?.[0] ?? null)} />
            {file ? (
              <div className="flex items-center justify-center gap-2">
                <FileText size={18} className="text-jade-400" />
                <span className="text-jade-300 text-sm font-medium">{file.name}</span>
                <span className="text-ink-500 text-xs">({(file.size / 1024 / 1024).toFixed(1)} MB)</span>
              </div>
            ) : (
              <>
                <Upload size={24} className="text-ink-500 mx-auto mb-2" />
                <p className="text-ink-400 text-sm">Drop a PDF here or click to browse</p>
                <p className="text-ink-600 text-xs mt-1">Max 20MB · AKTU question papers only</p>
              </>
            )}
          </label>

          <div className="grid grid-cols-2 gap-3 mb-4">
            <input placeholder="Subject (e.g. Electrical Engg)" className="input-field text-xs" value={meta.subject} onChange={e => setMeta({ ...meta, subject: e.target.value })} />
            <input placeholder="Year (e.g. 2023)" className="input-field text-xs" value={meta.year} onChange={e => setMeta({ ...meta, year: e.target.value })} />
            <input placeholder="Semester (e.g. 4)" className="input-field text-xs" value={meta.semester} onChange={e => setMeta({ ...meta, semester: e.target.value })} />
            <input placeholder="Your name (optional)" className="input-field text-xs" value={meta.name} onChange={e => setMeta({ ...meta, name: e.target.value })} />
          </div>

          {status === 'success' && (
            <div className="flex items-center gap-2 text-jade-400 text-sm mb-3 glass rounded-lg px-3 py-2">
              <CheckCircle size={15} /> {message}
            </div>
          )}
          {(status === 'error' || status === 'duplicate') && (
            <div className="flex items-center gap-2 text-rose-400 text-sm mb-3 glass rounded-lg px-3 py-2">
              <AlertCircle size={15} /> {message}
            </div>
          )}

          <button onClick={handleUpload} disabled={!file || status === 'uploading'} className="btn-primary w-full disabled:opacity-40 disabled:cursor-not-allowed">
            {status === 'uploading' ? 'Uploading...' : 'Submit for Review ↗'}
          </button>
        </div>

        {/* Donate */}
        <div id="donate" className="glass-strong rounded-2xl p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 rounded-xl bg-rose-600/15 border border-rose-500/20 flex items-center justify-center">
              <Heart size={16} className="text-rose-400" />
            </div>
            <div>
              <h2 className="text-ink-100 font-semibold text-base">Support with a Donation</h2>
              <p className="text-ink-500 text-xs">Keeps the servers running. Even ₹10 helps.</p>
            </div>
          </div>
          <p className="text-ink-400 text-sm leading-relaxed mb-4">
            This project is free for all AKTU students and always will be.
            If this saved you time during exams, consider buying the developer a cup of chai. ☕
          </p>
          <div className="grid grid-cols-3 gap-2 mb-4">
            {['₹10', '₹50', '₹100'].map(amt => (
              <button key={amt} className="btn-ghost text-sm py-2 hover:border-gold-500/30 hover:text-gold-400">{amt}</button>
            ))}
          </div>
          {/* Replace href with your actual UPI/payment link */}
          <a href="#" className="btn-primary w-full text-center block">Donate via UPI ↗</a>
          <p className="text-ink-600 text-xs text-center mt-2">UPI · Paytm · Google Pay · PhonePe</p>
        </div>
      </div>
    </main>
  )
}
