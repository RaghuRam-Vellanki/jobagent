import React from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Sidebar } from './components/Sidebar'
import { useAgentWebSocket } from './hooks/useAgent'
import { useAuthStore } from './store/authStore'
import Dashboard from './pages/Dashboard'
import Discovery from './pages/Discovery'
import Queue from './pages/Queue'
import Applied from './pages/Applied'
import ATS from './pages/ATS'
import Settings from './pages/Settings'
import Login from './pages/Login'
import Register from './pages/Register'

function ProtectedApp() {
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
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  const { token } = useAuthStore()

  return (
    <Routes>
      <Route path="/login" element={token ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/register" element={token ? <Navigate to="/" replace /> : <Register />} />
      <Route path="/*" element={token ? <ProtectedApp /> : <Navigate to="/login" replace />} />
    </Routes>
  )
}
