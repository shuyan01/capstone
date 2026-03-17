import React from 'react'
import { Routes, Route } from 'react-router-dom'
import NavBar from './components/NavBar'
import SearchPage from './pages/SearchPage'
import CandidatePage from './pages/CandidatePage'
import AnalyticsPage from './pages/AnalyticsPage'
import RecruiterPage from './pages/RecruiterPage'

export default function App() {
  return (
    <>
      <NavBar />
      <div style={{ paddingTop: 48 }}>
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/recruiter" element={<RecruiterPage />} />
          <Route path="/candidate/:resumeId" element={<CandidatePage />} />
        </Routes>
      </div>
    </>
  )
}
