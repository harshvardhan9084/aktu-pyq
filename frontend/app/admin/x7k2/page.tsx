'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Lock, Eye, EyeOff } from 'lucide-react'

export default function AdminLogin() {
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const router = useRouter()

  const handleLogin = async () => {
    if (!password) return
    setLoading(true)
    setError('')
    try {
      const res = await fetch('/api/admin/auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })
      if (res.ok) {
        const data = await res.json()
        if (data.token) {
          sessionStorage.setItem('admin_token', data.token)
        }
        router.push('/admin/x7k2/dashboard')
      } else {
        setError('Incorrect password.')
      }
    } catch {
      setError('Something went wrong.')
    }
    setLoading(false)
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="w-12 h-12 rounded-2xl bg-gold-500/15 border border-gold-500/20 flex items-center justify-center mx-auto mb-4">
            <Lock size={20} className="text-gold-400" />
          </div>
          <h1 className="font-display text-2xl font-bold text-ink-50">Admin Access</h1>
          <p className="text-ink-500 text-xs mt-1">Restricted area</p>
        </div>

        <div className="glass-strong rounded-2xl p-6">
          <div className="relative mb-4">
            <input
              type={show ? 'text' : 'password'}
              value={password}
              onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleLogin()}
              placeholder="Admin password"
              className="input-field !pr-10"
              autoComplete="current-password"
            />
            <button onClick={() => setShow(!show)} className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-400 hover:text-ink-200" type="button">
              {show ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          </div>
          {error && <p className="text-rose-400 text-xs mb-3">{error}</p>}
          <button onClick={handleLogin} disabled={loading || !password} className="btn-primary w-full disabled:opacity-40">
            {loading ? 'Verifying...' : 'Enter'}
          </button>
        </div>
      </div>
    </main>
  )
}
