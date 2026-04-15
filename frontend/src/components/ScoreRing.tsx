import React from 'react'

interface Props {
  score: number
  size?: number
  label?: string
}

export function ScoreRing({ score, size = 56, label }: Props) {
  const radius = (size - 8) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (score / 100) * circumference

  const color =
    score >= 75 ? '#34c759' :
    score >= 50 ? '#ff9500' :
    '#ff3b30'

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke="#e5e7eb" strokeWidth={4}
        />
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke={color} strokeWidth={4}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text
          x={size / 2} y={size / 2 + 1}
          textAnchor="middle" dominantBaseline="middle"
          fontSize={size < 50 ? 10 : 13}
          fontWeight={600}
          fill={color}
        >
          {Math.round(score)}
        </text>
      </svg>
      {label && <span className="text-[10px] text-muted font-medium">{label}</span>}
    </div>
  )
}
