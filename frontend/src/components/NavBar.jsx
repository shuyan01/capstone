import React from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import styles from './NavBar.module.css'

const NAV_ITEMS = [
  { label: 'Search',    path: '/' },
  { label: 'Analytics', path: '/analytics' },
  { label: 'Recruiter', path: '/recruiter' },
]

export default function NavBar() {
  const navigate = useNavigate()
  const { pathname } = useLocation()

  return (
    <nav className={styles.bar}>
      <div className={styles.brand} onClick={() => navigate('/', { state: { clearResults: true } })}>
        <span className={styles.brandIcon}>R</span>
        <span className={styles.brandName}>Resume Matcher</span>
      </div>
      <div className={styles.links}>
        {NAV_ITEMS.map(({ label, path }) => {
          const active = path === '/' ? pathname === '/' : pathname.startsWith(path)
          return (
            <button
              key={path}
              className={`${styles.link} ${active ? styles.linkActive : ''}`}
              onClick={() => navigate(path, path === '/' ? { state: { clearResults: true } } : {})}
            >
              {label}
            </button>
          )
        })}
      </div>
    </nav>
  )
}
