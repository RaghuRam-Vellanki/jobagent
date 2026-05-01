import React, { useState } from 'react'
import { Play, Pause, Square, RefreshCw } from 'lucide-react'
import { useAgentStore } from '../store/agentStore'
import { startDiscover, startApply, stopAgent, pauseAgent } from '../lib/api'
import { useQueryClient } from '@tanstack/react-query'

const PLATFORMS: Array<{ id: string; label: string }> = [
  { id: 'linkedin', label: 'LinkedIn' },
  { id: 'naukri', label: 'Naukri' },
  { id: 'ats', label: 'Top Companies' },
]

export function AgentControls() {
  const { running, phase, paused } = useAgentStore()
  const qc = useQueryClient()
  const [selected, setSelected] = useState<string[]>(['linkedin', 'naukri', 'ats'])
  const [loading, setLoading] = useState(false)

  const toggle = (p: string) =>
    setSelected(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p])

  async function handleDiscover() {
    setLoading(true)
    try {
      await startDiscover(selected)
      qc.invalidateQueries({ queryKey: ['jobs'] })
    } finally {
      setLoading(false)
    }
  }

  async function handleApply() {
    setLoading(true)
    try {
      await startApply()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Platform selector */}
      <div className="flex gap-2">
        {PLATFORMS.map(p => (
          <button
            key={p.id}
            onClick={() => toggle(p.id)}
            disabled={running}
            className={`px-3 py-1.5 rounded-sm text-xs font-medium border transition-colors ${
              selected.includes(p.id)
                ? 'bg-accent text-white border-accent'
                : 'bg-white text-muted border-border hover:border-accent'
            } disabled:opacity-40`}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="h-5 w-px bg-border" />

      {/* Action buttons */}
      {!running ? (
        <>
          <button
            onClick={handleDiscover}
            disabled={loading || selected.length === 0}
            className="flex items-center gap-2 px-4 py-2 bg-accent text-white rounded font-medium text-sm hover:bg-[#4F46E5] disabled:opacity-40 transition-colors"
          >
            <RefreshCw size={14} />
            Discover Jobs
          </button>
          <button
            onClick={handleApply}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-success text-white rounded font-medium text-sm hover:bg-green-600 disabled:opacity-40 transition-colors"
          >
            <Play size={14} />
            Apply Approved
          </button>
        </>
      ) : (
        <>
          <button
            onClick={() => pauseAgent()}
            className="flex items-center gap-2 px-4 py-2 bg-warning text-white rounded font-medium text-sm hover:bg-orange-500 transition-colors"
          >
            <Pause size={14} />
            {paused ? 'Resume' : 'Pause'}
          </button>
          <button
            onClick={() => stopAgent()}
            className="flex items-center gap-2 px-4 py-2 bg-danger text-white rounded font-medium text-sm hover:bg-red-600 transition-colors"
          >
            <Square size={14} />
            Stop
          </button>
          <span className="text-sm text-muted animate-pulse">
            {phase === 'discovering' ? '🔍 Discovering...' : phase === 'applying' ? '🚀 Applying...' : '⏸ Waiting...'}
          </span>
        </>
      )}
    </div>
  )
}
