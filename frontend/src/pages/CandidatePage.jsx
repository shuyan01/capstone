import React, { useState, useEffect } from 'react'
import { useNavigate, useLocation, useParams } from 'react-router-dom'
import {
  createHandoff,
  fetchHandoffs,
  fetchResumeText,
  fetchSchedule,
  scheduleInterview,
  submitFeedback,
} from '../api'
import styles from './CandidatePage.module.css'

const DIMENSIONS = [
  { key:'skill_score',      label:'Skills',      color:'#7C6FCD', bg:'#EDE9F7' },
  { key:'experience_score', label:'Experience',  color:'#4CAF82', bg:'#E8F5EF' },
  { key:'technical_score',  label:'Technical',   color:'#E09B3D', bg:'#FEF6E8' },
  { key:'culture_score',    label:'Culture fit', color:'#E07B6A', bg:'#FFEFED' },
]

function CircleScore({ score }) {
  const pct = Math.round(score * 100)
  const r = 40, circ = 2 * Math.PI * r
  const offset = circ - (pct / 100) * circ
  const color = score >= 0.55 ? '#4CAF82' : score >= 0.35 ? '#E09B3D' : '#E07B6A'
  return (
    <div className={styles.circleWrap}>
      <svg width="100" height="100" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r={r} fill="none" stroke="#EDE5D8" strokeWidth="8" />
        <circle cx="50" cy="50" r={r} fill="none" stroke={color} strokeWidth="8"
          strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
          transform="rotate(-90 50 50)"
          style={{ transition: 'stroke-dashoffset 1s cubic-bezier(0.16,1,0.3,1)' }} />
        <text x="50" y="46" textAnchor="middle" fontSize="20" fontWeight="500" fontFamily="Lora,serif" fill="#3D2B1F">{pct}%</text>
        <text x="50" y="62" textAnchor="middle" fontSize="10" fill="#8B7355">match</text>
      </svg>
    </div>
  )
}

function InsightRow({ icon, title, subtitle, variant = 'default' }) {
  const v = {
    success: { bg:'#E8F5EF', iconBg:'#4CAF82', border:'#A5D6A7' },
    warning: { bg:'#FEF6E8', iconBg:'#E09B3D', border:'#F0D9A0' },
    danger:  { bg:'#FFEBEE', iconBg:'#E07B6A', border:'#FFCDD2' },
    default: { bg:'#F5F0E8', iconBg:'#8B7355', border:'#D6CCBB' },
  }[variant]
  return (
    <div className={styles.insightRow} style={{ background: v.bg, borderColor: v.border }}>
      <div className={styles.insightIcon} style={{ background: v.iconBg }}>{icon}</div>
      <div>
        <div className={styles.insightTitle}>{title}</div>
        {subtitle && <div className={styles.insightSub}>{subtitle}</div>}
      </div>
    </div>
  )
}

export default function CandidatePage() {
  const navigate = useNavigate()
  const { state } = useLocation()
  const { resumeId } = useParams()

  const candidate = state?.candidate
  const jobQuery  = state?.jobQuery

  // ── All hooks must be declared unconditionally at the top ──
  const [activeTab,     setActiveTab]     = useState('insights')
  const [resumeText,    setResumeText]    = useState(null)
  const [resumeLoading, setResumeLoading] = useState(false)
  const [feedbackState, setFeedbackState] = useState({ status: 'idle', message: '' })
  const [scheduleItems, setScheduleItems] = useState([])
  const [handoffItems, setHandoffItems] = useState([])
  const [scheduleForm, setScheduleForm] = useState({
    interview_round: 'recruiter_screen',
    scheduled_for: '',
    interviewer_name: '',
    meeting_link: '',
  })
  const [handoffForm, setHandoffForm] = useState({
    sender_role: 'recruiter',
    recipient_role: 'hiring_manager',
    note: '',
  })
  const [scheduleState, setScheduleState] = useState({ status: 'idle', message: '' })
  const [handoffState, setHandoffState] = useState({ status: 'idle', message: '' })

  // Fetch full resume text only when Raw resume tab is first opened
  useEffect(() => {
    if (activeTab === 'resume' && resumeText === null) {
      setResumeLoading(true)
      fetchResumeText(resumeId)
        .then(data => setResumeText(data.full_text))
        .catch(() => setResumeText('Could not load resume text.'))
        .finally(() => setResumeLoading(false))
    }
  }, [activeTab])

  useEffect(() => {
    if (!resumeId) return
    fetchSchedule(resumeId).then(setScheduleItems).catch(() => {})
    fetchHandoffs(resumeId).then(setHandoffItems).catch(() => {})
  }, [resumeId])

  // ── Guard: show fallback if no candidate data ──
  if (!candidate) {
    return (
      <div className={styles.notFound}>
        <p>Candidate data not found.</p>
        <button onClick={() => navigate('/')} className={styles.backBtn}>← Back to search</button>
      </div>
    )
  }

  const {
    scores, matched_skills, missing_skills, partial_matches,
    tech_stack, soft_skills, seniority_level, total_years,
    category, explanation, complexity_level,
    education_tags = [], location_tags = [], industry_tags = [], explicit_years,
    job_titles = [], degree_subjects = [], education_level = '',
    gating_passed, gating_penalty, gating_reasons, screening_profile,
    bias_flags = [],
  } = candidate

  async function handleFeedback(feedbackLabel) {
    setFeedbackState({ status: 'loading', message: '' })
    try {
      await submitFeedback({
        resume_id: resumeId,
        job_query: jobQuery || '',
        feedback_label: feedbackLabel,
        rank_position: candidate.rank,
        composite_score: candidate.composite_score,
      })
      setFeedbackState({
        status: 'success',
        message: feedbackLabel === 'positive' ? 'Marked as helpful.' : 'Marked as not helpful.',
      })
    } catch (err) {
      setFeedbackState({ status: 'error', message: err.message })
    }
  }

  async function handleScheduleSubmit(e) {
    e.preventDefault()
    setScheduleState({ status: 'loading', message: '' })
    try {
      const created = await scheduleInterview({
        resume_id: resumeId,
        job_query: jobQuery || '',
        ...scheduleForm,
      })
      setScheduleItems(items => [created, ...items])
      setScheduleState({ status: 'success', message: 'Interview scheduled.' })
      setScheduleForm({
        interview_round: 'recruiter_screen',
        scheduled_for: '',
        interviewer_name: '',
        meeting_link: '',
      })
    } catch (err) {
      setScheduleState({ status: 'error', message: err.message })
    }
  }

  async function handleHandoffSubmit(e) {
    e.preventDefault()
    setHandoffState({ status: 'loading', message: '' })
    try {
      const created = await createHandoff({
        resume_id: resumeId,
        job_query: jobQuery || '',
        ...handoffForm,
      })
      setHandoffItems(items => [{ ...created, created_at: new Date().toISOString() }, ...items])
      setHandoffState({ status: 'success', message: 'Handoff note shared.' })
      setHandoffForm(form => ({ ...form, note: '' }))
    } catch (err) {
      setHandoffState({ status: 'error', message: err.message })
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.topBar}>
        <button
          onClick={() => navigate('/', { state: {
            restoreResults: true,
            savedResults:   state?.savedResults,
            savedQuery:     state?.savedQuery,
            savedElapsed:   state?.savedElapsed,
          }})}
          className={styles.backBtn}
        >
          ← Back to results
        </button>
        {jobQuery && (
          <div className={styles.queryPill}>
            <span className={styles.queryLabel}>Query</span>
            <span className={styles.queryText}>{jobQuery}</span>
          </div>
        )}
      </div>

      <div className={styles.content}>
        <div className={styles.leftCol}>

          {/* Profile header */}
          <div className={styles.profileCard}>
            <div className={styles.profileAvatar}>
              {resumeId.includes('_csv_') ? 'CV' : 'PD'}
            </div>
            <div>
              <div className={styles.profileName}>{resumeId}</div>
              <div className={styles.profileMeta}>
                {category}
                {total_years > 0 && ` · ${total_years} yrs exp`}
                {seniority_level && ` · ${seniority_level}`}
              </div>
            </div>
          </div>

          {/* Tab section */}
          <div className={styles.section}>
            <div className={styles.tabs}>
              <button
                className={`${styles.tab} ${activeTab === 'insights' ? styles.tabActive : ''}`}
                onClick={() => setActiveTab('insights')}
              >
                AI insights
              </button>
              <button
                className={`${styles.tab} ${activeTab === 'resume' ? styles.tabActive : ''}`}
                onClick={() => setActiveTab('resume')}
              >
                Raw resume
              </button>
            </div>

            {activeTab === 'insights' && (
              <div className={styles.insightList}>
                {bias_flags?.length > 0 && (
                  <InsightRow
                    icon="⚐"
                    title="Demographic disclosure detected"
                    subtitle={`Resume contains: ${bias_flags.join(', ')} — consider blind review to reduce bias.`}
                    variant="warning"
                  />
                )}
                {gating_reasons?.length > 0 && (
                  <InsightRow
                    icon={gating_passed ? '!' : '⚠'}
                    title={gating_passed ? 'Screening penalty applied' : 'Screening threshold not met'}
                    subtitle={`${gating_reasons.join(' · ')}${gating_penalty > 0 ? ` · penalty ${Math.round(gating_penalty * 100)} pts` : ''}`}
                    variant={gating_passed ? 'warning' : 'danger'}
                  />
                )}
                {matched_skills.length > 0 && (
                  <InsightRow icon="✓" title="Skills matched" subtitle={`Matched: ${matched_skills.join(', ')}`} variant="success" />
                )}
                {partial_matches.length > 0 && (
                  <InsightRow icon="~" title="Related skills" subtitle={`Transferable: ${partial_matches.join(', ')}`} variant="warning" />
                )}
                {missing_skills.length > 0 && (
                  <InsightRow icon="✗" title="Skills gap" subtitle={`Missing: ${missing_skills.join(', ')}`} variant="danger" />
                )}
                {tech_stack.length > 0 && (
                  <InsightRow icon="⚡" title="Tech stack identified" subtitle={tech_stack.join(', ')} variant="default" />
                )}
                {soft_skills.length > 0 && (
                  <InsightRow icon="◎" title="Soft skills" subtitle={soft_skills.join(', ')} variant="default" />
                )}
              </div>
            )}

            {activeTab === 'resume' && (
              <div className={styles.resumeText}>
                {resumeLoading ? 'Loading resume...' : (resumeText || 'Resume text not available.')}
              </div>
            )}
          </div>

          {/* Explanation */}
            <div className={styles.explanationBox}>
            <p className={styles.explanationLabel}>Explanation</p>
            <p className={styles.explanationText}>{explanation}</p>
            <p className={styles.explanationMeta}>Screening profile: {screening_profile || 'general'}</p>
            <div className={styles.feedbackBar}>
              <button
                className={styles.feedbackBtn}
                onClick={() => handleFeedback('positive')}
                disabled={feedbackState.status === 'loading'}
              >
                Helpful
              </button>
              <button
                className={styles.feedbackBtn}
                onClick={() => handleFeedback('negative')}
                disabled={feedbackState.status === 'loading'}
              >
                Not helpful
              </button>
            </div>
            {feedbackState.message && (
              <p className={`${styles.feedbackMsg} ${feedbackState.status === 'error' ? styles.feedbackError : ''}`}>
                {feedbackState.message}
              </p>
            )}
          </div>

        </div>

        <div className={styles.rightCol}>
          <div className={styles.scoreCard}>
            <CircleScore score={candidate.composite_score} />
            <div className={styles.scoreCardLabel}>Fit score</div>
          </div>

          <div className={styles.card}>
            <h3 className={styles.sectionTitle}>Score breakdown</h3>
            <div className={styles.barList}>
              {DIMENSIONS.map(({ key, label, color, bg }) => {
                const pct = Math.round((scores[key] || 0) * 100)
                return (
                  <div key={key} className={styles.barRow}>
                    <div className={styles.barHeader}>
                      <span className={styles.barLabel}>{label}</span>
                      <span className={styles.barPct} style={{ color, background: bg }}>{pct}%</span>
                    </div>
                    <div className={styles.barTrack}>
                      <div className={styles.barFill} style={{ width: `${pct}%`, background: color }} />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <div className={styles.card}>
            <h3 className={styles.sectionTitle}>Candidate profile</h3>
            <div className={styles.profileGrid}>
              <div className={styles.profileCell}>
                <span className={styles.profileCellLabel}>Years exp.</span>
                <span className={styles.profileCellVal}>{total_years > 0 ? total_years : '—'}</span>
              </div>
              <div className={styles.profileCell}>
                <span className={styles.profileCellLabel}>Explicit years</span>
                <span className={styles.profileCellVal}>{explicit_years > 0 ? explicit_years : '—'}</span>
              </div>
              <div className={styles.profileCell}>
                <span className={styles.profileCellLabel}>Seniority</span>
                <span className={styles.profileCellVal}>{seniority_level || '—'}</span>
              </div>
              <div className={styles.profileCell}>
                <span className={styles.profileCellLabel}>Category</span>
                <span className={styles.profileCellVal} style={{ fontSize: '11px' }}>{category}</span>
              </div>
              <div className={styles.profileCell}>
                <span className={styles.profileCellLabel}>Tech depth</span>
                <span className={styles.profileCellVal}>{complexity_level || '—'}</span>
              </div>
              <div className={styles.profileCell}>
                <span className={styles.profileCellLabel}>Education level</span>
                <span className={styles.profileCellVal}>{education_level || '—'}</span>
              </div>
            </div>
          </div>

          {(education_tags.length > 0 || location_tags.length > 0 || industry_tags.length > 0 || job_titles.length > 0 || degree_subjects.length > 0) && (
            <div className={styles.card}>
              <h3 className={styles.sectionTitle}>Structured metadata</h3>
              <div className={styles.metaGroup}>
                {job_titles.length > 0 && (
                  <div>
                    <div className={styles.metaLabel}>Role titles</div>
                    <div className={styles.tagWrap}>
                      {job_titles.map(t => <span key={`role-${t}`} className={styles.techTag}>{t}</span>)}
                    </div>
                  </div>
                )}
                {education_tags.length > 0 && (
                  <div>
                    <div className={styles.metaLabel}>Education</div>
                    <div className={styles.tagWrap}>
                      {education_tags.map(t => <span key={`edu-${t}`} className={styles.techTag}>{t}</span>)}
                    </div>
                  </div>
                )}
                {degree_subjects.length > 0 && (
                  <div>
                    <div className={styles.metaLabel}>Degree subjects</div>
                    <div className={styles.tagWrap}>
                      {degree_subjects.map(t => <span key={`subject-${t}`} className={styles.techTag}>{t}</span>)}
                    </div>
                  </div>
                )}
                {location_tags.length > 0 && (
                  <div>
                    <div className={styles.metaLabel}>Locations</div>
                    <div className={styles.tagWrap}>
                      {location_tags.map(t => <span key={`loc-${t}`} className={styles.techTag}>{t}</span>)}
                    </div>
                  </div>
                )}
                {industry_tags.length > 0 && (
                  <div>
                    <div className={styles.metaLabel}>Industries</div>
                    <div className={styles.tagWrap}>
                      {industry_tags.map(t => <span key={`ind-${t}`} className={styles.techTag}>{t}</span>)}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {tech_stack.length > 0 && (
            <div className={styles.card}>
              <h3 className={styles.sectionTitle}>Tech stack</h3>
              <div className={styles.tagWrap}>
                {tech_stack.map(t => (
                  <span key={t} className={styles.techTag}>{t}</span>
                ))}
              </div>
            </div>
          )}

          <div className={styles.card}>
            <h3 className={styles.sectionTitle}>Interview scheduling</h3>
            <form className={styles.formStack} onSubmit={handleScheduleSubmit}>
              <select
                className={styles.inlineInput}
                value={scheduleForm.interview_round}
                onChange={e => setScheduleForm(form => ({ ...form, interview_round: e.target.value }))}
              >
                <option value="recruiter_screen">Recruiter screen</option>
                <option value="technical_round">Technical round</option>
                <option value="manager_round">Manager round</option>
              </select>
              <input
                className={styles.inlineInput}
                type="datetime-local"
                value={scheduleForm.scheduled_for}
                onChange={e => setScheduleForm(form => ({ ...form, scheduled_for: e.target.value }))}
                required
              />
              <input
                className={styles.inlineInput}
                placeholder="Interviewer name"
                value={scheduleForm.interviewer_name}
                onChange={e => setScheduleForm(form => ({ ...form, interviewer_name: e.target.value }))}
                required
              />
              <input
                className={styles.inlineInput}
                placeholder="Meeting link (optional)"
                value={scheduleForm.meeting_link}
                onChange={e => setScheduleForm(form => ({ ...form, meeting_link: e.target.value }))}
              />
              <button className={styles.primaryBtn} type="submit" disabled={scheduleState.status === 'loading'}>
                Schedule interview
              </button>
            </form>
            {scheduleState.message && (
              <p className={`${styles.feedbackMsg} ${scheduleState.status === 'error' ? styles.feedbackError : ''}`}>
                {scheduleState.message}
              </p>
            )}
            {scheduleItems.length > 0 && (
              <div className={styles.timeline}>
                {scheduleItems.slice(0, 4).map(item => (
                  <div key={item.id} className={styles.timelineItem}>
                    <div className={styles.timelineTitle}>{item.interview_round}</div>
                    <div className={styles.timelineSub}>{item.scheduled_for} · {item.interviewer_name}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className={styles.card}>
            <h3 className={styles.sectionTitle}>Recruiter to manager handoff</h3>
            <form className={styles.formStack} onSubmit={handleHandoffSubmit}>
              <div className={styles.inlineRow}>
                <select
                  className={styles.inlineInput}
                  value={handoffForm.sender_role}
                  onChange={e => setHandoffForm(form => ({ ...form, sender_role: e.target.value }))}
                >
                  <option value="recruiter">Recruiter</option>
                  <option value="hiring_manager">Hiring manager</option>
                </select>
                <select
                  className={styles.inlineInput}
                  value={handoffForm.recipient_role}
                  onChange={e => setHandoffForm(form => ({ ...form, recipient_role: e.target.value }))}
                >
                  <option value="hiring_manager">Hiring manager</option>
                  <option value="recruiter">Recruiter</option>
                </select>
              </div>
              <textarea
                className={styles.inlineTextarea}
                placeholder="Share interview context, risks, and next-step recommendations..."
                value={handoffForm.note}
                onChange={e => setHandoffForm(form => ({ ...form, note: e.target.value }))}
                rows={4}
                required
              />
              <button className={styles.primaryBtn} type="submit" disabled={handoffState.status === 'loading'}>
                Send handoff note
              </button>
            </form>
            {handoffState.message && (
              <p className={`${styles.feedbackMsg} ${handoffState.status === 'error' ? styles.feedbackError : ''}`}>
                {handoffState.message}
              </p>
            )}
            {handoffItems.length > 0 && (
              <div className={styles.timeline}>
                {handoffItems.slice(0, 4).map(item => (
                  <div key={item.id} className={styles.timelineItem}>
                    <div className={styles.timelineTitle}>{item.sender_role} → {item.recipient_role}</div>
                    <div className={styles.timelineSub}>{item.note}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
