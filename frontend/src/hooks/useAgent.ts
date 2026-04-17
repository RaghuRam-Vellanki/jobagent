import { useEffect, useRef } from 'react'
import { useAgentStore } from '../store/agentStore'
import { useAuthStore } from '../store/authStore'

export function useAgentWebSocket() {
  const { setAgentState, appendLog, setConnected } = useAgentStore()
  const { token } = useAuthStore()
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!token) return
    let active = true

    function connect() {
      if (!active) return
      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${protocol}://${window.location.host}/api/agent/ws?token=${token}`)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)

      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data)
          if (msg.type === 'init' || msg.type === 'stats') {
            const { log, ...rest } = msg.state ?? {}
            setAgentState(rest)
            if (Array.isArray(log)) setAgentState({ log })
          } else if (msg.type === 'log') {
            appendLog(msg.message)
          }
        } catch (_) {}
      }

      ws.onclose = () => {
        setConnected(false)
        if (active) reconnectTimer.current = setTimeout(connect, 3000)
      }

      ws.onerror = () => ws.close()
    }

    connect()

    return () => {
      active = false
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [token, setAgentState, appendLog, setConnected])
}
