import React from 'react'
import { Routes, Route } from 'react-router-dom'
import { Sidebar } from './components/Sidebar'
import { useAgentWebSocket } from './hooks/useAgent'
import Dashboard from './pages/Dashboard'
import Discovery from './pages/Discovery'
import Queue from './pages/Queue'
import Applied from './pages/Applied'
import ATS from './pages/ATS'
import Settings from './pages/Settings'

export default function App() {
  useAgentWebSocket()

  return (
    <div className="flex min-h-screen bg-bg">
      <Sidebar />
      <main className="ml-56 flex-1 p-6 max-w-6xl">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/discover" element={<Discovery />} />
          <Route path="/queue" element={<Queue />} />
          <Route path="/applied" element={<Applied />} />
          <Route path="/ats" element={<ATS />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  )
}
