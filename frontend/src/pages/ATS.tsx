import React, { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getGapReport, scoreAts, uploadResume } from '../lib/api'
import { ScoreRing } from '../components/ScoreRing'
import { Upload, RefreshCw } from 'lucide-react'

export default function ATS() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState('')
  const [jdText, setJdText] = useState('')
  const [atsResult, setAtsResult] = useState<null | {
    score: number
    matched: string[]
    missing: string[]
    suggestions: string[]
  }>(null)
  const [scoring, setScoring] = useState(false)

  const { data: report, refetch: refetchReport } = useQuery({
    queryKey: ['gap-report'],
    queryFn: getGapReport,
  })

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadMsg('')
    try {
      await uploadResume(file)
      setUploadMsg(`✅ Uploaded: ${file.name}`)
      qc.invalidateQueries({ queryKey: ['profile'] })
    } catch {
      setUploadMsg('❌ Upload failed')
    } finally {
      setUploading(false)
    }
  }

  async function handleScore() {
    if (!jdText.trim()) return
    setScoring(true)
    setAtsResult(null)
    try {
      const result = await scoreAts(jdText)
      setAtsResult(result)
    } finally {
      setScoring(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-text">ATS Score</h1>
        <p className="text-sm text-muted mt-0.5">Score your resume against any job description</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Resume upload */}
        <div className="bg-white border border-border rounded-lg p-5">
          <div className="text-xs font-semibold text-muted uppercase tracking-wider mb-4">Resume</div>
          <div
            onClick={() => fileRef.current?.click()}
            className="border-2 border-dashed border-border rounded-lg p-8 text-center cursor-pointer hover:border-accent transition-colors"
          >
            <Upload size={24} className="mx-auto text-muted mb-2" />
            <div className="text-sm font-medium text-text">Click to upload PDF resume</div>
            <div className="text-xs text-muted mt-1">PDF only, max 10MB</div>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={handleUpload}
          />
          {uploading && <div className="text-sm text-accent mt-2">Uploading...</div>}
          {uploadMsg && <div className="text-sm mt-2">{uploadMsg}</div>}
        </div>

        {/* JD scorer */}
        <div className="bg-white border border-border rounded-lg p-5">
          <div className="text-xs font-semibold text-muted uppercase tracking-wider mb-4">Score Against Job Description</div>
          <textarea
            value={jdText}
            onChange={e => setJdText(e.target.value)}
            placeholder="Paste the job description here..."
            rows={6}
            className="w-full border border-border rounded p-3 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-accent"
          />
          <button
            onClick={handleScore}
            disabled={scoring || !jdText.trim()}
            className="mt-3 flex items-center gap-2 px-4 py-2 bg-accent text-white rounded text-sm font-medium hover:bg-blue-600 disabled:opacity-40 transition-colors"
          >
            <RefreshCw size={14} className={scoring ? 'animate-spin' : ''} />
            {scoring ? 'Scoring...' : 'Score Resume'}
          </button>
        </div>
      </div>

      {/* Score result */}
      {atsResult && (
        <div className="bg-white border border-border rounded-lg p-5">
          <div className="text-xs font-semibold text-muted uppercase tracking-wider mb-4">Score Result</div>
          <div className="flex items-start gap-8">
            <ScoreRing score={atsResult.score} size={80} label="ATS Score" />
            <div className="flex-1 space-y-3">
              {atsResult.suggestions.map((s, i) => (
                <div key={i} className="text-sm text-text bg-accent/5 border border-accent/20 rounded px-3 py-2">
                  {s}
                </div>
              ))}
              <div className="grid grid-cols-2 gap-3 mt-2">
                {atsResult.matched.length > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-success mb-1">Matched ({atsResult.matched.length})</div>
                    <div className="flex flex-wrap gap-1">
                      {atsResult.matched.map(kw => (
                        <span key={kw} className="px-2 py-0.5 bg-green-50 text-green-700 border border-green-100 rounded-sm text-xs">{kw}</span>
                      ))}
                    </div>
                  </div>
                )}
                {atsResult.missing.length > 0 && (
                  <div>
                    <div className="text-xs font-semibold text-danger mb-1">Missing ({atsResult.missing.length})</div>
                    <div className="flex flex-wrap gap-1">
                      {atsResult.missing.map(kw => (
                        <span key={kw} className="px-2 py-0.5 bg-red-50 text-red-600 border border-red-100 rounded-sm text-xs">{kw}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Weekly gap report */}
      <div className="bg-white border border-border rounded-lg p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="text-xs font-semibold text-muted uppercase tracking-wider">Weekly Gap Report</div>
          <button onClick={() => refetchReport()} className="text-xs text-accent hover:underline">Refresh</button>
        </div>
        {report ? (
          <>
            <div className="text-sm text-muted mb-3">
              Analyzed <b className="text-text">{report.jobs_analyzed}</b> jobs this week. {report.suggestion}
            </div>
            <div className="space-y-2">
              {report.top_gaps.slice(0, 12).map((g: { keyword: string; count: number }) => (
                <div key={g.keyword} className="flex items-center gap-3">
                  <span className="text-xs text-text w-40 truncate font-medium">{g.keyword}</span>
                  <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-danger rounded-full"
                      style={{ width: `${(g.count / (report.top_gaps[0]?.count ?? 1)) * 100}%` }}
                    />
                  </div>
                  <span className="text-xs text-muted w-6 text-right">{g.count}</span>
                </div>
              ))}
              {report.top_gaps.length === 0 && (
                <div className="text-sm text-muted text-center py-4">
                  No gap data yet — run discovery and ATS scoring first.
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="text-sm text-muted">Loading...</div>
        )}
      </div>
    </div>
  )
}
