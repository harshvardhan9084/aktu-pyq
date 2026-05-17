'use client'
import Link from 'next/link'
import { useState } from 'react'
import { Menu, X, Zap, Sun, Moon } from 'lucide-react'
import { useTheme } from '@/components/ThemeProvider'

export default function Navbar() {
  const [open, setOpen] = useState(false)
  const { theme, toggle } = useTheme()

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 glass border-b" style={{ borderColor: 'var(--border-subtle)' }}>
      <div className="max-w-6xl mx-auto px-4 md:px-6 h-14 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 group">
          <div
            className="w-7 h-7 rounded-md flex items-center justify-center group-hover:scale-105 transition-transform"
            style={{ background: 'rgba(232,184,75,0.15)', border: '1px solid rgba(232,184,75,0.25)' }}
          >
            <Zap size={14} style={{ color: 'var(--gold-500)' }} />
          </div>
          <span className="font-display font-bold text-base tracking-tight" style={{ color: 'var(--text-primary)' }}>
            AKTU <span className="gold-text">PYQ</span>
          </span>
        </Link>

        <div className="hidden md:flex items-center gap-5">
          {[
            { href: '/#search', label: 'Search' },
            { href: '/papers', label: 'Papers' },
            { href: '/contribute', label: 'Contribute' },
          ].map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className="text-sm transition-colors"
              style={{ color: 'var(--text-dim)' }}
              onMouseEnter={e => (e.currentTarget.style.color = 'var(--text-primary)')}
              onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-dim)')}
            >
              {label}
            </Link>
          ))}
          <Link href="/contribute#donate" className="btn-primary !px-4 !py-1.5">
            Support ↗
          </Link>

          {/* Theme toggle */}
          <button
            onClick={toggle}
            aria-label="Toggle theme"
            className="theme-toggle w-8 h-8 rounded-lg glass flex items-center justify-center"
            title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          >
            {theme === 'dark'
              ? <Sun size={14} style={{ color: 'var(--gold-400)' }} />
              : <Moon size={14} style={{ color: 'var(--text-dim)' }} />
            }
          </button>
        </div>

        <div className="flex items-center gap-2 md:hidden">
          {/* Mobile theme toggle */}
          <button
            onClick={toggle}
            aria-label="Toggle theme"
            className="theme-toggle w-8 h-8 rounded-lg glass flex items-center justify-center"
          >
            {theme === 'dark'
              ? <Sun size={13} style={{ color: 'var(--gold-400)' }} />
              : <Moon size={13} style={{ color: 'var(--text-dim)' }} />
            }
          </button>
          <button
            className="transition-colors"
            style={{ color: 'var(--text-dim)' }}
            onClick={() => setOpen(!open)}
            aria-label="Toggle menu"
          >
            {open ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>

      {open && (
        <div
          className="md:hidden glass-strong border-t px-4 py-4 flex flex-col gap-3"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <Link href="/#search" className="text-sm py-2" style={{ color: 'var(--text-secondary)' }} onClick={() => setOpen(false)}>Search</Link>
          <Link href="/papers" className="text-sm py-2" style={{ color: 'var(--text-secondary)' }} onClick={() => setOpen(false)}>Papers</Link>
          <Link href="/contribute" className="text-sm py-2" style={{ color: 'var(--text-secondary)' }} onClick={() => setOpen(false)}>Contribute</Link>
          <Link href="/contribute#donate" className="btn-primary text-center mt-1" onClick={() => setOpen(false)}>Support ↗</Link>
        </div>
      )}
    </nav>
  )
}
