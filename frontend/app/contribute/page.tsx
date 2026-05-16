'use client'
import { useState, useRef } from 'react'
import { Upload, Heart, FileText, Sparkles, X, ArrowRight } from 'lucide-react'
import Navbar from '@/components/Navbar'

type UploadState = 'idle' | 'uploading' | 'queued' | 'duplicate' | 'error'

interface UploadResult {
  duplicate: boolean
  message: string
  subject?: string
  metadata?: {
    subject: string | null
    subject_code: string | null
    branch: string | null
    programme: string | null
    semester: number | null
    year: number | null
    exam_session: string | null
  }
}

export default function ContributePage() {
  const [file, setFile] = useState<File | null>(null)
  const [status, setStatus] = useState<UploadState>('idle')
  const [result, setResult] = useState<UploadResult | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] ?? null
    setFile(f)
    setStatus('idle')
    setResult(null)
    setErrorMsg('')
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    const f = e.dataTransfer.files?.[0]
    if (f?.type === 'application/pdf') {
      setFile(f)
      setStatus('idle')
      setResult(null)
      setErrorMsg('')
    }
  }

  const handleUpload = async () => {
    if (!file) return
    setStatus('uploading')
    setResult(null)
    setErrorMsg('')

    const formData = new FormData()
    formData.append('file', file)

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/submit/pdf`, {
        method: 'POST',
        body: formData,
      })
      const data: UploadResult = await res.json()

      if (!res.ok) {
        setStatus('error')
        setErrorMsg((data as any).detail || 'Upload failed. Please try again.')
        return
      }

      setResult(data)
      setStatus(data.duplicate ? 'duplicate' : 'queued')
    } catch {
      setStatus('error')
      setErrorMsg('Could not connect to server. Please try again.')
    }
  }

  const reset = () => {
    setFile(null)
    setStatus('idle')
    setResult(null)
    setErrorMsg('')
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <main className="min-h-screen">
      <Navbar />
      <div className="max-w-2xl mx-auto px-4 pt-28 pb-20">
        <h1 className="font-display text-3xl md:text-4xl font-black text-ink-50 mb-2">
          Help Build the <span className="gold-text">Database</span>
        </h1>
        <p className="text-ink-400 text-sm mb-10 leading-relaxed">
          Every paper you upload makes this smarter for every AKTU student.
          Just drop the PDF — we extract everything automatically.
        </p>

        {/* Upload card */}
        <div className="glass-strong rounded-2xl p-6 mb-6">
          <div className="flex items-center gap-3 mb-5">
            <div className="w-9 h-9 rounded-xl bg-jade-500/15 border border-jade-500/20 flex items-center justify-center">
              <Upload size={16} className="text-jade-400" />
            </div>
            <div>
              <h2 className="text-ink-100 font-semibold text-base">Contribute a Question Paper</h2>
              <p className="text-ink-500 text-xs">Drop your PDF · subject, year and diagrams auto-extracted</p>
            </div>
          </div>

          {/* Drop zone */}
          <label
            onDragOver={e => e.preventDefault()}
            onDrop={handleDrop}
            className={`
              block border-2 border-dashed rounded-xl p-8 text-center cursor-pointer
              transition-all duration-200 mb-4
              ${file ? 'border-jade-500/50 bg-jade-500/5' : 'border-ink-600 hover:border-ink-400 hover:bg-white/[0.02]'}
            `}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={handleFileChange}
            />
            {file ? (
              <div className="flex items-center justify-center gap-2">
                <FileText size={16} className="text-jade-400 shrink-0" />
                <span className="text-jade-300 text-sm font-medium truncate max-w-xs">{file.name}</span>
                <span className="text-ink-500 text-xs shrink-0">
                  ({(file.size / 1024 / 1024).toFixed(1)} MB)
                </span>
                <button
                  type="button"
                  onClick={e => { e.preventDefault(); reset() }}
                  className="text-ink-500 hover:text-rose-400 transition-colors ml-1"
                >
                  <X size={13} />
                </button>
              </div>
            ) : (
              <>
                <Upload size={22} className="text-ink-500 mx-auto mb-2" />
                <p className="text-ink-400 text-sm">Drop an AKTU PDF here or click to browse</p>
                <p className="text-ink-600 text-xs mt-1">Max 20 MB</p>
              </>
            )}
          </label>

          {/* Auto-extract note */}
          <div className="glass rounded-lg px-3 py-2 mb-4 flex items-start gap-2">
            <Sparkles size={12} className="text-gold-400 mt-0.5 shrink-0" />
            <p className="text-ink-400 text-xs leading-relaxed">
              Subject, semester, year, branch and diagrams are read automatically from
              the paper. Your paper goes straight into the processing queue — no admin
              review needed.
            </p>
          </div>

          {/* Result: queued */}
          {status === 'queued' && result && (
            <div className="glass rounded-xl px-4 py-3 mb-4 border border-jade-500/20 bg-jade-500/5">
              <div className="flex items-center gap-2 mb-1">
                <Sparkles size={14} className="text-jade-400" />
                <span className="text-jade-300 text-sm font-semibold">Paper received — processing now</span>
              </div>
              {result.metadata?.subject && (
                <p className="text-ink-400 text-xs mb-1">
                  Detected: <span className="text-ink-200">{result.metadata.subject}</span>
                  {result.metadata.year ? ` · ${result.metadata.year}` : ''}
                  {result.metadata.exam_session ? ` ${result.metadata.exam_session.charAt(0).toUpperCase() + result.metadata.exam_session.slice(1)} Sem` : ''}
                </p>
              )}
              <p className="text-ink-500 text-xs">
                Questions will be extracted, clustered, and searchable shortly. Thank you for helping every AKTU student!
              </p>
              <div className="flex gap-2 mt-3">
                <button onClick={reset} className="text-xs btn-ghost !px-3 !py-1.5">
                  Submit another
                </button>
                <a href="/" className="text-xs btn-primary !px-3 !py-1.5 inline-block text-center">
                  Go search <ArrowRight size={11} className="inline ml-1" />
                </a>
              </div>
            </div>
          )}

          {/* Result: duplicate */}
          {status === 'duplicate' && result && (
            <div className="glass rounded-xl px-4 py-3 mb-4 border border-gold-500/20 bg-gold-500/5">
              <div className="flex items-center gap-2 mb-1">
                <FileText size={14} className="text-gold-400" />
                <span className="text-gold-300 text-sm font-semibold">Already in our database</span>
              </div>
              <p className="text-ink-400 text-xs mb-3 leading-relaxed">{result.message}</p>
              <div className="flex gap-2">
                <button onClick={reset} className="text-xs btn-ghost !px-3 !py-1.5">
                  Upload a different paper
                </button>
                <a href="/papers" className="text-xs btn-primary !px-3 !py-1.5 inline-block text-center">
                  Browse indexed papers →
                </a>
              </div>
            </div>
          )}

          {/* Error */}
          {status === 'error' && (
            <div className="flex items-center gap-2 text-rose-400 text-sm mb-4 glass rounded-lg px-3 py-2 border border-rose-500/20">
              <span className="shrink-0">⚠</span> {errorMsg}
            </div>
          )}

          {status !== 'queued' && status !== 'duplicate' && (
            <button
              onClick={handleUpload}
              disabled={!file || status === 'uploading'}
              className="btn-primary w-full disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {status === 'uploading' ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-3.5 h-3.5 border-2 border-ink-900/40 border-t-ink-900 rounded-full animate-spin" />
                  Reading paper header…
                </span>
              ) : (
                'Submit Paper ↗'
              )}
            </button>
          )}
        </div>

        {/* Donate card */}
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
            This project is free for all AKTU students and always will be. If this saved
            you time during exams, consider buying the developer a cup of chai. ☕
          </p>
          <div className="grid grid-cols-3 gap-2 mb-4">
            {['₹10', '₹50', '₹100'].map(amt => (
              <button
                key={amt}
                className="btn-ghost text-sm py-2 hover:border-gold-500/30 hover:text-gold-400"
              >
                {amt}
              </button>
            ))}
          </div>
          {/* Replace href with your actual UPI link */}
          <a href="#" className="btn-primary w-full text-center block">
            Donate via UPI ↗
          </a>
          <p className="text-ink-600 text-xs text-center mt-2">UPI · Paytm · Google Pay · PhonePe</p>
        </div>
      </div>
    </main>
  )
}
