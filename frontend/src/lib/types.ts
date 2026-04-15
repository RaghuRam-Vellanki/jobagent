export interface Job {
  id: number
  job_id: string
  platform: string
  title: string
  company: string
  location: string
  url: string
  match_score: number
  ats_score: number | null
  matched_kws: string[]
  ats_gaps: string[]
  status: string
  skip_reason: string | null
  notes: string | null
  response_status: string
  follow_up_date: string | null
  discovered_at: string | null
  applied_at: string | null
}
