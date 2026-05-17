/**
 * Analytics collector v2
 * Collects rich, privacy-respecting behavioral data — no external SDKs.
 * All data sent to /admin/analytics/event on the backend.
 *
 * Collected signals (no PII, all inferred):
 *   - Page views with referrer, utm params
 *   - Time spent per page
 *   - Scroll depth (25/50/75/100%)
 *   - Search queries, filters, result counts
 *   - Question expand / share / confirm events
 *   - Contribute attempts + outcomes
 *   - Device class, viewport, connection speed
 *   - Session length, page sequence
 *   - Age group estimation (deferred — via interaction pattern)
 *   - Return visitor detection
 */

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || ''

// ── Session / device fingerprint (no PII) ────────────────────────────────────

function getSessionId(): string {
  let sid = sessionStorage.getItem('sid')
  if (!sid) {
    sid = Math.random().toString(36).slice(2) + Date.now().toString(36)
    sessionStorage.setItem('sid', sid)
  }
  return sid
}

function getOrCreateUserId(): string {
  // Persists across sessions — anonymous, no PII
  let uid = localStorage.getItem('_uid')
  if (!uid) {
    uid = 'u_' + Math.random().toString(36).slice(2) + Date.now().toString(36)
    localStorage.setItem('_uid', uid)
  }
  return uid
}

function isReturnVisitor(): boolean {
  const visits = parseInt(localStorage.getItem('_visits') || '0')
  const newCount = visits + 1
  localStorage.setItem('_visits', String(newCount))
  return visits > 0
}

function getDeviceInfo() {
  const w = window.innerWidth
  const deviceClass = w < 768 ? 'mobile' : w < 1280 ? 'tablet' : 'desktop'
  const conn = (navigator as any).connection
  return {
    device_class: deviceClass,
    screen_w: w,
    screen_h: window.innerHeight,
    connection_type: conn?.effectiveType || null,
    connection_downlink: conn?.downlink || null,
    language: navigator.language,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    is_touch: 'ontouchstart' in window,
    pixel_ratio: window.devicePixelRatio || 1,
  }
}

function getReferrerInfo() {
  const ref = document.referrer
  const params = new URLSearchParams(window.location.search)
  return {
    referrer: ref || null,
    referrer_domain: ref ? new URL(ref).hostname : null,
    utm_source: params.get('utm_source'),
    utm_medium: params.get('utm_medium'),
    utm_campaign: params.get('utm_campaign'),
    is_direct: !ref,
  }
}

// ── Core fire-and-forget sender ───────────────────────────────────────────────

function fire(event_type: string, metadata: Record<string, unknown> = {}) {
  const sid = getSessionId()
  const uid = getOrCreateUserId()
  fetch(`${BACKEND}/admin/analytics/event`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      event_type,
      page: typeof window !== 'undefined' ? window.location.pathname : '/',
      session_id: sid,
      metadata: {
        ...metadata,
        user_id: uid,
        ts: Date.now(),
      },
    }),
  }).catch(() => {})
}

// ── Page view ─────────────────────────────────────────────────────────────────

let _pageStartTime = Date.now()

export function trackPageView() {
  _pageStartTime = Date.now()
  const isReturn = isReturnVisitor()
  fire('page_view', {
    ...getReferrerInfo(),
    ...getDeviceInfo(),
    is_return_visitor: isReturn,
    visit_number: parseInt(localStorage.getItem('_visits') || '1'),
  })
}

// ── Time on page (called on unload / route change) ────────────────────────────

export function trackPageExit() {
  const seconds = Math.round((Date.now() - _pageStartTime) / 1000)
  fire('page_exit', { time_on_page_seconds: seconds })
}

// ── Scroll depth ──────────────────────────────────────────────────────────────

const _scrollMilestones = new Set<number>()

export function initScrollTracking() {
  if (typeof window === 'undefined') return
  _scrollMilestones.clear()

  const onScroll = () => {
    const pct = Math.round(
      ((window.scrollY + window.innerHeight) / document.documentElement.scrollHeight) * 100,
    )
    for (const milestone of [25, 50, 75, 100]) {
      if (pct >= milestone && !_scrollMilestones.has(milestone)) {
        _scrollMilestones.add(milestone)
        fire('scroll_depth', { depth_pct: milestone })
      }
    }
  }
  window.addEventListener('scroll', onScroll, { passive: true })
  return () => window.removeEventListener('scroll', onScroll)
}

// ── Search ────────────────────────────────────────────────────────────────────

export function trackSearch(params: {
  mode: 'nl' | 'form'
  query?: string
  subject?: string
  unit?: number | null
  semester?: number | null
  question_type?: string | null
  result_count: number
  time_to_result_ms: number
}) {
  fire('search', params)
}

// ── Question interactions ─────────────────────────────────────────────────────

export function trackQuestionExpand(questionId: number, rank: number) {
  fire('question_expand', { question_id: questionId, rank })
}

export function trackQuestionShare(questionId: number, method: 'whatsapp' | 'copy') {
  fire('question_share', { question_id: questionId, method })
}

export function trackConfirmAppeared(questionId: number) {
  fire('question_confirm_appeared', { question_id: questionId })
}

// ── Contribute ────────────────────────────────────────────────────────────────

export function trackContributeAttempt() {
  fire('contribute_attempt', getDeviceInfo())
}

export function trackContributeResult(outcome: 'success' | 'duplicate' | 'error', subject?: string) {
  fire('contribute_result', { outcome, subject })
}

// ── Time-on-results (engagement metric) ──────────────────────────────────────

let _resultsStartTime: number | null = null

export function startResultsTimer() {
  _resultsStartTime = Date.now()
}

export function stopResultsTimer(resultCount: number) {
  if (!_resultsStartTime) return
  const seconds = Math.round((Date.now() - _resultsStartTime) / 1000)
  fire('results_engagement', { time_seconds: seconds, result_count: resultCount })
  _resultsStartTime = null
}

// ── Session heartbeat (active time tracking, 30s interval) ───────────────────

let _heartbeatInterval: ReturnType<typeof setInterval> | null = null

export function startHeartbeat() {
  if (_heartbeatInterval) return
  let ticks = 0
  _heartbeatInterval = setInterval(() => {
    ticks++
    // Every 2 minutes (4 ticks × 30s)
    if (ticks % 4 === 0) {
      fire('heartbeat', { active_minutes: ticks / 2 })
    }
  }, 30_000)
}

export function stopHeartbeat() {
  if (_heartbeatInterval) {
    clearInterval(_heartbeatInterval)
    _heartbeatInterval = null
  }
}
