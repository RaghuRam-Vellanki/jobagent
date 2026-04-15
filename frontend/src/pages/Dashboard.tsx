import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { getTotals, getStats } from '../lib/api'
import { useAgentStore } from '../store/agentStore'
import { AgentControls } from '../components/AgentControls'
import { LiveLog } from '../components/LiveLog'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend
} from 'recharts'

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
  const { data: totals } = useQuery({ queryKey: ['totals'], queryFn: getTotals, refetchInterval: 10_000 })
  const { data: chartData } = useQuery({ queryKey: ['stats'], queryFn: () => getStats(7), refetchInterval: 30_000 })

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
        <div className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">Agent Controls</div>
        <AgentControls />
      </div>

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
