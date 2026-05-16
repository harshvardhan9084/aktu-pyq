'use client'
import { useState, useEffect } from 'react'
import { ChevronRight, RotateCcw, ChevronLeft } from 'lucide-react'
import type { Question } from '@/lib/supabase'

const STEPS = [
  { id: 'university', label: 'University', options: ['AKTU'] },
  { id: 'programme', label: 'Programme', options: ['B.Tech', 'Diploma', 'MBA', 'MCA', 'M.Tech'] },
  {
    id: 'branch', label: 'Branch', dependsOn: 'programme',
    optionsByParent: {
      'B.Tech': ['Electrical Engineering', 'Computer Science & Engineering', 'Mechanical Engineering', 'Civil Engineering', 'Electronics & Communication', 'Information Technology'],
      'Diploma': ['Electrical', 'Computer Science', 'Mechanical', 'Civil', 'Electronics'],
      'MBA': ['Finance', 'Marketing', 'HR', 'Operations'],
      'MCA': ['Computer Applications'],
      'M.Tech': ['Computer Science', 'Electrical', 'Mechanical'],
    },
  },
  { id: 'semester', label: 'Semester', options: ['Semester 1', 'Semester 2', 'Semester 3', 'Semester 4', 'Semester 5', 'Semester 6', 'Semester 7', 'Semester 8'] },
  { id: 'subject', label: 'Subject', options: [] as string[], dynamic: true },
  { id: 'unit', label: 'Unit', options: ['All Units', 'Unit 1', 'Unit 2', 'Unit 3', 'Unit 4', 'Unit 5'] },
  { id: 'question_type', label: 'Question Type', options: ['All Types', 'Theory', 'Numerical', 'Short Answer', 'Diagram'] },
  { id: 'count', label: 'Show Top', options: ['5 questions', '10 questions', '15 questions', '20 questions', 'All'] },
]

const COOKIE_KEY = 'aktu_prefs'
const STEP_COLORS = [
  'border-jade-500/40 text-jade-400', 'border-gold-500/40 text-gold-400',
  'border-jade-500/40 text-jade-400', 'border-gold-500/40 text-gold-400',
  'border-jade-500/40 text-jade-400', 'border-gold-500/40 text-gold-400',
  'border-jade-500/40 text-gold-400', 'border-gold-500/40 text-gold-400',
]

function getCookie(): Partial<Record<string, string>> {
  try {
    const raw = document.cookie.split(';').find(c => c.trim().startsWith(COOKIE_KEY + '='))
    if (!raw) return {}
    return JSON.parse(decodeURIComponent(raw.split('=')[1]))
  } catch {
    return {}
  }
}

function setCookie(data: Record<string, string>) {
  const expires = new Date(Date.now() + 90 * 24 * 60 * 60 * 1000).toUTCString()
  document.cookie = `${COOKIE_KEY}=${encodeURIComponent(JSON.stringify(data))}; expires=${expires}; path=/`
}

interface Props {
  onResults: (q: Question[]) => void
  onLoading: (v: boolean) => void
}

export default function DynamicForm({ onResults, onLoading }: Props) {
  const [values, setValues] = useState<Record<string, string>>({})
  const [activeStep, setActiveStep] = useState(0)
  const [error, setError] = useState('')
  const [dynamicSubjects, setDynamicSubjects] = useState<string[]>([])
  const [subjectLoading, setSubjectLoading] = useState(false)
  const [cookiePrefs, setCookiePrefs] = useState<Record<string, string>>({})
  const [searchEverything, setSearchEverything] = useState(false)

  // Load cookie prefs on mount and pre-fill steps 0-3
  useEffect(() => {
    const prefs = getCookie()
    if (prefs && Object.keys(prefs).length > 0) {
      setCookiePrefs(prefs as Record<string, string>)
      // Pre-fill and advance to subject step
      const prefilled: Record<string, string> = {}
      const preStepIds = ['university', 'programme', 'branch', 'semester']
      let lastPrefilled = -1
      for (let i = 0; i < preStepIds.length; i++) {
        const sid = preStepIds[i]
        if ((prefs as Record<string, string>)[sid]) {
          prefilled[sid] = (prefs as Record<string, string>)[sid]
          lastPrefilled = i
        } else break
      }
      if (lastPrefilled >= 0) {
        setValues(prefilled)
        setActiveStep(lastPrefilled + 1)
      }
    }
  }, [])

  // Fetch subjects from DB when branch+semester are selected
  useEffect(() => {
    const branch = values.branch
    const semStr = values.semester
    if (!branch && !semStr) return
    const semNum = semStr ? parseInt(semStr.replace('Semester ', '')) : undefined
    setSubjectLoading(true)
    fetch(
      `${process.env.NEXT_PUBLIC_BACKEND_URL}/search/subjects?university=${values.university || 'AKTU'}${branch ? `&branch=${encodeURIComponent(branch)}` : ''}${semNum ? `&semester=${semNum}` : ''}`
    )
      .then(r => r.json())
      .then(d => {
        const subjects: string[] = d.subjects ?? []
        setDynamicSubjects(subjects)
      })
      .catch(() => setDynamicSubjects([]))
      .finally(() => setSubjectLoading(false))
  }, [values.branch, values.semester, values.university])

  const getOptions = (step: typeof STEPS[0]) => {
    if (step.dynamic) {
      return dynamicSubjects.length > 0 ? dynamicSubjects : step.options
    }
    if ('dependsOn' in step && step.dependsOn) {
      const parent = values[step.dependsOn]
      return ('optionsByParent' in step && parent)
        ? (step.optionsByParent as Record<string, string[]>)[parent] ?? []
        : []
    }
    return step.options ?? []
  }

  const handleSelect = (stepId: string, value: string, stepIndex: number) => {
    const newValues = { ...values, [stepId]: value }
    STEPS.slice(stepIndex + 1).forEach(s => delete newValues[s.id])
    setValues(newValues)

    // Save prefs for steps 0-3 into cookie
    const preStepIds = ['university', 'programme', 'branch', 'semester']
    if (preStepIds.includes(stepId)) {
      const prefData: Record<string, string> = {}
      preStepIds.forEach(id => { if (newValues[id]) prefData[id] = newValues[id] })
      setCookie(prefData)
    }

    if (stepIndex < STEPS.length - 1) setActiveStep(stepIndex + 1)
  }

  const handlePrev = () => {
    if (activeStep <= 0) return
    const prevStepId = STEPS[activeStep].id
    const newValues = { ...values }
    delete newValues[prevStepId]
    setValues(newValues)
    setActiveStep(activeStep - 1)
  }

  const reset = () => {
    setValues({})
    setActiveStep(0)
    setError('')
    setSearchEverything(false)
  }

  const handleSearch = async () => {
    if (!values.subject) { setError('Please select at least a subject.'); return }
    setError('')
    onLoading(true)

    const semNum = values.semester ? parseInt(values.semester.replace('Semester ', '')) : null
    const unitNum = values.unit && values.unit !== 'All Units'
      ? parseInt(values.unit.replace('Unit ', ''))
      : null

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/search/filter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          university: values.university || 'AKTU',
          programme: (!searchEverything && values.programme) ? values.programme : null,
          branch: (!searchEverything && values.branch) ? values.branch : null,
          semester: (!searchEverything && semNum) ? semNum : null,
          subject: values.subject,
          unit: unitNum,
          question_type: values.question_type === 'All Types' ? null
            : values.question_type === 'Short Answer' ? 'short'
            : values.question_type?.toLowerCase(),
          count: values.count === 'All' ? 100 : parseInt(values.count) || 10,
        }),
      })
      if (!res.ok) throw new Error()
      const data = await res.json()
      onResults(data.results)

      // Track search
      const sid = sessionStorage.getItem('sid') || ''
      fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/admin/analytics/event`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_type: 'search',
          page: '/',
          metadata: { subject: values.subject, unit: unitNum, mode: 'form' },
          session_id: sid,
        }),
      }).catch(() => {})
    } catch {
      setError('Could not reach the server. Make sure the backend is running.')
      onLoading(false)
    }
  }

  // Cookie summary pill (shown if prefs loaded and step > 3)
  const showCookiePill =
    Object.keys(cookiePrefs).length >= 2 &&
    values.programme === cookiePrefs.programme &&
    values.branch === cookiePrefs.branch

  return (
    <div className="glass-strong rounded-2xl p-5 md:p-6 text-left">
      <div className="flex items-center justify-between mb-4">
        <p className="text-ink-400 text-xs">Narrow from programme → subject → unit</p>
        <div className="flex items-center gap-2">
          {activeStep > 0 && (
            <button
              onClick={handlePrev}
              className="flex items-center gap-1 text-xs text-ink-500 hover:text-ink-300 transition-colors"
            >
              <ChevronLeft size={11} /> Back
            </button>
          )}
          <button onClick={reset} className="flex items-center gap-1 text-xs text-ink-500 hover:text-ink-300 transition-colors">
            <RotateCcw size={11} /> Reset
          </button>
        </div>
      </div>

      {/* Cookie summary pill */}
      {showCookiePill && activeStep >= 4 && (
        <div className="flex items-center gap-2 mb-4 glass rounded-xl px-3 py-2">
          <span className="text-ink-300 text-xs">
            {values.programme} · {values.branch}{values.semester ? ` · ${values.semester}` : ''}
          </span>
          <button
            onClick={() => setSearchEverything(!searchEverything)}
            className={`ml-auto text-xs px-2.5 py-1 rounded-lg border transition-all ${
              searchEverything
                ? 'border-jade-500/30 text-jade-400 bg-jade-500/10'
                : 'border-ink-600 text-ink-500 hover:border-ink-400'
            }`}
          >
            {searchEverything ? 'My branch ✓' : 'Search everything'}
          </button>
        </div>
      )}

      <div className="space-y-4">
        {STEPS.slice(0, activeStep + 1).map((step, i) => {
          const opts = getOptions(step)
          const selected = values[step.id]
          const isActive = i === activeStep

          return (
            <div key={step.id} className="transition-all duration-300">
              <div className="flex items-center gap-2 mb-2">
                <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${STEP_COLORS[i]}`}>
                  Step {i + 1}
                </span>
                <span className="text-ink-300 text-sm font-medium">{step.label}</span>
                {selected && !isActive && (
                  <>
                    <ChevronRight size={12} className="text-ink-600" />
                    <span className="text-gold-400 text-sm">{selected}</span>
                  </>
                )}
              </div>

              {isActive && (
                step.dynamic && subjectLoading ? (
                  <div className="flex gap-2 pl-0.5">
                    {Array.from({ length: 4 }).map((_, k) => (
                      <div key={k} className="h-7 w-28 bg-ink-700 rounded-lg animate-pulse" />
                    ))}
                  </div>
                ) : opts.length > 0 ? (
                  <div className="flex flex-wrap gap-2 pl-0.5">
                    {opts.map(opt => (
                      <button
                        key={opt}
                        onClick={() => handleSelect(step.id, opt, i)}
                        className={`text-xs px-3 py-1.5 rounded-lg border transition-all duration-150 ${
                          selected === opt
                            ? 'bg-gold-500 text-ink-900 border-gold-500 font-medium'
                            : 'border-ink-600 text-ink-300 hover:border-gold-500/50 hover:text-gold-400 glass'
                        }`}
                      >
                        {opt}
                      </button>
                    ))}
                  </div>
                ) : step.dynamic ? (
                  <p className="text-ink-600 text-xs pl-0.5">
                    No subjects in database for this branch/semester yet.{' '}
                    <a href="/contribute" className="text-gold-400 hover:underline">Contribute a paper →</a>
                  </p>
                ) : null
              )}
            </div>
          )
        })}
      </div>

      {error && <p className="text-rose-400 text-xs mt-3">{error}</p>}

      {values.subject && (
        <button
          onClick={handleSearch}
          className="btn-primary w-full mt-5 flex items-center justify-center gap-2"
        >
          Find questions ↗
        </button>
      )}
    </div>
  )
}
