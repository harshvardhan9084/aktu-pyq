'use client'
import Link from 'next/link'
import { useState } from 'react'
import { Menu, X, Zap } from 'lucide-react'

export default function Navbar() {
  const [open, setOpen] = useState(false)

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 glass border-b border-white/5">
      <div className="max-w-6xl mx-auto px-4 md:px-6 h-14 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 group">
          <div className="w-7 h-7 rounded-md bg-gold-500/20 border border-gold-500/30 flex items-center justify-center group-hover:bg-gold-500/30 transition-all">
            <Zap size={14} className="text-gold-400" />
          </div>
          <span className="font-display font-bold text-ink-50 text-base tracking-tight">
            AKTU <span className="gold-text">PYQ</span>
          </span>
        </Link>

        <div className="hidden md:flex items-center gap-6">
          <Link href="/#search" className="text-ink-300 hover:text-ink-100 text-sm transition-colors">Search</Link>
          <Link href="/contribute" className="text-ink-300 hover:text-ink-100 text-sm transition-colors">Contribute</Link>
          <Link href="/contribute#donate" className="btn-primary !px-4 !py-1.5">Support ↗</Link>
        </div>

        <button className="md:hidden text-ink-300 hover:text-ink-100" onClick={() => setOpen(!open)} aria-label="Toggle menu">
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {open && (
        <div className="md:hidden glass-strong border-t border-white/5 px-4 py-4 flex flex-col gap-3">
          <Link href="/#search" className="text-ink-200 text-sm py-2" onClick={() => setOpen(false)}>Search</Link>
          <Link href="/contribute" className="text-ink-200 text-sm py-2" onClick={() => setOpen(false)}>Contribute</Link>
          <Link href="/contribute#donate" className="btn-primary text-center mt-1" onClick={() => setOpen(false)}>Support ↗</Link>
        </div>
      )}
    </nav>
  )
}
