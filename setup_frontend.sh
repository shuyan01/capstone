#!/bin/bash
# ─────────────────────────────────────────────────────────────
# Frontend Setup Script
# Run from: ai_resume_matching_system/
# Usage: bash setup_frontend.sh
# ─────────────────────────────────────────────────────────────

echo "Setting up frontend..."

# Create folder structure
mkdir -p frontend/src/pages
mkdir -p frontend/src/components
mkdir -p frontend/public

# ── package.json ──────────────────────────────────────────────
cat > frontend/package.json << 'EOF'
{
  "name": "resume-matcher-ui",
  "private": true,
  "version": "0.2.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.2"
  },
  "devDependencies": {
    "@types/react": "^18.3.1",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.1",
    "vite": "^5.4.2"
  }
}
EOF

# ── vite.config.js ────────────────────────────────────────────
cat > frontend/vite.config.js << 'EOF'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
EOF

# ── index.html ────────────────────────────────────────────────
cat > frontend/index.html << 'EOF'
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Resume Matcher</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,500;1,400&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
EOF

# ── src/index.css ─────────────────────────────────────────────
cat > frontend/src/index.css << 'EOF'
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --sand-50:  #FDFAF5;
  --sand-100: #F5F0E8;
  --sand-200: #EDE5D8;
  --sand-300: #D6CCBB;
  --sand-400: #C4B89A;
  --sand-500: #8B7355;
  --sand-600: #6B5740;
  --sand-700: #4A3828;
  --sand-800: #3D2B1F;
  --sand-900: #2A1A10;
  --skill-color:   #7C6FCD;
  --exp-color:     #4CAF82;
  --tech-color:    #E09B3D;
  --culture-color: #E07B6A;
  --skill-bg:   #EDE9F7;
  --exp-bg:     #E8F5EF;
  --tech-bg:    #FEF6E8;
  --culture-bg: #FFEFED;
  --font-serif: 'Lora', Georgia, serif;
  --font-sans:  'DM Sans', system-ui, sans-serif;
  --radius-sm: 8px; --radius-md: 12px; --radius-lg: 16px; --radius-full: 9999px;
  --transition: 0.18s ease;
}
html, body, #root { height: 100%; font-family: var(--font-sans); background: var(--sand-100); color: var(--sand-800); -webkit-font-smoothing: antialiased; }
button { font-family: var(--font-sans); cursor: pointer; }
textarea, select, input { font-family: var(--font-sans); }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--sand-300); border-radius: var(--radius-full); }
EOF

# ── src/main.jsx ──────────────────────────────────────────────
cat > frontend/src/main.jsx << 'EOF'
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
)
EOF

# ── src/App.jsx ───────────────────────────────────────────────
cat > frontend/src/App.jsx << 'EOF'
import React from 'react'
import { Routes, Route } from 'react-router-dom'
import SearchPage from './pages/SearchPage'
import CandidatePage from './pages/CandidatePage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<SearchPage />} />
      <Route path="/candidate/:resumeId" element={<CandidatePage />} />
    </Routes>
  )
}
EOF

# ── src/api.js ────────────────────────────────────────────────
cat > frontend/src/api.js << 'EOF'
const BASE = '/api'

export async function fetchCategories() {
  const res = await fetch(`${BASE}/categories`)
  if (!res.ok) throw new Error('Failed to fetch categories')
  const data = await res.json()
  return data.categories
}

export async function matchCandidates({ jobQuery, topK, filterCategory }) {
  const body = { job_query: jobQuery, top_k: topK, filter_category: filterCategory || null }
  const res = await fetch(`${BASE}/match`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Match request failed')
  return data
}

export async function checkHealth() {
  const res = await fetch(`${BASE}/health`)
  if (!res.ok) throw new Error('Health check failed')
  return res.json()
}
EOF

# ── src/components/LoadingSpinner.jsx ─────────────────────────
cat > frontend/src/components/LoadingSpinner.jsx << 'EOF'
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
EOF

cat > frontend/src/components/LoadingSpinner.module.css << 'EOF'
.wrap { display:flex; flex-direction:column; align-items:center; justify-content:center; padding:60px 24px; gap:16px; }
.dotsWrap { display:flex; gap:8px; }
.dot { width:8px; height:8px; border-radius:50%; background:var(--sand-500); animation:bounce 1.2s ease-in-out infinite; }
@keyframes bounce { 0%,80%,100%{transform:scale(0.6);opacity:0.4} 40%{transform:scale(1);opacity:1} }
.label { font-size:13px; color:var(--sand-600); font-style:italic; font-family:var(--font-serif); }
.stepList { display:flex; flex-direction:column; gap:8px; width:100%; max-width:260px; margin-top:8px; }
.stepItem { display:flex; align-items:center; gap:10px; opacity:0.35; transition:opacity 0.3s ease; }
.stepItem.done { opacity:0.7; }
.stepItem.active { opacity:1; }
.stepDot { width:6px; height:6px; border-radius:50%; background:var(--sand-400); flex-shrink:0; transition:background 0.3s ease; }
.stepItem.done .stepDot { background:var(--exp-color); }
.stepItem.active .stepDot { background:var(--sand-700); box-shadow:0 0 0 3px rgba(61,43,31,0.12); }
.stepText { font-size:12px; color:var(--sand-600); }
.stepItem.active .stepText { color:var(--sand-800); font-weight:500; }
EOF

# ── src/pages/SearchPage.jsx ──────────────────────────────────
cat > frontend/src/pages/SearchPage.jsx << 'EOF'
import React, { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchCategories, matchCandidates } from '../api'
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
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(false)
  const [loadingStep, setLoadingStep] = useState(0)
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)
  const [elapsed, setElapsed] = useState(null)
  const stepTimer = useRef([])
  const startTime = useRef(null)

  useEffect(() => { fetchCategories().then(setCategories).catch(() => {}) }, [])

  function startAnimation() {
    setLoadingStep(0)
    stepTimer.current = [0,3000,8000,13000,20000,28000].map((d, i) => setTimeout(() => setLoadingStep(i), d))
  }
  function clearAnimation() { stepTimer.current.forEach(clearTimeout) }

  async function handleSubmit(e) {
    e.preventDefault()
    if (!jobQuery.trim()) return
    setError(null); setResults(null); setLoading(true)
    startAnimation(); startTime.current = Date.now()
    try {
      const data = await matchCandidates({ jobQuery: jobQuery.trim(), topK, filterCategory: category || null })
      setResults(data)
      setElapsed(((Date.now() - startTime.current) / 1000).toFixed(1))
    } catch (err) { setError(err.message) }
    finally { clearAnimation(); setLoading(false) }
  }

  const avgScore = results
    ? results.candidates.reduce((s, c) => s + c.composite_score, 0) / results.candidates.length
    : null

  return (
    <div className={styles.page}>
      <aside className={styles.sidebar}>
        <div className={styles.logo}>
          <div className={styles.logoIcon}>R</div>
          <div>
            <div className={styles.logoName}>Resume matcher</div>
            <div className={styles.logoSub}>AI-powered hiring</div>
          </div>
        </div>
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
              <button className={styles.newBtn} onClick={() => { setResults(null); setError(null) }}>New search</button>
            </div>
            <div className={styles.cardList}>
              {results.candidates.map((c, i) => {
                const col = getScoreColor(c.composite_score)
                const av = AVATAR_COLORS[i % AVATAR_COLORS.length]
                return (
                  <div key={c.resume_id} className={styles.card} style={{animationDelay:`${i*70}ms`}}
                    onClick={() => navigate(`/candidate/${encodeURIComponent(c.resume_id)}`, { state: { candidate: c, jobQuery } })}>
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
                      </div>
                    </div>
                    <div className={styles.cardRight}>
                      <div className={styles.scoreBadge} style={{background:col.bg,borderColor:col.border,color:col.text}}>{(c.composite_score*100).toFixed(0)}%</div>
                      <div className={styles.scoreLabel} style={{color:col.text}}>{getScoreLabel(c.composite_score)}</div>
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
EOF

cat > frontend/src/pages/SearchPage.module.css << 'EOF'
.page { display:grid; grid-template-columns:300px 1fr; min-height:100vh; }
.sidebar { background:#F5F0E8; border-right:0.5px solid #D6CCBB; padding:22px 18px; display:flex; flex-direction:column; gap:18px; position:sticky; top:0; height:100vh; overflow-y:auto; }
.logo { display:flex; align-items:center; gap:10px; padding-bottom:16px; border-bottom:0.5px solid #D6CCBB; }
.logoIcon { width:34px; height:34px; border-radius:9px; background:#3D2B1F; display:flex; align-items:center; justify-content:center; font-size:16px; font-family:var(--font-serif); font-style:italic; color:#F5F0E8; flex-shrink:0; }
.logoName { font-size:14px; font-weight:500; color:#3D2B1F; }
.logoSub { font-size:11px; color:#8B7355; margin-top:1px; }
.form { display:flex; flex-direction:column; gap:13px; }
.field { display:flex; flex-direction:column; gap:5px; }
.label { font-size:11px; font-weight:500; color:#8B7355; text-transform:uppercase; letter-spacing:0.05em; display:flex; align-items:center; justify-content:space-between; }
.topKVal { font-size:13px; font-weight:500; color:#3D2B1F; text-transform:none; letter-spacing:0; }
.textarea { width:100%; border:0.5px solid #C4B89A; border-radius:10px; padding:10px 12px; font-size:13px; color:#3D2B1F; background:#FDFAF5; resize:none; line-height:1.6; transition:border-color 0.15s; }
.textarea:focus { outline:none; border-color:#6B5740; }
.textarea::placeholder { color:#C4B89A; }
.select { width:100%; border:0.5px solid #C4B89A; border-radius:10px; padding:8px 12px; font-size:13px; color:#3D2B1F; background:#FDFAF5; appearance:none; background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%238B7355' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E"); background-repeat:no-repeat; background-position:right 12px center; }
.select:focus { outline:none; }
.slider { width:100%; accent-color:#3D2B1F; }
.ticks { display:flex; justify-content:space-between; font-size:10px; color:#C4B89A; padding:0 2px; }
.btn { width:100%; padding:11px 0; background:#3D2B1F; border:none; border-radius:10px; font-size:14px; font-weight:500; color:#F5F0E8; transition:background 0.15s, opacity 0.15s; }
.btn:hover:not(:disabled) { background:#2A1A10; }
.btn:disabled { opacity:0.4; cursor:not-allowed; }
.statsBox { background:#FDFAF5; border:0.5px solid #D6CCBB; border-radius:12px; padding:14px; display:flex; align-items:center; justify-content:space-between; gap:8px; }
.statItem { display:flex; flex-direction:column; align-items:center; gap:2px; flex:1; }
.statVal { font-size:18px; font-weight:500; font-family:var(--font-serif); color:#3D2B1F; }
.statLabel { font-size:10px; color:#8B7355; text-align:center; }
.statDivider { width:0.5px; height:28px; background:#D6CCBB; }
.legend { display:flex; flex-wrap:wrap; gap:6px 12px; padding-top:14px; border-top:0.5px solid #D6CCBB; margin-top:auto; }
.legendItem { display:flex; align-items:center; gap:5px; font-size:11px; color:#8B7355; }
.legendDot { width:8px; height:8px; border-radius:2px; flex-shrink:0; }
.main { background:#FDFAF5; padding:28px 32px; min-height:100vh; }
.empty { display:flex; flex-direction:column; align-items:center; text-align:center; padding:60px 40px; max-width:460px; margin:0 auto; }
.emptyIcon { color:#C4B89A; margin-bottom:18px; }
.emptyTitle { font-size:18px; font-weight:500; font-family:var(--font-serif); color:#6B5740; margin-bottom:8px; }
.emptyText { font-size:13px; color:#8B7355; line-height:1.7; margin-bottom:28px; }
.examples { display:flex; flex-direction:column; gap:8px; width:100%; }
.examplesLabel { font-size:11px; font-weight:500; color:#C4B89A; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:4px; }
.exampleBtn { font-size:12px; color:#6B5740; background:#F5F0E8; border:0.5px solid #D6CCBB; border-radius:10px; padding:9px 13px; text-align:left; line-height:1.5; transition:background 0.15s; }
.exampleBtn:hover { background:#EDE5D8; }
.errorBox { background:#FFEBEE; border:0.5px solid #FFCDD2; border-radius:12px; padding:14px 16px; color:#9B3D2E; font-size:13px; line-height:1.6; }
.errorBox strong { display:block; font-weight:500; margin-bottom:4px; }
.results { display:flex; flex-direction:column; gap:12px; }
.resultsHeader { display:flex; align-items:flex-start; justify-content:space-between; margin-bottom:4px; }
.resultsTitle { font-size:20px; font-weight:500; font-family:var(--font-serif); color:#3D2B1F; }
.resultsMeta { font-size:12px; color:#8B7355; margin-top:3px; }
.newBtn { font-size:12px; color:#8B7355; background:none; border:0.5px solid #D6CCBB; border-radius:20px; padding:5px 14px; transition:background 0.15s; }
.newBtn:hover { background:#EDE5D8; }
.cardList { display:flex; flex-direction:column; gap:8px; }
.card { background:#FDFAF5; border:0.5px solid #D6CCBB; border-radius:14px; padding:14px 16px; display:flex; align-items:center; justify-content:space-between; cursor:pointer; transition:border-color 0.15s, box-shadow 0.15s; animation:slideUp 0.35s cubic-bezier(0.16,1,0.3,1) both; }
.card:hover { border-color:#8B7355; box-shadow:0 2px 12px rgba(61,43,31,0.07); }
@keyframes slideUp { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:translateY(0)} }
.cardLeft { display:flex; align-items:center; gap:10px; min-width:0; flex:1; }
.rankBadge { font-size:11px; font-weight:500; color:#8B7355; background:#EDE5D8; border:0.5px solid #D6CCBB; border-radius:20px; padding:2px 8px; white-space:nowrap; flex-shrink:0; }
.avatar { width:36px; height:36px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:11px; font-weight:500; flex-shrink:0; }
.cardInfo { min-width:0; }
.cardName { font-size:13px; font-weight:500; color:#3D2B1F; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:220px; }
.cardMeta { font-size:11px; color:#8B7355; margin-top:2px; }
.cardTags { display:flex; flex-wrap:wrap; gap:4px; margin-top:6px; }
.tag { font-size:11px; padding:2px 7px; border-radius:20px; border:0.5px solid #D6CCBB; color:#8B7355; background:#F5F0E8; }
.matched { background:#E8F5E9; border-color:#A5D6A7; color:#1B5E20; }
.missing { background:#FFEBEE; border-color:#FFCDD2; color:#B71C1C; }
.cardRight { display:flex; flex-direction:column; align-items:flex-end; gap:4px; flex-shrink:0; padding-left:16px; }
.scoreBadge { border:0.5px solid; border-radius:20px; padding:4px 11px; font-size:15px; font-weight:500; font-family:var(--font-serif); }
.scoreLabel { font-size:10px; font-weight:500; }
.miniBar { display:flex; flex-direction:column; gap:3px; width:80px; margin-top:4px; }
.miniBarTrack { height:3px; background:#EDE5D8; border-radius:2px; overflow:hidden; }
.miniBarFill { height:100%; border-radius:2px; transition:width 0.5s cubic-bezier(0.16,1,0.3,1); }
.viewLink { font-size:11px; color:#8B7355; margin-top:2px; }
EOF

# ── src/pages/CandidatePage.jsx ───────────────────────────────
cat > frontend/src/pages/CandidatePage.jsx << 'EOF'
import React from 'react'
import { useNavigate, useLocation, useParams } from 'react-router-dom'
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
          transform="rotate(-90 50 50)" style={{transition:'stroke-dashoffset 1s cubic-bezier(0.16,1,0.3,1)'}} />
        <text x="50" y="46" textAnchor="middle" fontSize="20" fontWeight="500" fontFamily="Lora,serif" fill="#3D2B1F">{pct}%</text>
        <text x="50" y="62" textAnchor="middle" fontSize="10" fill="#8B7355">match</text>
      </svg>
    </div>
  )
}

function InsightRow({ icon, title, subtitle, variant='default' }) {
  const v = { success:{bg:'#E8F5EF',iconBg:'#4CAF82',border:'#A5D6A7'}, warning:{bg:'#FEF6E8',iconBg:'#E09B3D',border:'#F0D9A0'}, danger:{bg:'#FFEBEE',iconBg:'#E07B6A',border:'#FFCDD2'}, default:{bg:'#F5F0E8',iconBg:'#8B7355',border:'#D6CCBB'} }[variant]
  return (
    <div className={styles.insightRow} style={{background:v.bg,borderColor:v.border}}>
      <div className={styles.insightIcon} style={{background:v.iconBg}}>{icon}</div>
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
  const jobQuery = state?.jobQuery

  if (!candidate) return (
    <div className={styles.notFound}>
      <p>Candidate data not found.</p>
      <button onClick={() => navigate('/')} className={styles.backBtn}>← Back to search</button>
    </div>
  )

  const { scores, matched_skills, missing_skills, partial_matches, tech_stack, soft_skills, seniority_level, total_years, category, explanation, complexity_level } = candidate

  return (
    <div className={styles.page}>
      <div className={styles.topBar}>
        <button onClick={() => navigate(-1)} className={styles.backBtn}>← Back to results</button>
        {jobQuery && (
          <div className={styles.queryPill}>
            <span className={styles.queryLabel}>Query</span>
            <span className={styles.queryText}>{jobQuery}</span>
          </div>
        )}
      </div>
      <div className={styles.content}>
        <div className={styles.leftCol}>
          <div className={styles.profileCard}>
            <div className={styles.profileAvatar}>{resumeId.includes('_csv_') ? 'CV' : 'PD'}</div>
            <div>
              <div className={styles.profileName}>{resumeId}</div>
              <div className={styles.profileMeta}>{category}{total_years > 0 && ` · ${total_years} yrs exp`}{seniority_level && ` · ${seniority_level}`}</div>
            </div>
          </div>
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>AI insights</h3>
            <div className={styles.insightList}>
              {matched_skills.length > 0 && <InsightRow icon="✓" title="Skills matched" subtitle={`Matched: ${matched_skills.join(', ')}`} variant="success" />}
              {partial_matches.length > 0 && <InsightRow icon="~" title="Related skills" subtitle={`Transferable: ${partial_matches.join(', ')}`} variant="warning" />}
              {missing_skills.length > 0 && <InsightRow icon="✗" title="Skills gap" subtitle={`Missing: ${missing_skills.join(', ')}`} variant="danger" />}
              {tech_stack.length > 0 && <InsightRow icon="⚡" title="Tech stack identified" subtitle={tech_stack.join(', ')} variant="default" />}
              {soft_skills.length > 0 && <InsightRow icon="◎" title="Soft skills" subtitle={soft_skills.join(', ')} variant="default" />}
            </div>
          </div>
          <div className={styles.explanationBox}>
            <p className={styles.explanationLabel}>Explanation</p>
            <p className={styles.explanationText}>{explanation}</p>
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
                      <span className={styles.barPct} style={{color,background:bg}}>{pct}%</span>
                    </div>
                    <div className={styles.barTrack}><div className={styles.barFill} style={{width:`${pct}%`,background:color}} /></div>
                  </div>
                )
              })}
            </div>
          </div>
          <div className={styles.card}>
            <h3 className={styles.sectionTitle}>Candidate profile</h3>
            <div className={styles.profileGrid}>
              <div className={styles.profileCell}><span className={styles.profileCellLabel}>Years exp.</span><span className={styles.profileCellVal}>{total_years > 0 ? total_years : '—'}</span></div>
              <div className={styles.profileCell}><span className={styles.profileCellLabel}>Seniority</span><span className={styles.profileCellVal}>{seniority_level || '—'}</span></div>
              <div className={styles.profileCell}><span className={styles.profileCellLabel}>Category</span><span className={styles.profileCellVal} style={{fontSize:'11px'}}>{category}</span></div>
              <div className={styles.profileCell}><span className={styles.profileCellLabel}>Tech depth</span><span className={styles.profileCellVal}>{complexity_level || '—'}</span></div>
            </div>
          </div>
          {tech_stack.length > 0 && (
            <div className={styles.card}>
              <h3 className={styles.sectionTitle}>Tech stack</h3>
              <div className={styles.tagWrap}>{tech_stack.map(t => <span key={t} className={styles.techTag}>{t}</span>)}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
EOF

cat > frontend/src/pages/CandidatePage.module.css << 'EOF'
.page { min-height:100vh; background:#FDFAF5; }
.topBar { display:flex; align-items:center; gap:14px; padding:16px 32px; border-bottom:0.5px solid #D6CCBB; background:#F5F0E8; position:sticky; top:0; z-index:10; }
.backBtn { font-size:13px; color:#6B5740; background:none; border:0.5px solid #D6CCBB; border-radius:20px; padding:6px 14px; transition:background 0.15s; }
.backBtn:hover { background:#EDE5D8; }
.queryPill { display:flex; align-items:center; gap:8px; background:#FDFAF5; border:0.5px solid #D6CCBB; border-radius:20px; padding:5px 14px; max-width:560px; overflow:hidden; }
.queryLabel { font-size:10px; font-weight:500; color:#8B7355; text-transform:uppercase; letter-spacing:0.05em; white-space:nowrap; }
.queryText { font-size:12px; color:#3D2B1F; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.content { display:grid; grid-template-columns:1fr 340px; gap:24px; padding:28px 32px; max-width:1100px; }
.leftCol { display:flex; flex-direction:column; gap:16px; }
.rightCol { display:flex; flex-direction:column; gap:14px; }
.profileCard { display:flex; align-items:center; gap:14px; background:#FDFAF5; border:0.5px solid #D6CCBB; border-radius:14px; padding:16px 18px; }
.profileAvatar { width:48px; height:48px; border-radius:50%; background:#EDE5D8; color:#6B5740; display:flex; align-items:center; justify-content:center; font-size:13px; font-weight:500; flex-shrink:0; }
.profileName { font-size:16px; font-weight:500; color:#3D2B1F; font-family:var(--font-serif); }
.profileMeta { font-size:12px; color:#8B7355; margin-top:3px; }
.section { background:#FDFAF5; border:0.5px solid #D6CCBB; border-radius:14px; padding:16px 18px; }
.sectionTitle { font-size:13px; font-weight:500; color:#3D2B1F; margin-bottom:12px; }
.insightList { display:flex; flex-direction:column; gap:8px; }
.insightRow { display:flex; align-items:flex-start; gap:10px; border:0.5px solid; border-radius:10px; padding:10px 12px; }
.insightIcon { width:24px; height:24px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-size:11px; color:white; flex-shrink:0; font-weight:500; margin-top:1px; }
.insightTitle { font-size:13px; font-weight:500; color:#3D2B1F; }
.insightSub { font-size:12px; color:#6B5740; margin-top:2px; line-height:1.5; }
.explanationBox { background:#F5F0E8; border:0.5px solid #D6CCBB; border-radius:14px; padding:14px 16px; }
.explanationLabel { font-size:11px; font-weight:500; color:#8B7355; text-transform:uppercase; letter-spacing:0.05em; margin-bottom:6px; }
.explanationText { font-size:13px; color:#6B5740; line-height:1.7; }
.scoreCard { background:#FDFAF5; border:0.5px solid #D6CCBB; border-radius:14px; padding:20px; display:flex; flex-direction:column; align-items:center; gap:4px; }
.circleWrap { display:flex; align-items:center; justify-content:center; }
.scoreCardLabel { font-size:12px; color:#8B7355; }
.card { background:#FDFAF5; border:0.5px solid #D6CCBB; border-radius:14px; padding:16px 18px; }
.barList { display:flex; flex-direction:column; gap:10px; }
.barRow { display:flex; flex-direction:column; gap:5px; }
.barHeader { display:flex; align-items:center; justify-content:space-between; }
.barLabel { font-size:12px; color:#6B5740; }
.barPct { font-size:11px; font-weight:500; padding:2px 7px; border-radius:20px; }
.barTrack { height:5px; background:#EDE5D8; border-radius:3px; overflow:hidden; }
.barFill { height:100%; border-radius:3px; transition:width 0.7s cubic-bezier(0.16,1,0.3,1); }
.profileGrid { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
.profileCell { background:#F5F0E8; border-radius:8px; padding:10px 12px; display:flex; flex-direction:column; gap:3px; }
.profileCellLabel { font-size:10px; font-weight:500; color:#8B7355; text-transform:uppercase; letter-spacing:0.04em; }
.profileCellVal { font-size:14px; font-weight:500; color:#3D2B1F; font-family:var(--font-serif); text-transform:capitalize; }
.tagWrap { display:flex; flex-wrap:wrap; gap:6px; }
.techTag { font-size:12px; padding:4px 10px; border-radius:20px; background:#EDE5D8; border:0.5px solid #D6CCBB; color:#6B5740; }
.notFound { display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:100vh; gap:14px; color:#8B7355; }
EOF

echo ""
echo "✓ Frontend files created successfully!"
echo ""
echo "Next steps:"
echo "  cd frontend"
echo "  npm install"
echo "  npm run dev"
echo ""
echo "Make sure FastAPI is running first:"
echo "  uvicorn api.main:app --reload --host 0.0.0.0 --port 8000"