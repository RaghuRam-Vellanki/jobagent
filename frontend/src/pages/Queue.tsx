import React, { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getJobs, approveJob, rejectJob, approveAll, startApply, applyOneJob } from '../lib/api'
import { Job } from '../lib/types'
import { ScoreRing } from '../components/ScoreRing'
import { PlatformBadge } from '../components/PlatformBadge'
import { Check, X, ExternalLink, CheckCheck, Send } from 'lucide-react'
import { useAgentStore } from '../store/agentStore'

export default function Queue() {
  const qc = useQueryClient()
  const phase = useAgentStore(s => s.phase)
  const running = useAgentStore(s => s.running)
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({})
  const [bulkMin, setBulkMin] = useState<number>(60)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [bulkMsg, setBulkMsg] = useState<string>('')
  const [applyBusy, setApplyBusy] = useState(false)

  const { data } = useQuery({
    queryKey: ['jobs', 'queue'],
    queryFn: () => getJobs('QUEUED'),
    refetchInterval: 6_000,
  })
  const { data: approvedData } = useQuery({
    queryKey: ['jobs', 'approved'],
    queryFn: () => getJobs('APPROVED'),
    refetchInterval: 6_000,
  })

  const jobs = data?.jobs ?? []
  const approvedCount = approvedData?.total ?? 0
  const eligible = jobs.filter((j: Job) => (j.match_score ?? 0) >= bulkMin).length

  async function handleApplyApproved() {
    if (applyBusy || approvedCount === 0) return
    setApplyBusy(true)
    try {
      await startApply()
    } finally {
      // The agent runs async in the backend; clear our local "starting" lock
      // after a moment. The Live Log on the Dashboard shows real progress.
      setTimeout(() => setApplyBusy(false), 2000)
    }
  }

  async function handleBulkApprove() {
    if (!eligible) return
    setBulkBusy(true)
    try {
      const res = await approveAll(bulkMin)
      const approved = res.approved ?? 0
      qc.invalidateQueries({ queryKey: ['jobs'] })

      // E2-S7: auto-trigger apply if the agent is idle. If it's mid-discovery
      // or already applying, the user must wait for that phase to finish — we
      // don't preempt it (the apply phase will see APPROVED jobs on its next
      // run anyway).
      if (approved > 0 && !running && phase === 'idle') {
        try {
          await startApply()
          setBulkMsg(`Approved ${approved} — applying now…`)
        } catch (e: any) {
          setBulkMsg(`Approved ${approved} — couldn't auto-start apply (${e?.message || 'unknown'})`)
        }
      } else if (approved > 0 && (running || phase !== 'idle')) {
        setBulkMsg(`Approved ${approved} — agent busy, will apply after current run`)
      } else {
        setBulkMsg(`Approved ${approved} job${approved === 1 ? '' : 's'} (≥ ${bulkMin})`)
      }
      setTimeout(() => setBulkMsg(''), 5000)
    } finally {
      setBulkBusy(false)
    }
  }

  async function handleApprove(jobId: string, numericId: number) {
    setActionLoading(prev => ({ ...prev, [jobId]: true }))
    try {
      await approveJob(jobId)
      qc.invalidateQueries({ queryKey: ['jobs'] })

      // E2-S8: kick off apply for THIS job immediately when agent is idle.
      // The visible browser opens, follows external redirects if needed, runs
      // the universal filler, and stops at the review step.
      if (!running && phase === 'idle') {
        try {
          await applyOneJob(numericId)
          setBulkMsg('Applying now — watch the live log on the Dashboard')
          setTimeout(() => setBulkMsg(''), 5000)
        } catch (e) {
          // approve still succeeded; surface but don't block
          console.warn('apply-one failed', e)
        }
      }
    } finally {
      setActionLoading(prev => ({ ...prev, [jobId]: false }))
    }
  }

  async function handleReject(jobId: string) {
    setActionLoading(prev => ({ ...prev, [jobId]: true }))
    await rejectJob(jobId)
    qc.invalidateQueries({ queryKey: ['jobs'] })
    setActionLoading(prev => ({ ...prev, [jobId]: false }))
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text">Review Queue</h1>
          <p className="text-sm text-muted mt-0.5">Approve jobs you want to apply to. Click 'Apply now' above when ready.</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-white border border-border rounded-lg px-2 py-1.5">
            <label className="text-xs text-muted">Approve all ≥</label>
            <input
              type="number"
              min={0}
              max={100}
              value={bulkMin}
              onChange={e => setBulkMin(Number(e.target.value) || 0)}
              className="w-14 border border-border rounded px-2 py-1 text-sm text-center focus:outline-none focus:ring-1 focus:ring-accent"
            />
            <button
              onClick={handleBulkApprove}
              disabled={bulkBusy || eligible === 0}
              className="flex items-center gap-1 px-3 py-1 bg-success text-white rounded text-sm font-medium hover:bg-green-600 disabled:opacity-50 transition-colors"
              title={eligible === 0 ? 'No jobs at or above this score' : `Will approve ${eligible} job(s)`}
            >
              <CheckCheck size={14} />
              {bulkBusy ? '...' : `Approve ${eligible}`}
            </button>
          </div>
          <div className="text-sm text-muted">
            <span className="font-semibold text-text">{jobs.length}</span> pending
          </div>
        </div>
      </div>
      {bulkMsg && (
        <div className="text-sm text-success bg-green-50 border border-green-100 rounded px-3 py-2">
          {bulkMsg}
        </div>
      )}

      {approvedCount > 0 && (
        <div className="flex items-center justify-between gap-3 bg-blue-50 border border-blue-100 rounded-lg px-4 py-3">
          <div className="text-sm">
            <span className="font-semibold text-text">{approvedCount}</span>
            <span className="text-muted"> job{approvedCount === 1 ? '' : 's'} approved and waiting to apply.</span>
          </div>
          <button
            onClick={handleApplyApproved}
            disabled={applyBusy}
            className="flex items-center gap-1.5 px-4 py-2 bg-accent text-white rounded text-sm font-medium hover:bg-[#4F46E5] disabled:opacity-50 transition-colors"
          >
            <Send size={14} />
            {applyBusy ? 'Starting…' : `Apply ${approvedCount} now`}
          </button>
        </div>
      )}

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
                onClick={() => handleApprove(job.job_id, job.id)}
                disabled={actionLoading[job.job_id]}
                className="flex items-center gap-1.5 px-3 py-2 bg-success text-white rounded text-sm font-medium hover:bg-green-600 disabled:opacity-50 transition-colors"
                title="Add to the approved list. Click 'Apply N now' above to actually submit."
              >
                <Check size={14} />
                Approve
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
