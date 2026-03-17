import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchAnalytics } from '../api'
import styles from './AnalyticsPage.module.css'

function MiniTrend({ points }) {
  const maxValue = Math.max(...points.map(point => point.total_feedback || 0), 1)
  return (
    <div className={styles.trendChart}>
      {points.map(point => (
        <div key={point.bucket} className={styles.trendBarWrap}>
          <div
            className={styles.trendBar}
            style={{ height: `${Math.max(12, ((point.total_feedback || 0) / maxValue) * 120)}px` }}
          />
          <span className={styles.trendLabel}>{point.bucket.slice(5)}</span>
        </div>
      ))}
    </div>
  )
}

export default function AnalyticsPage() {
  const navigate = useNavigate()
  const [analytics, setAnalytics] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchAnalytics().then(setAnalytics).catch(err => setError(err.message))
  }, [])

  return (
    <div className={styles.page}>
      <div className={styles.topBar}>
        <div>
          <h1 className={styles.title}>Analytics dashboard</h1>
          <p className={styles.subtitle}>Feedback quality, shortlist accuracy, and recruiter query patterns.</p>
        </div>
      </div>

      {error && <div className={styles.errorBox}>{error}</div>}

      {analytics && (
        <div className={styles.grid}>
          <section className={styles.hero}>
            <div className={styles.metricCard}>
              <span className={styles.metricValue}>{analytics.total_feedback}</span>
              <span className={styles.metricLabel}>total feedback</span>
            </div>
            <div className={styles.metricCard}>
              <span className={styles.metricValue}>{Math.round((analytics.positive_rate || 0) * 100)}%</span>
              <span className={styles.metricLabel}>positive rate</span>
            </div>
            <div className={styles.metricCard}>
              <span className={styles.metricValue}>{Math.round((analytics.avg_composite_score || 0) * 100)}%</span>
              <span className={styles.metricLabel}>avg match score</span>
            </div>
            <div className={styles.metricCard}>
              <span className={styles.metricValue}>{analytics.negative_feedback}</span>
              <span className={styles.metricLabel}>negative feedback</span>
            </div>
          </section>

          <section className={styles.card}>
            <div className={styles.cardTitle}>Feedback trend</div>
            {analytics.feedback_trend?.length > 0
              ? <MiniTrend points={analytics.feedback_trend} />
              : <div className={styles.empty}>No feedback trend yet.</div>}
          </section>

          <section className={styles.card}>
            <div className={styles.cardTitle}>Most reviewed resumes</div>
            <div className={styles.list}>
              {analytics.top_resumes?.length > 0 ? analytics.top_resumes.map(item => (
                <div key={item.resume_id} className={styles.row}>
                  <span>{item.resume_id}</span>
                  <strong>{item.feedback_count}</strong>
                </div>
              )) : <div className={styles.empty}>No feedback records yet.</div>}
            </div>
          </section>

          <section className={styles.card}>
            <div className={styles.cardTitle}>Common recruiter queries</div>
            <div className={styles.list}>
              {analytics.common_queries?.length > 0 ? analytics.common_queries.map(item => (
                <div key={item.job_query} className={styles.queryRow}>
                  <span>{item.job_query}</span>
                  <strong>{item.usage_count}</strong>
                </div>
              )) : <div className={styles.empty}>No saved queries yet.</div>}
            </div>
          </section>

          <section className={`${styles.card} ${styles.wide}`}>
            <div className={styles.cardTitle}>Recent recruiter feedback</div>
            <div className={styles.table}>
              {analytics.recent_feedback?.length > 0 ? analytics.recent_feedback.map(item => (
                <div key={item.id} className={styles.tableRow}>
                  <span>{item.resume_id}</span>
                  <span>{item.feedback_label}</span>
                  <span>{item.rank_position || '—'}</span>
                  <span>{item.created_at.slice(0, 10)}</span>
                </div>
              )) : <div className={styles.empty}>No recent feedback yet.</div>}
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
