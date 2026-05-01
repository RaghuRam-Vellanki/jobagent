import React from 'react'

const PLATFORM_CONFIG: Record<string, { label: string; color: string }> = {
  linkedin: { label: 'LinkedIn', color: '#0a66c2' },
  naukri: { label: 'Naukri', color: '#ff7555' },
  ats: { label: 'Top Companies', color: '#7c3aed' },
}

export function PlatformBadge({ platform }: { platform: string }) {
  const cfg = PLATFORM_CONFIG[platform] ?? { label: platform, color: '#6b7280' }
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-sm text-xs font-medium text-white"
      style={{ backgroundColor: cfg.color }}
    >
      {cfg.label}
    </span>
  )
}
