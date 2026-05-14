'use client'
import { useState } from 'react'
import { ChevronRight, RotateCcw } from 'lucide-react'
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
  {
    id: 'subject', label: 'Subject',
    options: ['Engineering Mathematics', 'Engineering Electrical', 'Network Theory', 'DBMS', 'Data Structures', 'Signals & Systems', 'Control Systems', 'Digital Electronics', 'Operating Systems'],
  },
  { id: 'unit', label: 'Unit', options: ['All Units', 'Unit 1', 'Unit 2', 'Unit 3', 'Unit 4', 'Unit 5'] },
  { id: 'question_type', label: 'Question Type', options: ['All Types', 'Theory', 'Numerical', 'Short Answer'] },
  { id: 'count', label: 'Show Top', options: ['5 questions', '10 questions', '15 questions', '20 questions', 'All'] },
]

const STEP_COLORS = [
  'border-jade-500/40 text-jade-400',
  'border-gold-500/40 text-gold-400', 'border-jade-500/40 text-jade-400',
  'border-gold-500/40 text-gold-400', 'border-jade-500/40 text-jade-400',
  'border-gold-500/40 text-gold-400', 'border-jade-500/40 text-gold-400',
  'border-gold-500/40 text-gold-400',
]

interface Props {
  onResults: (q: Question[]) => void
  onLoading: (v: boolean) => void
}

export default function DynamicForm({ onResults, onLoading }: Props) {
  const [values, setValues] = useState<Record<string, string>>({})
  const [activeStep, setActiveStep] = useState(0)
  const [error, setError] = useState('')

  const getOptions = (step: typeof STEPS[0]) => {
    if ('dependsOn' in step && step.dependsOn && 'optionsByParent' in step) {
      const parent = values[step.dependsOn as string]
      return (step.optionsByParent as Record<string, string[]>)[parent] ?? []
    }
    return step.options ?? []
  }

  const handleSelect = (stepId: string, value: string, stepIndex: number) => {
    const newValues = { ...values, [stepId]: value }
    STEPS.slice(stepIndex + 1).forEach(s => delete newValues[s.id])
    setValues(newValues)
    if (stepIndex < STEPS.length - 1) setActiveStep(stepIndex + 1)
  }

  const reset = () => { setValues({}); setActiveStep(0); setError('') }

  const handleSearch = async () => {
    if (!values.subject) { setError('Please select at least a subject.'); return }
    setError('')
    onLoading(true)

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL}/search/filter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          university: values.university || 'AKTU',
          programme: values.programme || null,
          branch: values.branch || null,
          subject: values.subject,
          unit: values.unit === 'All Units' ? null : values.unit?.replace('Unit ', ''),
          question_type: values.question_type === 'All Types' ? null
            : values.question_type === 'Short Answer' ? 'short'
            : values.question_type?.toLowerCase(),
          count: values.count === 'All' ? 100 : parseInt(values.count) || 10,
        }),
      })
      if (!res.ok) throw new Error()
      const data = await res.json()
      onResults(data.results)
    } catch {
      setError('Could not reach the server. Make sure the backend is running.')
      onLoading(false)
    }
  }

  return (
    <div className="glass-strong rounded-2xl p-5 md:p-6 text-left">
      <div className="flex items-center justify-between mb-5">
        <p className="text-ink-400 text-xs">Select step by step — like narrowing from country to street</p>
        <button onClick={reset} className="flex items-center gap-1 text-xs text-ink-500 hover:text-ink-300 transition-colors">
          <RotateCcw size={11} /> Reset
        </button>
      </div>

      <div className="space-y-4">
        {STEPS.slice(0, activeStep + 1).map((step, i) => {
          const opts = getOptions(step)
          const selected = values[step.id]
          const isActive = i === activeStep

          return (
            <div key={step.id} className={`transition-all duration-300`}>
              <div className="flex items-center gap-2 mb-2">
                <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${STEP_COLORS[i]}`}>Step {i + 1}</span>
                <span className="text-ink-300 text-sm font-medium">{step.label}</span>
                {selected && !isActive && <><ChevronRight size={12} className="text-ink-600" /><span className="text-gold-400 text-sm">{selected}</span></>}
              </div>

              {(isActive || !selected) && opts.length > 0 && (
                <div className="flex flex-wrap gap-2 pl-0.5">
                  {opts.map(opt => (
                    <button key={opt} onClick={() => handleSelect(step.id, opt, i)}
                      className={`text-xs px-3 py-1.5 rounded-lg border transition-all duration-150 ${selected === opt ? 'bg-gold-500 text-ink-900 border-gold-500 font-medium' : 'border-ink-600 text-ink-300 hover:border-gold-500/50 hover:text-gold-400 glass'}`}>
                      {opt}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {error && <p className="text-rose-400 text-xs mt-3">{error}</p>}

      {values.subject && (
        <button onClick={handleSearch} className="btn-primary w-full mt-5 flex items-center justify-center gap-2">
          Find questions ↗
        </button>
      )}
    </div>
  )
}
