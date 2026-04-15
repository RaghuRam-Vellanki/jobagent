import React from 'react'
import { clsx } from 'clsx'

const STATUS_STYLES: Record<string, string> = {
  QUEUED: 'bg-green-100 text-green-800',
  APPROVED: 'bg-orange-100 text-orange-800',
  APPLIED: 'bg-blue-100 text-blue-800',
  SKIPPED: 'bg-gray-100 text-gray-600',
  FAILED: 'bg-red-100 text-red-700',
  DUPLICATE: 'bg-yellow-100 text-yellow-700',
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={clsx('inline-flex px-2 py-0.5 rounded-sm text-xs font-medium', STATUS_STYLES[status] ?? 'bg-gray-100 text-gray-600')}>
      {status}
    </span>
  )
}
