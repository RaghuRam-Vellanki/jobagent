import React, { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getJobs, approveJob, rejectJob } from '../lib/api'
import { Job } from '../lib/types'
import { ScoreRing } from '../components/ScoreRing'
import { PlatformBadge } from '../components/PlatformBadge'
import { Check, X, ExternalLink } from 'lucide-react'

export default function Queue() {
  const qc = useQueryClient()
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({})

  const { data } = useQuery({
    queryKey: ['jobs', 'queue'],
    queryFn: () => getJobs('QUEUED'),
    refetchInterval: 6_000,
  })

  const jobs = data?.jobs ?? []

  async function handleApprove(jobId: string) {
    setActionLoading(prev => ({ ...prev, [jobId]: true }))
    await approveJob(jobId)
    qc.invalidateQueries({ queryKey: ['jobs'] })
    setActionLoading(prev => ({ ...prev, [jobId]: false }))
  }

  async function handleReject(jobId: string) {
    setActionLoading(prev => ({ ...prev, [jobId]: true }))
    await rejectJob(jobId)
    qc.invalidateQueries({ queryKey: ['jobs'] })
    setActionLoading(prev => ({ ...prev, [jobId]: false }))
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text">Review Queue</h1>
          <p className="text-sm text-muted mt-0.5">Approve jobs to apply, reject to skip</p>
        </div>
        <div className="text-sm text-muted">
          <span className="font-semibold text-text">{jobs.length}</span> pending review
        </div>
      </div>

      {jobs.length === 0 && (
        <div className="bg-white border border-border rounded-lg p-16 text-center">
          <div className="text-3xl mb-3">📭</div>
          <div className="font-medium text-text">Queue is empty</div>
          <div className="text-sm text-muted mt-1">Run discovery to find matching jobs</div>
        </div>
      )}

      <div className="grid gap-3">
        {jobs.map((job: Job) => (
          <div
            key={job.job_id}
            className="bg-white border border-border rounded-lg p-4 flex items-start gap-4 hover:border-gray-300 transition-colors"
          >
            <ScoreRing score={job.match_score ?? 0} size={52} label="match" />

            <div className="flex-1 min-w-0">
              <div className="flex items-start gap-2 flex-wrap">
                <a
                  href={job.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-semibold text-text hover:text-accent flex items-center gap-1 group"
                >
                  {job.title}
                  <ExternalLink size={12} className="opacity-0 group-hover:opacity-100" />
                </a>
                <PlatformBadge platform={job.platform} />
              </div>
              <div className="text-sm text-muted mt-0.5">{job.company} · {job.location}</div>

              {/* Matched keywords */}
              <div className="flex flex-wrap gap-1.5 mt-2">
                {(job.matched_kws ?? []).slice(0, 6).map((kw: string) => (
                  <span key={kw} className="px-2 py-0.5 bg-green-50 text-green-700 rounded-sm text-xs border border-green-100">
                    {kw}
                  </span>
                ))}
              </div>

              {/* ATS gaps */}
              {(job.ats_gaps ?? []).length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {(job.ats_gaps ?? []).slice(0, 4).map((kw: string) => (
                    <span key={kw} className="px-2 py-0.5 bg-red-50 text-red-600 rounded-sm text-xs border border-red-100">
                      missing: {kw}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="flex gap-2 flex-shrink-0">
              <button
                onClick={() => handleApprove(job.job_id)}
                disabled={actionLoading[job.job_id]}
                className="flex items-center gap-1.5 px-3 py-2 bg-success text-white rounded text-sm font-medium hover:bg-green-600 disabled:opacity-50 transition-colors"
              >
                <Check size={14} />
                Apply
              </button>
              <button
                onClick={() => handleReject(job.job_id)}
                disabled={actionLoading[job.job_id]}
                className="flex items-center gap-1.5 px-3 py-2 bg-gray-100 text-gray-700 rounded text-sm font-medium hover:bg-gray-200 disabled:opacity-50 transition-colors"
              >
                <X size={14} />
                Skip
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
