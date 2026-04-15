import React from 'react'
import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Search, Inbox, CheckSquare, BarChart2, Settings, Wifi, WifiOff } from 'lucide-react'
import { clsx } from 'clsx'
import { useAgentStore } from '../store/agentStore'

const NAV = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/discover', icon: Search, label: 'Discover' },
  { to: '/queue', icon: Inbox, label: 'Queue' },
  { to: '/applied', icon: CheckSquare, label: 'Applied' },
  { to: '/ats', icon: BarChart2, label: 'ATS Score' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export function Sidebar() {
  const { connected, running, phase } = useAgentStore()

  return (
    <nav className="fixed left-0 top-0 h-screen w-56 bg-white border-r border-border flex flex-col z-10">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-accent rounded flex items-center justify-center">
            <span className="text-white font-bold text-sm">JA</span>
          </div>
          <div>
            <div className="font-semibold text-sm text-text leading-tight">JobAgent</div>
            <div className="text-[10px] text-muted">LazyApply v2</div>
          </div>
        </div>
      </div>

      {/* Nav links */}
      <div className="flex-1 px-3 py-4 space-y-1">
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-3 py-2 rounded text-sm font-medium transition-colors',
                isActive
                  ? 'bg-accent/10 text-accent'
                  : 'text-muted hover:bg-gray-100 hover:text-text'
              )
            }
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </div>

      {/* Status footer */}
      <div className="px-4 py-4 border-t border-border">
        <div className="flex items-center gap-2 text-xs">
          {connected ? (
            <Wifi size={12} className="text-success" />
          ) : (
            <WifiOff size={12} className="text-danger" />
          )}
          <span className={connected ? 'text-success' : 'text-danger'}>
            {connected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
        {running && (
          <div className="mt-1 flex items-center gap-1.5 text-xs text-warning">
            <span className="w-1.5 h-1.5 rounded-full bg-warning animate-pulse" />
            {phase}
          </div>
        )}
      </div>
    </nav>
  )
}
