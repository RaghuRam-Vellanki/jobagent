import React, { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getProfile, updateProfile, getCredentials, setCredentials } from '../lib/api'
import { Save, Eye, EyeOff } from 'lucide-react'

const PLATFORMS = ['linkedin', 'naukri', 'internshala', 'unstop']

type Tab = 'profile' | 'credentials' | 'search' | 'limits'

export default function Settings() {
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('profile')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [form, setForm] = useState<Record<string, unknown>>({})
  const [creds, setCreds] = useState<Record<string, { email: string; password: string }>>({})
  const [showPass, setShowPass] = useState<Record<string, boolean>>({})

  const { data: profile } = useQuery({ queryKey: ['profile'], queryFn: getProfile })

  useEffect(() => {
    if (profile) setForm(profile)
  }, [profile])

  // Load credentials for all platforms
  useEffect(() => {
    PLATFORMS.forEach(async p => {
      const c = await getCredentials(p)
      setCreds(prev => ({ ...prev, [p]: { email: c.email, password: '' } }))
    })
  }, [])

  function setField(key: string, value: unknown) {
    setForm(prev => ({ ...prev, [key]: value }))
  }

  async function handleSave() {
    setSaving(true)
    setSaved(false)
    try {
      await updateProfile(form)
      // Save credentials. Only send the password field when the user typed
      // a new one — otherwise we'd blank the saved password on every save,
      // since the form intentionally never echoes the stored password back.
      for (const p of PLATFORMS) {
        const c = creds[p]
        if (!c) continue
        const payload: { email?: string; password?: string } = {}
        if (c.email) payload.email = c.email
        if (c.password) payload.password = c.password
        if (Object.keys(payload).length > 0) {
          await setCredentials(p, payload)
        }
      }
      qc.invalidateQueries({ queryKey: ['profile'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } finally {
      setSaving(false)
    }
  }

  const TABS: { id: Tab; label: string }[] = [
    { id: 'profile', label: 'Profile' },
    { id: 'credentials', label: 'Credentials' },
    { id: 'search', label: 'Search Config' },
    { id: 'limits', label: 'Limits & Delays' },
  ]

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text">Settings</h1>
          <p className="text-sm text-muted mt-0.5">Profile, credentials and agent configuration</p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-accent text-white rounded text-sm font-medium hover:bg-[#4F46E5] disabled:opacity-40 transition-colors"
        >
          <Save size={14} />
          {saving ? 'Saving...' : saved ? '✅ Saved!' : 'Save All'}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-lg w-fit">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
              tab === t.id ? 'bg-white text-text shadow-sm' : 'text-muted hover:text-text'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="bg-white border border-border rounded-lg p-6 space-y-5">

        {/* Profile tab */}
        {tab === 'profile' && (
          <>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Full Name" value={form.full_name as string ?? ''} onChange={v => setField('full_name', v)} />
              <Field label="Email" value={form.email as string ?? ''} onChange={v => setField('email', v)} type="email" />
              <Field label="Phone" value={form.phone as string ?? ''} onChange={v => setField('phone', v)} />
              <Field label="City" value={form.city as string ?? ''} onChange={v => setField('city', v)} />
              <Field label="Current Title" value={form.current_title as string ?? ''} onChange={v => setField('current_title', v)} />
              <Field label="Years of Experience" value={String(form.years_of_experience ?? '')} onChange={v => setField('years_of_experience', Number(v))} type="number" />
              <Field label="Expected Salary (₹)" value={form.expected_salary as string ?? ''} onChange={v => setField('expected_salary', v)} />
              <Field label="Notice Period" value={form.notice_period as string ?? ''} onChange={v => setField('notice_period', v)} />
              <Field label="Portfolio URL" value={form.portfolio_url as string ?? ''} onChange={v => setField('portfolio_url', v)} className="col-span-2" />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted mb-1.5">Skills (comma-separated)</label>
              <textarea
                value={Array.isArray(form.skills) ? (form.skills as string[]).join(', ') : ''}
                onChange={e => setField('skills', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                rows={3}
                className="w-full border border-border rounded p-3 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-accent"
                placeholder="product manager, agile, jira, sql, figma..."
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted mb-1.5">Cover Letter Template</label>
              <textarea
                value={form.cover_letter_template as string ?? ''}
                onChange={e => setField('cover_letter_template', e.target.value)}
                rows={7}
                className="w-full border border-border rounded p-3 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-accent font-mono"
              />
            </div>
          </>
        )}

        {/* Credentials tab */}
        {tab === 'credentials' && (
          <div className="space-y-6">
            {PLATFORMS.map(p => (
              <div key={p}>
                <div className="text-sm font-semibold text-text mb-3 capitalize">{p}</div>
                <div className="grid grid-cols-2 gap-3">
                  <Field
                    label="Email"
                    value={creds[p]?.email ?? ''}
                    onChange={v => setCreds(prev => ({ ...prev, [p]: { ...prev[p], email: v } }))}
                    type="email"
                  />
                  <div className="relative">
                    <label className="block text-xs font-medium text-muted mb-1.5">Password</label>
                    <input
                      type={showPass[p] ? 'text' : 'password'}
                      value={creds[p]?.password ?? ''}
                      onChange={e => setCreds(prev => ({ ...prev, [p]: { ...prev[p], password: e.target.value } }))}
                      placeholder="Enter to update..."
                      className="w-full border border-border rounded px-3 py-2 text-sm pr-9 focus:outline-none focus:ring-1 focus:ring-accent"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPass(prev => ({ ...prev, [p]: !prev[p] }))}
                      className="absolute right-2.5 top-8 text-muted"
                    >
                      {showPass[p] ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                </div>
              </div>
            ))}
            <div className="text-xs text-muted bg-yellow-50 border border-yellow-200 rounded p-3">
              Credentials are stored locally in your SQLite database. They are never sent to any external server.
            </div>
          </div>
        )}

        {/* Search config tab */}
        {tab === 'search' && (
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-muted mb-1.5">Search Keywords (comma-separated)</label>
              <input
                value={Array.isArray(form.search_keywords) ? (form.search_keywords as string[]).join(', ') : ''}
                onChange={e => setField('search_keywords', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                className="w-full border border-border rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
                placeholder="Product Manager, APM, Associate Product Manager..."
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Field label="Location Filter" value={form.location_filter as string ?? 'India'} onChange={v => setField('location_filter', v)} />
              <div>
                <label className="block text-xs font-medium text-muted mb-1.5">Date Posted</label>
                <select
                  value={form.date_posted as string ?? 'r86400'}
                  onChange={e => setField('date_posted', e.target.value)}
                  className="w-full border border-border rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
                >
                  <option value="r3600">Last hour</option>
                  <option value="r86400">Last 24 hours</option>
                  <option value="r604800">Last week</option>
                  <option value="r2592000">Last month</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-muted mb-1.5">Match Threshold (%)</label>
                <input
                  type="number" min={0} max={100}
                  value={form.match_threshold as number ?? 60}
                  onChange={e => setField('match_threshold', Number(e.target.value))}
                  className="w-full border border-border rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>
            </div>
          </div>
        )}

        {/* Limits tab */}
        {tab === 'limits' && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <Field label="Daily Queue Limit" value={String(form.daily_queue_limit ?? 50)} onChange={v => setField('daily_queue_limit', Number(v))} type="number" />
              <Field label="Daily Apply Limit" value={String(form.daily_apply_limit ?? 25)} onChange={v => setField('daily_apply_limit', Number(v))} type="number" />
              <Field label="Min Delay (seconds)" value={String(form.delay_min ?? 4)} onChange={v => setField('delay_min', Number(v))} type="number" />
              <Field label="Max Delay (seconds)" value={String(form.delay_max ?? 10)} onChange={v => setField('delay_max', Number(v))} type="number" />
            </div>

            <div className="border-t border-border pt-5">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <div className="text-sm font-semibold text-text">Daily auto-run</div>
                  <div className="text-xs text-muted mt-0.5">
                    Run discovery + apply automatically every day at the chosen time (IST).
                  </div>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={Boolean(form.auto_run_enabled)}
                  onClick={() => setField('auto_run_enabled', !form.auto_run_enabled)}
                  className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
                    form.auto_run_enabled ? 'bg-accent' : 'bg-gray-300'
                  }`}
                >
                  <span
                    className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition-transform ${
                      form.auto_run_enabled ? 'translate-x-5' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>

              {Boolean(form.auto_run_enabled) && (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-muted mb-1.5">Run time (IST, 24h)</label>
                    <input
                      type="time"
                      value={String(form.auto_run_time || '09:00')}
                      onChange={e => setField('auto_run_time', e.target.value)}
                      className="w-full border border-border rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
                    />
                    <div className="text-xs text-muted mt-1">
                      Skipped silently if the agent is already running at that time.
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function Field({
  label, value, onChange, type = 'text', className = '',
}: {
  label: string
  value: string
  onChange: (v: string) => void
  type?: string
  className?: string
}) {
  return (
    <div className={className}>
      <label className="block text-xs font-medium text-muted mb-1.5">{label}</label>
      <input
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full border border-border rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
      />
    </div>
  )
}
