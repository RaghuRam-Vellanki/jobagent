import axios from 'axios'

export const api = axios.create({ baseURL: '/api' })

// Attach JWT token from localStorage on every request
api.interceptors.request.use((config) => {
  try {
    const stored = localStorage.getItem('jobagent-auth')
    if (stored) {
      const { state } = JSON.parse(stored)
      if (state?.token) {
        config.headers.Authorization = `Bearer ${state.token}`
      }
    }
  } catch (_) {}
  return config
})

// Redirect to login on 401
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && window.location.pathname !== '/login') {
      localStorage.removeItem('jobagent-auth')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// Jobs
export const getJobs = (status?: string, platform?: string) =>
  api.get('/jobs', { params: { status, platform, limit: 200 } }).then(r => r.data)

export const approveJob = (jobId: string) =>
  api.post(`/jobs/${jobId}/approve`).then(r => r.data)

export const rejectJob = (jobId: string) =>
  api.post(`/jobs/${jobId}/reject`).then(r => r.data)

export const updateJob = (jobId: string, payload: Record<string, unknown>) =>
  api.patch(`/jobs/${jobId}`, payload).then(r => r.data)

// Agent
export const getAgentState = () =>
  api.get('/agent/state').then(r => r.data)

export const getAgentLog = (limit = 100) =>
  api.get('/agent/log', { params: { limit } }).then(r => r.data)

export const startDiscover = (platforms: string[]) =>
  api.post('/agent/start/discover', { platforms }).then(r => r.data)

export const startApply = () =>
  api.post('/agent/start/apply').then(r => r.data)

export const stopAgent = () =>
  api.post('/agent/stop').then(r => r.data)

export const pauseAgent = () =>
  api.post('/agent/pause').then(r => r.data)

// Profile
export const getProfile = () => api.get('/profile').then(r => r.data)
export const updateProfile = (data: Record<string, unknown>) =>
  api.put('/profile', data).then(r => r.data)
export const uploadResume = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post('/profile/resume', fd).then(r => r.data)
}
export const getCredentials = (platform: string) =>
  api.get(`/profile/credentials/${platform}`).then(r => r.data)
export const setCredentials = (platform: string, data: Record<string, string>) =>
  api.put(`/profile/credentials/${platform}`, data).then(r => r.data)

// ATS
export const scoreAts = (description: string) =>
  api.post('/ats/score', { description }).then(r => r.data)
export const getGapReport = () =>
  api.get('/ats/gap-report').then(r => r.data)

// Stats
export const getStats = (days = 7) =>
  api.get('/stats', { params: { days } }).then(r => r.data)
export const getTotals = () =>
  api.get('/stats/totals').then(r => r.data)
