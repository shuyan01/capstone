import React from 'react'
import styles from './LoadingSpinner.module.css'

const STEPS = [
  'Searching resumes...', 'Running skill matching...', 'Evaluating experience...',
  'Assessing technical depth...', 'Scoring culture fit...', 'Ranking candidates...',
]

export default function LoadingSpinner({ step = 0 }) {
  return (
    <div className={styles.wrap}>
      <div className={styles.dotsWrap}>
        <span className={styles.dot} style={{ animationDelay: '0ms' }} />
        <span className={styles.dot} style={{ animationDelay: '160ms' }} />
        <span className={styles.dot} style={{ animationDelay: '320ms' }} />
      </div>
      <p className={styles.label}>{STEPS[step % STEPS.length]}</p>
      <div className={styles.stepList}>
        {STEPS.map((s, i) => (
          <div key={s} className={`${styles.stepItem} ${i < step ? styles.done : ''} ${i === step ? styles.active : ''}`}>
            <span className={styles.stepDot} />
            <span className={styles.stepText}>{s}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
