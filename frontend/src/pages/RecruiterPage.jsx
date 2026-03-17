import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchAnalytics, fetchAllSchedules, fetchAllHandoffs } from '../api'
import styles from './RecruiterPage.module.css'

export default function RecruiterPage() {
  const navigate = useNavigate()
  const [analytics, setAnalytics] = useState(null)
  const [allSchedules, setAllSchedules] = useState([])
  const [allHandoffs, setAllHandoffs] = useState([])
  const [error, setError] = useState(null)
  const [expandedCandidate, setExpandedCandidate] = useState(null)
  const [pipelineSearch, setPipelineSearch] = useState('')
  const [pipelinePage, setPipelinePage] = useState(0)
  const PIPELINE_PAGE_SIZE = 10

  useEffect(() => {
    fetchAnalytics().then(setAnalytics).catch(err => setError(err.message))
    fetchAllSchedules().then(setAllSchedules).catch(() => {})
    fetchAllHandoffs().then(setAllHandoffs).catch(() => {})
  }, [])

  // Build per-candidate map
  const candidateMap = {}
  allSchedules.forEach(s => {
    if (!candidateMap[s.resume_id]) candidateMap[s.resume_id] = { interviews: [], handoffs: [] }
    candidateMap[s.resume_id].interviews.push(s)
  })
  allHandoffs.forEach(h => {
    if (!candidateMap[h.resume_id]) candidateMap[h.resume_id] = { interviews: [], handoffs: [] }
    candidateMap[h.resume_id].handoffs.push(h)
  })
  const allEntries = Object.entries(candidateMap)
  const filtered = pipelineSearch.trim()
    ? allEntries.filter(([id]) => id.toLowerCase().includes(pipelineSearch.trim().toLowerCase()))
    : allEntries
  const totalPages = Math.ceil(filtered.length / PIPELINE_PAGE_SIZE)
  const page = Math.min(pipelinePage, Math.max(0, totalPages - 1))
  const pageEntries = filtered.slice(page * PIPELINE_PAGE_SIZE, (page + 1) * PIPELINE_PAGE_SIZE)

  const totalInterviews = analytics?.interviews_summary?.reduce((s, i) => s + (i.total_count || 0), 0) || 0
  const totalHandoffs = analytics?.handoff_summary?.reduce((s, i) => s + (i.total_count || 0), 0) || 0

  return (
    <div className={styles.page}>
      <div className={styles.topBar}>
        <div>
          <h1 className={styles.title}>Recruiter workspace</h1>
          <p className={styles.subtitle}>Interview scheduling, handoff tracking, and candidate pipeline.</p>
        </div>
      </div>

      {error && <div className={styles.errorBox}>{error}</div>}

      {/* Summary metrics */}
      <div className={styles.hero}>
        <div className={styles.metricCard}>
          <span className={styles.metricValue}>{totalInterviews}</span>
          <span className={styles.metricLabel}>scheduled interviews</span>
        </div>
        <div className={styles.metricCard}>
          <span className={styles.metricValue}>{totalHandoffs}</span>
          <span className={styles.metricLabel}>handoffs issued</span>
        </div>
        <div className={styles.metricCard}>
          <span className={styles.metricValue}>{allEntries.length}</span>
          <span className={styles.metricLabel}>candidates in pipeline</span>
        </div>
        <div className={styles.metricCard}>
          <span className={styles.metricValue}>{analytics?.interviews_summary?.length || 0}</span>
          <span className={styles.metricLabel}>interview rounds active</span>
        </div>
      </div>

      <div className={styles.grid}>
        {/* Interview pipeline summary */}
        <section className={styles.card}>
          <div className={styles.cardTitle}>Interview pipeline</div>
          <div className={styles.list}>
            {analytics?.interviews_summary?.length > 0 ? analytics.interviews_summary.map(item => (
              <div key={item.interview_round} className={styles.row}>
                <span>{item.interview_round}</span>
                <strong>{item.total_count}</strong>
              </div>
            )) : <div className={styles.empty}>No interview schedules yet.</div>}
          </div>
        </section>

        {/* Handoff recipients summary */}
        <section className={styles.card}>
          <div className={styles.cardTitle}>Handoff recipients</div>
          <div className={styles.list}>
            {analytics?.handoff_summary?.length > 0 ? analytics.handoff_summary.map(item => (
              <div key={item.recipient_role} className={styles.row}>
                <span>{item.recipient_role}</span>
                <strong>{item.total_count}</strong>
              </div>
            )) : <div className={styles.empty}>No handoff notes yet.</div>}
          </div>
        </section>

        {/* Candidate pipeline unified view */}
        <section className={`${styles.card} ${styles.wide}`}>
          <div className={styles.pipelineHeader}>
            <div className={styles.cardTitle} style={{ marginBottom: 0 }}>Candidate pipeline — unified view</div>
            <input
              className={styles.pipelineSearch}
              placeholder="Search candidate ID…"
              value={pipelineSearch}
              onChange={e => { setPipelineSearch(e.target.value); setPipelinePage(0) }}
            />
            <span className={styles.pipelineCount}>{filtered.length} candidate{filtered.length !== 1 ? 's' : ''}</span>
          </div>

          {allEntries.length === 0 ? (
            <div className={styles.empty}>No candidates in pipeline yet. Schedule an interview or add a handoff note from a candidate's page.</div>
          ) : (
            <>
              <div className={styles.pipelineList}>
                {pageEntries.length > 0 ? pageEntries.map(([resumeId, { interviews, handoffs }]) => {
                  const isOpen = expandedCandidate === resumeId
                  return (
                    <div key={resumeId} className={styles.pipelineCandidate}>
                      <div
                        className={styles.pipelineCandidateHeader}
                        onClick={() => setExpandedCandidate(isOpen ? null : resumeId)}
                      >
                        <span className={styles.pipelineCandidateId}>{resumeId}</span>
                        <span className={styles.pipelineCandidateMeta}>
                          {interviews.length > 0 && <span className={styles.pipelineTag}>{interviews.length} interview{interviews.length > 1 ? 's' : ''}</span>}
                          {handoffs.length > 0 && <span className={`${styles.pipelineTag} ${styles.pipelineTagHandoff}`}>{handoffs.length} handoff{handoffs.length > 1 ? 's' : ''}</span>}
                          <span className={styles.chevron}>{isOpen ? '▲' : '▼'}</span>
                        </span>
                      </div>
                      {isOpen && (
                        <div className={styles.pipelineTimeline}>
                          {interviews.map(s => (
                            <div key={`s-${s.id}`} className={styles.pipelineEvent}>
                              <div className={styles.pipelineEventDot} style={{ background: '#7C6FCD' }} />
                              <div className={styles.pipelineEventBody}>
                                <div className={styles.pipelineEventTitle}>{s.interview_round}</div>
                                <div className={styles.pipelineEventMeta}>
                                  {s.scheduled_for} · {s.interviewer_name}
                                  {s.meeting_link && <> · <a href={s.meeting_link} target="_blank" rel="noreferrer" className={styles.link}>Join</a></>}
                                </div>
                                {s.job_query && <div className={styles.pipelineEventQuery}>{s.job_query}</div>}
                              </div>
                              <span className={`${styles.badge} ${styles['badge_' + s.status]}`}>{s.status}</span>
                            </div>
                          ))}
                          {handoffs.map(h => (
                            <div key={`h-${h.id}`} className={styles.pipelineEvent}>
                              <div className={styles.pipelineEventDot} style={{ background: '#E09B3D' }} />
                              <div className={styles.pipelineEventBody}>
                                <div className={styles.pipelineEventTitle}>{h.sender_role} → {h.recipient_role}</div>
                                <div className={styles.pipelineEventMeta}>{h.created_at?.slice(0, 16)}</div>
                                <div className={styles.pipelineEventNote}>{h.note}</div>
                                {h.job_query && <div className={styles.pipelineEventQuery}>{h.job_query}</div>}
                              </div>
                              <span className={styles.badge} style={{ background: '#FEF6E8', color: '#E09B3D' }}>handoff</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                }) : <div className={styles.empty}>No candidates match your search.</div>}
              </div>
              {totalPages > 1 && (
                <div className={styles.pager}>
                  <button className={styles.pagerBtn} disabled={page === 0} onClick={() => setPipelinePage(p => p - 1)}>← Prev</button>
                  <span className={styles.pagerInfo}>{page + 1} / {totalPages}</span>
                  <button className={styles.pagerBtn} disabled={page >= totalPages - 1} onClick={() => setPipelinePage(p => p + 1)}>Next →</button>
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  )
}
