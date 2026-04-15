import { create } from 'zustand'

export interface AgentState {
  running: boolean
  phase: 'idle' | 'discovering' | 'waiting' | 'applying'
  paused: boolean
  today_discovered: number
  today_queued: number
  today_approved: number
  today_applied: number
  today_skipped: number
  today_failed: number
  current_job: string
  last_update: string
  error: string | null
  log: string[]
  connected: boolean
}

interface AgentStore extends AgentState {
  setAgentState: (state: Partial<AgentState>) => void
  appendLog: (msg: string) => void
  setConnected: (v: boolean) => void
}

export const useAgentStore = create<AgentStore>((set) => ({
  running: false,
  phase: 'idle',
  paused: false,
  today_discovered: 0,
  today_queued: 0,
  today_approved: 0,
  today_applied: 0,
  today_skipped: 0,
  today_failed: 0,
  current_job: '',
  last_update: '',
  error: null,
  log: [],
  connected: false,

  setAgentState: (newState) =>
    set((prev) => ({ ...prev, ...newState })),

  appendLog: (msg) =>
    set((prev) => ({
      log: [...prev.log.slice(-499), msg],
    })),

  setConnected: (v) => set({ connected: v }),
}))
