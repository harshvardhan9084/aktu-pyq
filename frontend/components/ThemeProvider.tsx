'use client'
import { createContext, useContext, useEffect, useState, ReactNode } from 'react'

type Theme = 'dark' | 'light'

interface ThemeCtx {
  theme: Theme
  toggle: () => void
}

const Ctx = createContext<ThemeCtx>({ theme: 'dark', toggle: () => {} })

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>('dark')
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    // 1. Check localStorage for explicit user choice
    const stored = localStorage.getItem('theme') as Theme | null
    if (stored === 'dark' || stored === 'light') {
      apply(stored)
      setTheme(stored)
    } else {
      // 2. Default to system preference
      const sys = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
      apply(sys)
      setTheme(sys)
    }
    setMounted(true)

    // 3. Listen for system preference changes (only if user hasn't overridden)
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => {
      if (!localStorage.getItem('theme')) {
        const sys = e.matches ? 'dark' : 'light'
        apply(sys)
        setTheme(sys)
      }
    }
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  function apply(t: Theme) {
    const html = document.documentElement
    html.setAttribute('data-theme', t === 'light' ? 'light' : '')
  }

  const toggle = () => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    // Add transitioning class for smooth CSS transitions
    const html = document.documentElement
    html.classList.add('theme-transitioning')
    apply(next)
    setTheme(next)
    localStorage.setItem('theme', next)
    // Remove transition class after animation
    setTimeout(() => html.classList.remove('theme-transitioning'), 400)
  }

  // Prevent flash of wrong theme
  if (!mounted) return null

  return <Ctx.Provider value={{ theme, toggle }}>{children}</Ctx.Provider>
}

export const useTheme = () => useContext(Ctx)
