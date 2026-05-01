import React, { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getJobs, updateJob } from '../lib/api'
import { Job } from '../lib/types'
import { PlatformBadge } from '../components/PlatformBadge'
import { ScoreRing } from '../components/ScoreRing'
import { ExternalLink, Download } from 'lucide-react'

const RESPONSE_OPTIONS = [
  { value: 'no_response', label: 'No Response', color: 'bg-gray-100 text-gray-600' },
  { value: 'viewed', label: 'Viewed', color: 'bg-blue-100 text-blue-700' },
  { value: 'interview', label: 'Interview 🎉', color: 'bg-purple-100 text-purple-700' },
  { value: 'rejected', label: 'Rejected', color: 'bg-red-100 text-red-600' },
  { value: 'offer', label: 'Offer 🏆', color: 'bg-green-100 text-green-700' },
]

type ResponseStatus = 'no_response' | 'viewed' | 'interview' | 'rejected' | 'offer'

export default function Applied() {
  const qc = useQueryClient()
  const [filter, setFilter] = useState<string>('all')

  const { data } = useQuery({
    queryKey: ['jobs', 'applied'],
    queryFn: () => getJobs('APPLIED'),
    refetchInterval: 15_000,
  })

  const jobs: Job[] = (data?.jobs ?? []).filter((j: Job) =>
    filter === 'all' ? true : j.response_status === filter
  )

  async function handleStatus(jobId: string, status: ResponseStatus) {
    await updateJob(jobId, { response_status: status })
    qc.invalidateQueries({ queryKey: ['jobs', 'applied'] })
  }

  const counts = (data?.jobs ?? []).reduce((acc: Record<string, number>, j: Job) => {
    acc[j.response_status] = (acc[j.response_status] ?? 0) + 1
    return acc
  }, {})

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text">Applied Jobs</h1>
          <p className="text-sm text-muted mt-0.5">Track responses and interview progress</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-sm text-muted">
            <span className="font-semibold text-text">{data?.total ?? 0}</span> total applied
          </div>
          <a
            href="/api/jobs/export.csv?status=APPLIED"
            download
            onClick={(e) => {
              const t = localStorage.getItem('jobagent-auth')
              const token = t ? JSON.parse(t).state?.token : null
              if (!token) return
              e.preventDefault()
              fetch('/api/jobs/export.csv?status=APPLIED', {
                headers: { Authorization: `Bearer ${token}` },
              })
                .then(r => r.blob())
                .then(blob => {
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = `jobagent-export-${new Date().toISOString().slice(0,10)}.csv`
                  a.click()
                  URL.revokeObjectURL(url)
                })
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-border text-text rounded text-sm hover:border-accent hover:text-accent transition-colors"
          >
            <Download size={14} />
            Export CSV
          </a>
        </div>
      </div>

      {/* Kanban summary */}
      <div className="grid grid-cols-5 gap-3">
        {RESPONSE_OPTIONS.map(opt => (
          <button
            key={opt.value}
            onClick={() => setFilter(filter === opt.value ? 'all' : opt.value)}
            className={`rounded-lg p-3 border text-left transition-all ${
              filter === opt.value ? 'border-accent ring-1 ring-accent' : 'border-border bg-white'
            }`}
          >
            <div className="text-xl font-bold text-text">{counts[opt.value] ?? 0}</div>
            <div className={`text-xs font-medium mt-1 px-1.5 py-0.5 rounded-sm inline-block ${opt.color}`}>
              {opt.label}
            </div>
          </button>
        ))}
      </div>

      {/* Jobs list */}
      {jobs.length === 0 && (
        <div className="bg-white border border-border rounded-lg p-16 text-center">
          <div className="text-3xl mb-3">📋</div>
          <div className="font-medium text-text">No applications yet</div>
          <div className="text-sm text-muted mt-1">Approve jobs in the Queue and run Apply</div>
        </div>
      )}

      <div className="bg-white border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-gray-50 text-xs text-muted uppercase tracking-wider">
              <th className="px-4 py-3 text-left w-12">Score</th>
              <th className="px-4 py-3 text-left">Job</th>
              <th className="px-4 py-3 text-left">Platform</th>
              <th className="px-4 py-3 text-left">Applied</th>
              <th className="px-4 py-3 text-left">Response</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job: Job) => {
              const opt = RESPONSE_OPTIONS.find(o => o.value === job.response_status) ?? RESPONSE_OPTIONS[0]
              return (
                <tr key={job.job_id} className="border-b border-border hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <ScoreRing score={job.match_score ?? 0} size={38} />
                  </td>
                  <td className="px-4 py-3 max-w-xs">
                    <a
                      href={job.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-text hover:text-accent flex items-center gap-1 group"
                    >
                      <span className="truncate">{job.title}</span>
                      <ExternalLink size={11} className="opacity-0 group-hover:opacity-100 flex-shrink-0" />
                    </a>
                    <div className="text-xs text-muted mt-0.5">{job.company} · {job.location}</div>
                  </td>
                  <td className="px-4 py-3">
                    <PlatformBadge platform={job.platform} />
                  </td>
                  <td className="px-4 py-3 text-xs text-muted">
                    {job.applied_at ? new Date(job.applied_at).toLocaleDateString() : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <select
                      value={job.response_status ?? 'no_response'}
                      onChange={e => handleStatus(job.job_id, e.target.value as ResponseStatus)}
                      className="text-xs border border-border rounded px-2 py-1 bg-white focus:outline-none focus:ring-1 focus:ring-accent"
                    >
                      {RESPONSE_OPTIONS.map(o => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
