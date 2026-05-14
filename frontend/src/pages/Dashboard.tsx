import React from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getTotals, getStats, runBrief, getBriefHistory, downloadBriefUrl } from '../lib/api'
import { useAgentStore } from '../store/agentStore'
import { AgentControls } from '../components/AgentControls'
import { LiveLog } from '../components/LiveLog'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend
} from 'recharts'
import { Mail, Download } from 'lucide-react'

const STAT_CARDS = [
  { key: 'queued', label: 'In Queue', color: '#34c759' },
  { key: 'approved', label: 'Approved', color: '#ff9500' },
  { key: 'applied', label: 'Applied', color: '#0071e3' },
  { key: 'skipped', label: 'Skipped', color: '#9ca3af' },
  { key: 'failed', label: 'Failed', color: '#ff3b30' },
  { key: 'response_interview', label: 'Interviews', color: '#6c2dc7' },
]

const PLATFORM_COLORS: Record<string, string> = {
  linkedin: '#0a66c2',
  naukri: '#ff7555',
  internshala: '#00c6ae',
  unstop: '#6c2dc7',
}

export default function Dashboard() {
  const { today_discovered, today_queued, today_applied, log, current_job } = useAgentStore()
  const qc = useQueryClient()
  const { data: totals } = useQuery({ queryKey: ['totals'], queryFn: getTotals, refetchInterval: 10_000 })
  const { data: chartData } = useQuery({ queryKey: ['stats'], queryFn: () => getStats(7), refetchInterval: 30_000 })
  const { data: briefs } = useQuery({
    queryKey: ['briefs'],
    queryFn: () => getBriefHistory(10),
    refetchInterval: 30_000,
  })
  const [briefBusy, setBriefBusy] = React.useState(false)

  async function handleRunBrief() {
    setBriefBusy(true)
    try {
      await runBrief(null)
      setTimeout(() => qc.invalidateQueries({ queryKey: ['briefs'] }), 2000)
    } catch (e: any) {
      alert('Failed to start brief: ' + (e?.message || e))
    } finally {
      setBriefBusy(false)
    }
  }

  const platformData = totals
    ? Object.entries(totals.by_platform ?? {}).map(([k, v]) => ({ name: k, value: v as number }))
    : []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-text">Dashboard</h1>
        <p className="text-sm text-muted mt-0.5">Your job hunt at a glance</p>
      </div>

      {/* Today's summary */}
      <div className="bg-accent/5 border border-accent/20 rounded-lg px-4 py-3 flex items-center gap-6 text-sm">
        <span className="text-muted">Today:</span>
        <span><b className="text-text">{today_discovered}</b> discovered</span>
        <span><b className="text-text">{today_queued}</b> queued</span>
        <span><b className="text-text">{today_applied}</b> applied</span>
        {current_job && (
          <span className="ml-auto text-accent truncate max-w-xs">▶ {current_job}</span>
        )}
      </div>

      {/* Agent controls */}
      <div className="bg-white border border-border rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="text-xs font-semibold text-muted uppercase tracking-wider">Agent Controls</div>
          <button
            onClick={handleRunBrief}
            disabled={briefBusy}
            className="flex items-center gap-2 px-3 py-1.5 bg-accent text-white rounded text-xs font-medium hover:bg-[#4F46E5] disabled:opacity-40 transition-colors"
            title="Discover top jobs across all sources and email you the Excel digest"
          >
            <Mail size={13} />
            {briefBusy ? 'Queued...' : 'Run Brief Now'}
          </button>
        </div>
        <AgentControls />
      </div>

      {/* Recent briefs */}
      {briefs && briefs.length > 0 && (
        <div className="bg-white border border-border rounded-lg p-4">
          <div className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">Recent Briefs</div>
          <div className="space-y-2">
            {briefs.map((b: any) => (
              <div key={b.id} className="flex items-center justify-between text-sm border-b border-border last:border-b-0 pb-2 last:pb-0">
                <div className="flex items-center gap-3">
                  <span className="text-xs text-muted w-32">
                    {b.started_at ? new Date(b.started_at).toLocaleString() : '—'}
                  </span>
                  <span><b className="text-text">{b.jobs_count}</b> jobs</span>
                  <span className="text-xs text-muted">top {Math.round(b.top_score)}</span>
                  <span className={`text-xs px-2 py-0.5 rounded ${b.email_sent ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-700'}`}>
                    {b.email_sent ? 'emailed' : (b.error_msg ? 'error' : 'pending')}
                  </span>
                  {b.error_msg && (
                    <span className="text-xs text-red-600 truncate max-w-xs" title={b.error_msg}>{b.error_msg}</span>
                  )}
                </div>
                {b.has_xlsx && (
                  <a
                    href={downloadBriefUrl(b.id)}
                    className="flex items-center gap-1 text-xs text-accent hover:underline"
                  >
                    <Download size={12} />
                    Excel
                  </a>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Stats cards */}
      <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
        {STAT_CARDS.map(({ key, label, color }) => (
          <div key={key} className="bg-white border border-border rounded-lg p-4" style={{ borderLeftColor: color, borderLeftWidth: 3 }}>
            <div className="text-2xl font-bold" style={{ color }}>{totals?.[key] ?? 0}</div>
            <div className="text-xs text-muted mt-1">{label}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Activity chart */}
        <div className="lg:col-span-2 bg-white border border-border rounded-lg p-4">
          <div className="text-xs font-semibold text-muted uppercase tracking-wider mb-4">Weekly Activity</div>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={chartData ?? []} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={d => d.slice(5)} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Area type="monotone" dataKey="queued" stroke="#34c759" fill="#34c75920" name="Queued" />
              <Area type="monotone" dataKey="applied" stroke="#0071e3" fill="#0071e320" name="Applied" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Platform breakdown */}
        <div className="bg-white border border-border rounded-lg p-4">
          <div className="text-xs font-semibold text-muted uppercase tracking-wider mb-4">By Platform</div>
          {platformData.some(d => d.value > 0) ? (
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie data={platformData} cx="50%" cy="50%" innerRadius={40} outerRadius={70} dataKey="value">
                  {platformData.map((entry) => (
                    <Cell key={entry.name} fill={PLATFORM_COLORS[entry.name] ?? '#6b7280'} />
                  ))}
                </Pie>
                <Legend iconSize={8} wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-40 text-sm text-muted">
              No data yet
            </div>
          )}
        </div>
      </div>

      {/* Live log */}
      <div className="bg-white border border-border rounded-lg p-4">
        <div className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">Live Log</div>
        <LiveLog log={log} className="h-56" />
      </div>
    </div>
  )
}
