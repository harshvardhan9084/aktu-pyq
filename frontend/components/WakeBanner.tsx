'use client'
/**
 * WakeBanner — shown ONLY when:
 *   1. Backend was detected as sleeping (health check took >3s or failed)
 *   2. User triggered a search before the server fully woke
 *
 * Shows a friendly countdown with rotating student-language messages.
 * Hides automatically when search resolves or after 60s max.
 * NEVER shown when backend is already awake.
 */

import { useEffect, useRef, useState } from 'react'
import { Coffee, Zap } from 'lucide-react'

// Messages in student language — outcome-focused, not technical
const MESSAGES = [
  { at: 0,  text: "Connecting to server…" },
  { at: 8,  text: "Almost there — fetching your questions…" },
  { at: 16, text: "Backend is warming up… give it a moment" },
  { at: 25, text: "Finding the most-repeated questions just for you…" },
  { at: 33, text: "Servers are waking up — this happens once per day" },
  { at: 42, text: "Sending your query to the cloud…" },
  { at: 48, text: "Your financial support helps avoid this extra wait!" },
  { at: 55, text: "Still connecting — won't be long now…" },
]

interface Props {
  active: boolean         // true when a search is in-flight AND backend was sleeping
  elapsed: number         // seconds since search was fired
  totalWait: number       // estimated total wait (e.g. 50s remaining after user hit search)
  onDismiss?: () => void
}

export default function WakeBanner({ active, elapsed, totalWait, onDismiss }: Props) {
  const remaining = Math.max(0, totalWait - elapsed)
  const pct = Math.min(100, (elapsed / totalWait) * 100)

  const message = MESSAGES.reduce(
    (best, m) => (elapsed >= m.at ? m : best),
    MESSAGES[0],
  ).text

  if (!active) return null

  return (
    <div className="wake-banner">
      <div className="glass-strong rounded-2xl px-5 py-3 shadow-2xl flex items-center gap-4 min-w-72 max-w-sm">
        <div className="relative w-9 h-9 flex-shrink-0">
          <Coffee size={22} className="text-gold-400 absolute inset-0 m-auto animate-pulse" />
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-[var(--text-secondary)] text-xs font-medium leading-snug mb-1.5">
            {message}
          </p>
          {/* Progress bar */}
          <div className="h-1 rounded-full overflow-hidden" style={{ background: 'var(--bg-secondary)' }}>
            <div
              className="h-full rounded-full transition-all duration-1000 ease-linear"
              style={{
                width: `${pct}%`,
                background: 'linear-gradient(90deg, var(--gold-500), var(--jade-500))',
              }}
            />
          </div>
          <p className="mt-1 text-[var(--text-faint)] text-[10px]">
            {remaining > 0 ? `~${remaining}s` : 'Any moment now…'}
          </p>
        </div>

        {onDismiss && (
          <button
            onClick={onDismiss}
            className="text-[var(--text-ghost)] hover:text-[var(--text-dim)] transition-colors text-xs flex-shrink-0"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  )
}

/**
 * useBackendWake — hook that tracks backend sleeping status.
 *
 * Call on page mount. Returns:
 *   backendSleeping: boolean — true if health check took >3s or failed
 *   backendReady: boolean    — true once health check resolved
 *   searchElapsed: number    — seconds since user fired search (while sleeping)
 *   startSearchTimer: fn     — call when user fires a search
 *   stopSearchTimer: fn      — call when search resolves
 *   showBanner: boolean      — derived: show banner?
 *   bannerElapsed: number    — how many seconds the banner has been showing
 */
export function useBackendWake(backendUrl: string) {
  const [backendSleeping, setBackendSleeping] = useState(false)
  const [backendReady, setBackendReady] = useState(false)
  const [searchFiredAt, setSearchFiredAt] = useState<number | null>(null)
  const [bannerElapsed, setBannerElapsed] = useState(0)
  const [showBanner, setShowBanner] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // On mount: fire health check and measure how long it takes
  useEffect(() => {
    const t0 = Date.now()
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 8000)

    fetch(`${backendUrl}/health`, { signal: controller.signal })
      .then(() => {
        const elapsed = (Date.now() - t0) / 1000
        clearTimeout(timeout)
        setBackendSleeping(elapsed > 3)  // >3s = was sleeping
        setBackendReady(true)
      })
      .catch(() => {
        clearTimeout(timeout)
        setBackendSleeping(true)  // timed out = sleeping
        // Keep retrying every 5s
        const retry = setInterval(() => {
          fetch(`${backendUrl}/health`)
            .then(() => {
              setBackendReady(true)
              setBackendSleeping(false) // don't hide banner yet — let stop do it
              clearInterval(retry)
            })
            .catch(() => {})
        }, 5000)
      })

    return () => { clearTimeout(timeout); controller.abort() }
  }, [backendUrl])

  // Tick the banner elapsed counter
  useEffect(() => {
    if (showBanner) {
      intervalRef.current = setInterval(() => {
        setBannerElapsed(e => e + 1)
      }, 1000)
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current)
      setBannerElapsed(0)
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [showBanner])

  const startSearchTimer = () => {
    if (!backendReady && backendSleeping) {
      setSearchFiredAt(Date.now())
      setShowBanner(true)
    }
  }

  const stopSearchTimer = () => {
    setShowBanner(false)
    setSearchFiredAt(null)
  }

  // How long since user hit search
  const searchElapsed = searchFiredAt ? Math.floor((Date.now() - searchFiredAt) / 1000) : 0
  // How long the server has been sleeping before user searched (page load time so far)
  const pageAgeAtSearch = searchFiredAt ? Math.floor((searchFiredAt - performance.timeOrigin) / 1000) : 0
  // Total estimated wait = 50s minus time already spent on page (user surfed before searching)
  const totalWait = Math.max(10, 50 - Math.min(30, pageAgeAtSearch))

  return {
    backendSleeping,
    backendReady,
    showBanner,
    bannerElapsed,
    searchElapsed,
    totalWait,
    startSearchTimer,
    stopSearchTimer,
  }
}
