import React, { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Upload, CheckCircle2, FileText, MapPin, GraduationCap, Briefcase } from 'lucide-react'
import { uploadResume, updateProfile } from '../lib/api'
import { useAuthStore } from '../store/authStore'

const SUPPORTED_CITIES = [
  'Bengaluru',
  'Hyderabad',
  'Delhi NCR',
  'Gurgaon',
  'Noida',
  'Mumbai',
  'Pune',
  'Chennai',
  'Ahmedabad',
  'Kolkata',
  'Remote-India',
  'Anywhere-India',
] as const

type Persona = 'fresher' | 'early_career'

const CURRENT_YEAR = new Date().getFullYear()
const GRAD_YEAR_OPTIONS = [CURRENT_YEAR + 1, CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2]

export default function Onboarding() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { email, logout } = useAuthStore()
  const fileRef = useRef<HTMLInputElement>(null)
  const [state, setState] = useState<
    'idle' | 'uploading' | 'parsing' | 'persona' | 'saving' | 'error'
  >('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const [parsed, setParsed] = useState<Record<string, unknown> | null>(null)
  const [autofilled, setAutofilled] = useState<string[]>([])

  // Step 2 (persona + cities) form state
  const [persona, setPersona] = useState<Persona>('early_career')
  const [cities, setCities] = useState<string[]>(['Bengaluru'])
  const [gradYear, setGradYear] = useState<number>(CURRENT_YEAR)

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setErrorMsg('Only PDF files are supported.')
      setState('error')
      return
    }
    setState('uploading')
    setErrorMsg('')
    try {
      const result = await uploadResume(file)
      setState('parsing')
      setParsed(result.parsed || {})
      setAutofilled(result.autofilled_fields || [])
      // Optimistically merge new fields into the profile cache so the
      // route gate sees resume_path immediately and doesn't bounce
      // the user back to /onboarding.
      qc.setQueryData(['profile'], (old: any) => ({
        ...(old || {}),
        ...(result.parsed || {}),
        resume_path: result.resume_path,
      }))
      qc.invalidateQueries({ queryKey: ['profile'] })

      // Heuristic default: 0 yrs experience → fresher.
      const yoe = Number(result.parsed?.years_of_experience ?? 0)
      setPersona(yoe < 1 ? 'fresher' : 'early_career')

      // Pre-pick the parsed city if it's one we support.
      const parsedCity = String(result.parsed?.city ?? '').trim()
      if (parsedCity && SUPPORTED_CITIES.some(c => c.toLowerCase() === parsedCity.toLowerCase())) {
        const matched = SUPPORTED_CITIES.find(c => c.toLowerCase() === parsedCity.toLowerCase())
        if (matched) setCities([matched])
      }

      setState('persona')
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Upload failed'
      setErrorMsg(detail)
      setState('error')
    }
  }

  function toggleCity(c: string) {
    setCities(prev => (prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c]))
  }

  function handleSkip() {
    navigate('/settings')
  }

  async function handleSavePersona() {
    if (cities.length === 0) {
      setErrorMsg('Pick at least one city (or Remote-India / Anywhere-India).')
      return
    }
    setErrorMsg('')
    setState('saving')
    try {
      const payload: Record<string, unknown> = {
        persona,
        preferred_cities: cities,
        // Keep YoE-derived experience_level in sync with persona so discovery
        // filters match the persona band (E3 will read these).
        experience_level:
          persona === 'fresher'
            ? 'entry_level,associate,internship'
            : 'associate,mid_senior_level',
      }
      if (persona === 'fresher') {
        payload.graduation_year = gradYear
        payload.years_of_experience = 0
      }
      const next = await updateProfile(payload)
      qc.setQueryData(['profile'], next)
      navigate('/settings')
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Save failed'
      setErrorMsg(detail)
      setState('persona')
    }
  }

  return (
    <div className="min-h-screen bg-bg flex items-center justify-center p-6">
      <div className="w-full max-w-2xl">
        <div className="text-center mb-8">
          <div className="text-xs font-semibold text-muted uppercase tracking-wider mb-2">
            Welcome{email ? `, ${email}` : ''}
          </div>
          <h1 className="text-3xl font-semibold text-text">Let's set up your profile</h1>
          <p className="text-sm text-muted mt-2">
            Upload your resume and we'll auto-fill your name, contact, skills, and experience.
          </p>
        </div>

        <div className="bg-white border border-border rounded-xl p-8">
          {(state === 'idle' || state === 'uploading' || state === 'parsing' || state === 'error') && (
            <>
              <div
                onClick={() => state !== 'uploading' && fileRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-12 text-center transition-colors ${
                  state === 'uploading'
                    ? 'border-accent bg-indigo-50 cursor-wait'
                    : 'border-border hover:border-accent cursor-pointer'
                }`}
              >
                {state === 'uploading' || state === 'parsing' ? (
                  <>
                    <div className="w-10 h-10 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                    <div className="text-sm font-medium text-text">
                      {state === 'uploading' ? 'Uploading…' : 'Parsing your resume…'}
                    </div>
                  </>
                ) : (
                  <>
                    <Upload size={32} className="mx-auto text-muted mb-3" />
                    <div className="text-base font-medium text-text">Click to upload your resume</div>
                    <div className="text-xs text-muted mt-1">PDF only, max 10MB</div>
                  </>
                )}
              </div>
              <input
                ref={fileRef}
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={handleFile}
              />
              {errorMsg && (
                <div className="text-sm text-danger mt-4 bg-red-50 border border-red-200 rounded p-3">
                  {errorMsg}
                </div>
              )}
              <div className="flex justify-between items-center mt-6 text-xs">
                <button onClick={handleSkip} className="text-muted hover:text-text">
                  Skip — I'll fill it in manually
                </button>
                <button onClick={logout} className="text-muted hover:text-text">
                  Log out
                </button>
              </div>
            </>
          )}

          {(state === 'persona' || state === 'saving') && (
            <>
              <div className="text-center mb-6">
                <CheckCircle2 size={36} className="mx-auto text-success mb-2" />
                <div className="text-lg font-semibold text-text">Resume parsed</div>
                <div className="text-sm text-muted mt-1">
                  {autofilled.length > 0
                    ? `Auto-filled ${autofilled.length} field${autofilled.length === 1 ? '' : 's'}. Two quick questions and we're done.`
                    : "Two quick questions and we're done."}
                </div>
              </div>

              {parsed && (autofilled.length > 0) && (
                <div className="bg-gray-50 border border-border rounded-lg p-3 mb-6 space-y-1 text-xs">
                  {parsed.full_name ? <PreviewRow label="Name" value={String(parsed.full_name)} /> : null}
                  {parsed.email ? <PreviewRow label="Email" value={String(parsed.email)} /> : null}
                  {parsed.city ? <PreviewRow label="City" value={String(parsed.city)} /> : null}
                  {parsed.current_title ? <PreviewRow label="Title" value={String(parsed.current_title)} /> : null}
                  {parsed.years_of_experience ? <PreviewRow label="Experience" value={`${parsed.years_of_experience} yrs`} /> : null}
                </div>
              )}

              <div className="mb-6">
                <div className="flex items-center gap-2 text-sm font-medium text-text mb-3">
                  <Briefcase size={14} className="text-muted" />
                  Where are you in your career?
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <PersonaCard
                    selected={persona === 'fresher'}
                    onClick={() => setPersona('fresher')}
                    title="Fresh Graduate"
                    sub="0 years · entry-level / trainee / graduate program"
                  />
                  <PersonaCard
                    selected={persona === 'early_career'}
                    onClick={() => setPersona('early_career')}
                    title="Early Career"
                    sub="1–3 years · switching for salary / role / company"
                  />
                </div>
              </div>

              {persona === 'fresher' && (
                <div className="mb-6">
                  <div className="flex items-center gap-2 text-sm font-medium text-text mb-2">
                    <GraduationCap size={14} className="text-muted" />
                    Graduation year
                  </div>
                  <div className="flex gap-2">
                    {GRAD_YEAR_OPTIONS.map(y => (
                      <button
                        key={y}
                        type="button"
                        onClick={() => setGradYear(y)}
                        className={`px-4 py-2 text-sm rounded border transition-colors ${
                          gradYear === y
                            ? 'border-accent bg-accent text-white'
                            : 'border-border bg-white text-text hover:border-accent'
                        }`}
                      >
                        {y}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div className="mb-6">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2 text-sm font-medium text-text">
                    <MapPin size={14} className="text-muted" />
                    Where will you work?
                  </div>
                  <div className="text-xs text-muted">
                    {cities.length} selected
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {SUPPORTED_CITIES.map(c => {
                    const on = cities.includes(c)
                    return (
                      <button
                        key={c}
                        type="button"
                        onClick={() => toggleCity(c)}
                        className={`px-3 py-1.5 text-xs rounded-full border transition-colors ${
                          on
                            ? 'border-accent bg-accent text-white'
                            : 'border-border bg-white text-text hover:border-accent'
                        }`}
                      >
                        {c}
                      </button>
                    )
                  })}
                </div>
                <div className="text-xs text-muted mt-2">
                  Pick every city you'd actually move for. Remote-India means India-based remote roles.
                </div>
              </div>

              {errorMsg && (
                <div className="text-sm text-danger mb-4 bg-red-50 border border-red-200 rounded p-3">
                  {errorMsg}
                </div>
              )}

              <button
                onClick={handleSavePersona}
                disabled={state === 'saving' || cities.length === 0}
                className="w-full bg-accent text-white rounded py-3 text-sm font-medium hover:bg-[#4F46E5] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {state === 'saving' ? 'Saving…' : 'Continue to Settings →'}
              </button>
            </>
          )}
        </div>

        <div className="text-center mt-6 text-xs text-muted flex items-center justify-center gap-1.5">
          <FileText size={12} />
          Your resume is stored locally and only used to pre-fill your profile.
        </div>
      </div>
    </div>
  )
}

function PreviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-3">
      <div className="text-muted w-20 shrink-0">{label}</div>
      <div className="text-text font-medium">{value}</div>
    </div>
  )
}

function PersonaCard({
  selected,
  onClick,
  title,
  sub,
}: {
  selected: boolean
  onClick: () => void
  title: string
  sub: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`text-left p-4 rounded border-2 transition-colors ${
        selected
          ? 'border-accent bg-indigo-50'
          : 'border-border bg-white hover:border-accent'
      }`}
    >
      <div className="text-sm font-semibold text-text">{title}</div>
      <div className="text-xs text-muted mt-1 leading-snug">{sub}</div>
    </button>
  )
}
