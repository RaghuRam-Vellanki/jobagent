import React, { useEffect, useRef } from 'react'
import { clsx } from 'clsx'

interface Props {
  log: string[]
  className?: string
}

function lineColor(msg: string): string {
  if (msg.includes('✅') || msg.includes('Applied') || msg.includes('Queued')) return 'text-green-600'
  if (msg.includes('❌') || msg.includes('Failed') || msg.includes('Error') || msg.includes('💥')) return 'text-red-500'
  if (msg.includes('⏭') || msg.includes('Skipped')) return 'text-gray-400'
  if (msg.includes('🚀') || msg.includes('Starting')) return 'text-accent font-medium'
  if (msg.includes('⚠') || msg.includes('Warning')) return 'text-yellow-600'
  return 'text-gray-600'
}

export function LiveLog({ log, className }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [log.length])

  return (
    <div className={clsx('overflow-y-auto font-mono text-xs leading-5 bg-gray-50 rounded-lg p-3', className)}>
      {log.length === 0 && (
        <p className="text-muted text-center mt-8">Agent log will appear here...</p>
      )}
      {log.map((line, i) => (
        <div key={i} className={lineColor(line)}>
          {line}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
