import React, { useState, useEffect, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { fetchAnalytics, fetchCategories, matchCandidates } from '../api'
import LoadingSpinner from '../components/LoadingSpinner'
import styles from './SearchPage.module.css'

function getScoreColor(score) {
  if (score >= 0.55) return { bg:'#E8F5EF', border:'#A5D6A7', text:'#1B5E20' }
  if (score >= 0.35) return { bg:'#FEF6E8', border:'#F0D9A0', text:'#7A5010' }
  return { bg:'#FFEBEE', border:'#FFCDD2', text:'#9B3D2E' }
}
function getScoreLabel(score) {
  if (score >= 0.55) return 'Strong match'
  if (score >= 0.35) return 'Partial match'
  return 'Weak match'
}
function getInitials(resumeId) { return resumeId.includes('_csv_') ? 'CV' : 'PD' }
const AVATAR_COLORS = [
  { bg:'#EDE9F7', color:'#4A3FA0' },
  { bg:'#E8F5EF', color:'#1E7A4A' },
  { bg:'#FEF6E8', color:'#9B6A1A' },
  { bg:'#FFEFED', color:'#9B3D2E' },
  { bg:'#E8F0FB', color:'#1A4E8C' },
]

export default function SearchPage() {
  const navigate = useNavigate()
  const [jobQuery, setJobQuery] = useState('')
  const [topK, setTopK] = useState(5)
  const [category, setCategory] = useState('')
  const [requiredSkills, setRequiredSkills] = useState('')
  const [minYears, setMinYears] = useState('')
  const [educationKeywords, setEducationKeywords] = useState('')
  const [industryKeywords, setIndustryKeywords] = useState('')
  const [locationKeywords, setLocationKeywords] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [categories, setCategories] = useState([])
  const [analytics, setAnalytics] = useState(null)
  const [loading, setLoading] = useState(false)
  const [loadingStep, setLoadingStep] = useState(0)
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)
  const [elapsed, setElapsed] = useState(null)
  const stepTimer = useRef([])
  const startTime = useRef(null)
  const location = useLocation()

  useEffect(() => { fetchCategories().then(setCategories).catch(() => {}) }, [])
  useEffect(() => { fetchAnalytics().then(setAnalytics).catch(() => {}) }, [])
  useEffect(() => {
  const saved = sessionStorage.getItem('lastResults')
  const savedQuery = sessionStorage.getItem('lastQuery')
  const savedElapsed = sessionStorage.getItem('lastElapsed')
  if (saved) {
    setResults(JSON.parse(saved))
    setJobQuery(savedQuery || '')
    setElapsed(savedElapsed || null)
  }
}, [])
  useEffect(() => {
  if (location.state?.restoreResults && location.state?.savedResults) {
    setResults(location.state.savedResults)
    setJobQuery(location.state.savedQuery || '')
    setElapsed(location.state.savedElapsed || null)
  }
}, [location.state])

  useEffect(() => {
  if (location.state?.clearResults) {
    setResults(null)
    setError(null)
    setJobQuery('')
    sessionStorage.removeItem('lastResults')
    sessionStorage.removeItem('lastQuery')
    sessionStorage.removeItem('lastElapsed')
  }
}, [location.state])

  function startAnimation() {
    setLoadingStep(0)
    stepTimer.current = [0,3000,8000,13000,20000,28000].map((d, i) => setTimeout(() => setLoadingStep(i), d))
  }
  function clearAnimation() { stepTimer.current.forEach(clearTimeout) }
  function splitCsvField(value) {
    return value
      .split(',')
      .map(v => v.trim())
      .filter(Boolean)
  }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!jobQuery.trim()) return
    setError(null); setResults(null); setLoading(true)
    startAnimation(); startTime.current = Date.now()
    try {
      const data = await matchCandidates({
        jobQuery: jobQuery.trim(),
        topK,
        filterCategory: category || null,
        requiredSkills: splitCsvField(requiredSkills),
        minYears: minYears === '' ? null : Number(minYears),
        educationKeywords: splitCsvField(educationKeywords),
        industryKeywords: splitCsvField(industryKeywords),
        locationKeywords: splitCsvField(locationKeywords),
      })
    setResults(data)
    const el = ((Date.now() - startTime.current) / 1000).toFixed(1)
    setElapsed(el)
    sessionStorage.setItem('lastResults', JSON.stringify(data))
    sessionStorage.setItem('lastQuery', jobQuery.trim())
    sessionStorage.setItem('lastElapsed', el)
    } catch (err) { setError(err.message) }
    finally {
      fetchAnalytics().then(setAnalytics).catch(() => {})
      clearAnimation()
      setLoading(false)
    }
  }

  const avgScore = results
    ? results.candidates.reduce((s, c) => s + c.composite_score, 0) / results.candidates.length
    : null

  return (
    <div className={styles.page}>
      <aside className={styles.sidebar}>
        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.field}>
            <label className={styles.label}>Job description</label>
            <textarea className={styles.textarea} placeholder="Describe the role, required skills, and experience level..." value={jobQuery} onChange={e => setJobQuery(e.target.value)} rows={7} />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Category</label>
            <select className={styles.select} value={category} onChange={e => setCategory(e.target.value)}>
              <option value="">All categories</option>
              {categories.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className={styles.advancedBox}>
            <button
              type="button"
              className={styles.advancedToggle}
              onClick={() => setShowAdvanced(v => !v)}
            >
              {showAdvanced ? 'Hide advanced filters' : 'Show advanced filters'}
            </button>
            {showAdvanced && (
              <div className={styles.advancedFields}>
                <div className={styles.field}>
                  <label className={styles.label}>Required skills</label>
                  <input
                    className={styles.input}
                    placeholder="Python, FastAPI, PostgreSQL"
                    value={requiredSkills}
                    onChange={e => setRequiredSkills(e.target.value)}
                  />
                </div>
                <div className={styles.field}>
                  <label className={styles.label}>Min years</label>
                  <input
                    type="number"
                    min={0}
                    max={50}
                    className={styles.input}
                    placeholder="3"
                    value={minYears}
                    onChange={e => setMinYears(e.target.value)}
                  />
                </div>
                <div className={styles.field}>
                  <label className={styles.label}>Education</label>
                  <input
                    className={styles.input}
                    placeholder="Computer Science, B.Tech"
                    value={educationKeywords}
                    onChange={e => setEducationKeywords(e.target.value)}
                  />
                </div>
                <div className={styles.field}>
                  <label className={styles.label}>Industry</label>
                  <input
                    className={styles.input}
                    placeholder="Fintech, Banking"
                    value={industryKeywords}
                    onChange={e => setIndustryKeywords(e.target.value)}
                  />
                </div>
                <div className={styles.field}>
                  <label className={styles.label}>Location</label>
                  <input
                    className={styles.input}
                    placeholder="Bangalore, Chennai"
                    value={locationKeywords}
                    onChange={e => setLocationKeywords(e.target.value)}
                  />
                </div>
              </div>
            )}
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Results <span className={styles.topKVal}>{topK}</span></label>
            <input type="range" min={1} max={10} step={1} value={topK} onChange={e => setTopK(Number(e.target.value))} className={styles.slider} />
            <div className={styles.ticks}><span>1</span><span>5</span><span>10</span></div>
          </div>
          <button type="submit" className={styles.btn} disabled={loading || !jobQuery.trim()}>
            {loading ? 'Searching...' : 'Find candidates'}
          </button>
        </form>
        {results && (
          <div className={styles.statsBox}>
            <div className={styles.statItem}><span className={styles.statVal}>{results.total_found}</span><span className={styles.statLabel}>found</span></div>
            <div className={styles.statDivider} />
            <div className={styles.statItem}><span className={styles.statVal}>{avgScore ? Math.round(avgScore * 100) : '—'}%</span><span className={styles.statLabel}>avg score</span></div>
            <div className={styles.statDivider} />
            <div className={styles.statItem}><span className={styles.statVal}>{elapsed}s</span><span className={styles.statLabel}>elapsed</span></div>
          </div>
        )}
        <div className={styles.legend}>
          {[{label:'Skills',color:'#7C6FCD'},{label:'Experience',color:'#4CAF82'},{label:'Technical',color:'#E09B3D'},{label:'Culture fit',color:'#E07B6A'}].map(({label,color}) => (
            <div key={label} className={styles.legendItem}>
              <span className={styles.legendDot} style={{background:color}} />
              <span>{label}</span>
            </div>
          ))}
        </div>
        {analytics && (
          <div className={styles.analyticsBox}>
            <div className={styles.analyticsTitle}>Recruiter analytics</div>
            <div className={styles.analyticsGrid}>
              <div className={styles.analyticsItem}>
                <span className={styles.analyticsValue}>{analytics.total_feedback}</span>
                <span className={styles.analyticsLabel}>feedback</span>
              </div>
              <div className={styles.analyticsItem}>
                <span className={styles.analyticsValue}>{Math.round((analytics.positive_rate || 0) * 100)}%</span>
                <span className={styles.analyticsLabel}>positive rate</span>
              </div>
              <div className={styles.analyticsItem}>
                <span className={styles.analyticsValue}>{Math.round((analytics.avg_composite_score || 0) * 100)}%</span>
                <span className={styles.analyticsLabel}>avg score</span>
              </div>
            </div>
            {analytics.top_resumes?.length > 0 && (
              <div className={styles.analyticsList}>
                <div className={styles.analyticsSubTitle}>Top reviewed resumes</div>
                {analytics.top_resumes.slice(0, 3).map(item => (
                  <div key={item.resume_id} className={styles.analyticsRow}>
                    <span>{item.resume_id}</span>
                    <span>{item.feedback_count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </aside>

      <main className={styles.main}>
        {!loading && !results && !error && (
          <div className={styles.empty}>
            <div className={styles.emptyIcon}>
              <svg width="44" height="44" viewBox="0 0 44 44" fill="none">
                <rect x="7" y="4" width="26" height="34" rx="4" stroke="currentColor" strokeWidth="1.5" fill="none" opacity="0.25"/>
                <line x1="13" y1="13" x2="30" y2="13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity="0.4"/>
                <line x1="13" y1="19" x2="27" y2="19" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity="0.4"/>
                <line x1="13" y1="25" x2="22" y2="25" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity="0.4"/>
                <circle cx="32" cy="33" r="7" fill="none" stroke="currentColor" strokeWidth="1.5" opacity="0.55"/>
                <line x1="37" y1="38" x2="41" y2="42" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" opacity="0.55"/>
              </svg>
            </div>
            <p className={styles.emptyTitle}>Ready to find candidates</p>
            <p className={styles.emptyText}>Enter a job description on the left to search the resume database using AI-powered matching.</p>
            <div className={styles.examples}>
              <p className={styles.examplesLabel}>Try an example</p>
              {['Java full stack developer with Spring Boot and MySQL experience','Data analyst with SQL and reporting skills','IT consultant with ERP and project management experience'].map(q => (
                <button key={q} className={styles.exampleBtn} onClick={() => setJobQuery(q)}>{q}</button>
              ))}
            </div>
          </div>
        )}
        {loading && <LoadingSpinner step={loadingStep} />}
        {error && !loading && (
          <div className={styles.errorBox}><strong>Something went wrong</strong><p>{error}</p></div>
        )}
        {results && !loading && (
          <div className={styles.results}>
            <div className={styles.resultsHeader}>
              <div>
                <h2 className={styles.resultsTitle}>Candidates</h2>
                <p className={styles.resultsMeta}>{results.total_found} results{category && ` · ${category}`}{elapsed && ` · ${elapsed}s`}</p>
              </div>

            </div>
            <div className={styles.cardList}>
              {results.candidates.map((c, i) => {
                const col = getScoreColor(c.composite_score)
                const av = AVATAR_COLORS[i % AVATAR_COLORS.length]
                return (
                  <div key={c.resume_id} className={styles.card} style={{animationDelay:`${i*70}ms`}}
                    onClick={() => navigate(`/candidate/${encodeURIComponent(c.resume_id)}`, {state: {candidate: c, jobQuery, restoreResults: true, savedResults: results, savedQuery: jobQuery, savedElapsed: elapsed,}})}>
                    <div className={styles.cardLeft}>
                      <div className={styles.rankBadge}>#{c.rank}</div>
                      <div className={styles.avatar} style={{background:av.bg,color:av.color}}>{getInitials(c.resume_id)}</div>
                      <div className={styles.cardInfo}>
                        <div className={styles.cardName}>{c.resume_id}</div>
                        <div className={styles.cardMeta}>{c.category}{c.total_years > 0 && ` · ${c.total_years} yrs`}{c.seniority_level && ` · ${c.seniority_level}`}</div>
                        <div className={styles.cardTags}>
                          {c.matched_skills.slice(0,3).map(s => <span key={s} className={`${styles.tag} ${styles.matched}`}>{s}</span>)}
                          {c.missing_skills.slice(0,2).map(s => <span key={s} className={`${styles.tag} ${styles.missing}`}>{s}</span>)}
                        </div>
                        {c.gating_reasons?.length > 0 && (
                          <div className={styles.gatingNote}>
                            Screening note: {c.gating_reasons[0]}
                          </div>
                        )}
                      </div>
                    </div>
                    <div className={styles.cardRight}>
                      <div className={styles.scoreBadge} style={{background:col.bg,borderColor:col.border,color:col.text}}>{(c.composite_score*100).toFixed(0)}%</div>
                      <div className={styles.scoreLabel} style={{color:col.text}}>{getScoreLabel(c.composite_score)}</div>
                      {c.gating_penalty > 0 && (
                        <div className={styles.penaltyNote}>-{Math.round(c.gating_penalty * 100)} pts gate penalty</div>
                      )}
                      <div className={styles.miniBar}>
                        {[{s:c.scores.skill_score,c:'#7C6FCD'},{s:c.scores.experience_score,c:'#4CAF82'},{s:c.scores.technical_score,c:'#E09B3D'},{s:c.scores.culture_score,c:'#E07B6A'}].map(({s,c:col},idx) => (
                          <div key={idx} className={styles.miniBarTrack}><div className={styles.miniBarFill} style={{width:`${Math.round(s*100)}%`,background:col}} /></div>
                        ))}
                      </div>
                      <span className={styles.viewLink}>View details →</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
