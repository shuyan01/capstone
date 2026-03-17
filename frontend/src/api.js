const BASE = '/api'

export async function fetchCategories() {
  const res = await fetch(`${BASE}/categories`)
  if (!res.ok) throw new Error('Failed to fetch categories')
  const data = await res.json()
  return data.categories
}

export async function matchCandidates({
  jobQuery,
  topK,
  filterCategory,
  requiredSkills,
  minYears,
  educationKeywords,
  industryKeywords,
  locationKeywords,
}) {
  const body = {
    job_query: jobQuery,
    top_k: topK,
    filter_category: filterCategory || null,
    required_skills: requiredSkills || null,
    min_years: minYears ?? null,
    education_keywords: educationKeywords || null,
    industry_keywords: industryKeywords || null,
    location_keywords: locationKeywords || null,
  }
  const res = await fetch(`${BASE}/match`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  const data = await res.json()
  if (!res.ok) {
    const detail = data.detail
    const msg = typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map(d => d.msg || JSON.stringify(d)).join(', ')
        : JSON.stringify(detail)
    const err = new Error(msg || 'Match request failed')
    err.type = res.status === 400 ? 'guardrail' : 'system'
    throw err
  }
  return data
}

export async function checkHealth() {
  const res = await fetch(`${BASE}/health`)
  if (!res.ok) throw new Error('Health check failed')
  return res.json()
}

export async function fetchResumeText(resumeId) {
  const res = await fetch(`${BASE}/resume/${encodeURIComponent(resumeId)}`)
  if (!res.ok) throw new Error('Failed to fetch resume text')
  return res.json()
}

export async function submitFeedback(payload) {
  const res = await fetch(`${BASE}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const data = await res.json()
  if (!res.ok) {
    const detail = data.detail
    throw new Error(typeof detail === 'string' ? detail : 'Failed to submit feedback')
  }
  return data
}

export async function fetchAnalytics() {
  const res = await fetch(`${BASE}/analytics`)
  if (!res.ok) throw new Error('Failed to fetch analytics')
  return res.json()
}

export async function scheduleInterview(payload) {
  const res = await fetch(`${BASE}/schedule`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Failed to schedule interview')
  return data
}

export async function fetchSchedule(resumeId) {
  const res = await fetch(`${BASE}/schedule/${encodeURIComponent(resumeId)}`)
  if (!res.ok) throw new Error('Failed to fetch schedule')
  return res.json()
}

export async function fetchAllSchedules() {
  const res = await fetch(`${BASE}/schedule`)
  if (!res.ok) throw new Error('Failed to fetch all schedules')
  return res.json()
}

export async function createHandoff(payload) {
  const res = await fetch(`${BASE}/handoff`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Failed to create handoff')
  return data
}

export async function fetchHandoffs(resumeId) {
  const res = await fetch(`${BASE}/handoff/${encodeURIComponent(resumeId)}`)
  if (!res.ok) throw new Error('Failed to fetch handoff notes')
  return res.json()
}

export async function fetchAllHandoffs() {
  const res = await fetch(`${BASE}/handoffs`)
  if (!res.ok) throw new Error('Failed to fetch all handoff notes')
  return res.json()
}
