import React, { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Upload, CheckCircle2, FileText } from 'lucide-react'
import { uploadResume } from '../lib/api'
import { useAuthStore } from '../store/authStore'

export default function Onboarding() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { email, logout } = useAuthStore()
  const fileRef = useRef<HTMLInputElement>(null)
  const [state, setState] = useState<'idle' | 'uploading' | 'parsing' | 'done' | 'error'>('idle')
  const [errorMsg, setErrorMsg] = useState('')
  const [parsed, setParsed] = useState<Record<string, unknown> | null>(null)
  const [autofilled, setAutofilled] = useState<string[]>([])

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
      // Then trigger a real refetch in the background.
      qc.invalidateQueries({ queryKey: ['profile'] })
      setState('done')
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || 'Upload failed'
      setErrorMsg(detail)
      setState('error')
    }
  }

  function handleSkip() {
    navigate('/settings')
  }

  function handleContinue() {
    navigate('/settings')
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
          {state !== 'done' && (
            <>
              <div
                onClick={() => state !== 'uploading' && fileRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-12 text-center transition-colors ${
                  state === 'uploading'
                    ? 'border-accent bg-blue-50 cursor-wait'
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
                  ❌ {errorMsg}
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

          {state === 'done' && (
            <>
              <div className="text-center mb-6">
                <CheckCircle2 size={40} className="mx-auto text-success mb-3" />
                <div className="text-lg font-semibold text-text">Resume parsed</div>
                <div className="text-sm text-muted mt-1">
                  {autofilled.length > 0
                    ? `We auto-filled ${autofilled.length} field${autofilled.length === 1 ? '' : 's'}. Review and edit on the next page.`
                    : 'Your existing profile fields were preserved. Add any missing info on the next page.'}
                </div>
              </div>

              {parsed && (
                <div className="bg-gray-50 border border-border rounded-lg p-4 space-y-1.5 text-sm">
                  {parsed.full_name ? <PreviewRow label="Name" value={String(parsed.full_name)} /> : null}
                  {parsed.email ? <PreviewRow label="Email" value={String(parsed.email)} /> : null}
                  {parsed.phone ? <PreviewRow label="Phone" value={String(parsed.phone)} /> : null}
                  {parsed.city ? <PreviewRow label="City" value={String(parsed.city)} /> : null}
                  {parsed.current_title ? <PreviewRow label="Title" value={String(parsed.current_title)} /> : null}
                  {parsed.years_of_experience ? <PreviewRow label="Experience" value={`${parsed.years_of_experience} years`} /> : null}
                  {Array.isArray(parsed.skills) && parsed.skills.length > 0 && (
                    <PreviewRow label="Skills" value={`${(parsed.skills as string[]).slice(0, 8).join(', ')}${(parsed.skills as string[]).length > 8 ? `, +${(parsed.skills as string[]).length - 8} more` : ''}`} />
                  )}
                </div>
              )}

              <button
                onClick={handleContinue}
                className="w-full mt-6 bg-accent text-white rounded-lg py-3 text-sm font-medium hover:bg-blue-600 transition-colors"
              >
                Continue to Settings →
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
