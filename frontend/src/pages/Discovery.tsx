import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getJobs } from '../lib/api'
import { Job } from '../lib/types'
import { AgentControls } from '../components/AgentControls'
import { PlatformBadge } from '../components/PlatformBadge'
import { StatusBadge } from '../components/StatusBadge'
import { ScoreRing } from '../components/ScoreRing'
import { useAgentStore } from '../store/agentStore'
import { LiveLog } from '../components/LiveLog'
import { ExternalLink } from 'lucide-react'

const PLATFORMS = ['all', 'linkedin', 'naukri', 'ats']

const PLATFORM_LABELS: Record<string, string> = {
  all: 'All Platforms',
  linkedin: 'LinkedIn',
  naukri: 'Naukri',
  ats: 'Top Companies',
}

export default function Discovery() {
  const [platformFilter, setPlatformFilter] = useState('all')
  const { log } = useAgentStore()

  const { data, refetch } = useQuery({
    queryKey: ['jobs', 'discovered', platformFilter],
    queryFn: () => getJobs(undefined, platformFilter === 'all' ? undefined : platformFilter),
    refetchInterval: 8_000,
  })

  const jobs = data?.jobs ?? []

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-text">Discover Jobs</h1>
        <p className="text-sm text-muted mt-0.5">Search across all platforms and score matches</p>
      </div>

      {/* Controls */}
      <div className="bg-white border border-border rounded-lg p-4">
        <div className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">Start Discovery</div>
        <AgentControls />
      </div>

      {/* Platform filter tabs */}
      <div className="flex gap-2 flex-wrap">
        {PLATFORMS.map(p => (
          <button
            key={p}
            onClick={() => setPlatformFilter(p)}
            className={`px-3 py-1.5 rounded-sm text-sm font-medium border transition-colors ${
              platformFilter === p
                ? 'bg-text text-white border-text'
                : 'bg-white text-muted border-border hover:border-text'
            }`}
          >
            {PLATFORM_LABELS[p] ?? (p.charAt(0).toUpperCase() + p.slice(1))}
            {p !== 'all' && (
              <span className="ml-1.5 text-xs opacity-70">
                {jobs.filter((j: Job) => j.platform === p).length}
              </span>
            )}
          </button>
        ))}
        <span className="ml-auto text-sm text-muted self-center">{data?.total ?? 0} total</span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Jobs table */}
        <div className="lg:col-span-2 bg-white border border-border rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-gray-50 text-xs text-muted uppercase tracking-wider">
                  <th className="px-4 py-3 text-left w-12">Score</th>
                  <th className="px-4 py-3 text-left">Job</th>
                  <th className="px-4 py-3 text-left">Platform</th>
                  <th className="px-4 py-3 text-left">Status</th>
                  <th className="px-4 py-3 text-left">Keywords</th>
                </tr>
              </thead>
              <tbody>
                {jobs.length === 0 && (
                  <tr>
                    <td colSpan={5} className="text-center py-16 text-muted text-sm">
                      No jobs discovered yet. Run discovery above.
                    </td>
                  </tr>
                )}
                {jobs.map((job: Job) => (
                  <tr key={job.job_id} className="border-b border-border hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3">
                      <ScoreRing score={job.match_score ?? 0} size={40} />
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
                      <div className="text-xs text-muted mt-0.5 truncate">{job.company} · {job.location}</div>
                    </td>
                    <td className="px-4 py-3">
                      <PlatformBadge platform={job.platform} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1 max-w-xs">
                        {(job.matched_kws ?? []).slice(0, 4).map((kw: string) => (
                          <span key={kw} className="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded-sm text-[10px]">
                            {kw}
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Live log */}
        <div className="bg-white border border-border rounded-lg p-4">
          <div className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">Live Log</div>
          <LiveLog log={log} className="h-[500px]" />
        </div>
      </div>
    </div>
  )
}
