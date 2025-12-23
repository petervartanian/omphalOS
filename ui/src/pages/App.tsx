import React from 'react'
import { Routes, Route, Navigate, Link } from 'react-router-dom'
import { RunsPage } from './RunsPage'
import { RunPage } from './RunPage'
import { ComparePage } from './ComparePage'

export function App() {
  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: 18, fontFamily: 'ui-sans-serif, system-ui' }}>
      <header style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 14 }}>
        <div style={{ fontSize: 22, fontWeight: 800 }}>omphalOS</div>
        <nav style={{ display: 'flex', gap: 12 }}>
          <Link to="/runs">Runs</Link>
          <Link to="/compare">Compare</Link>
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<Navigate to="/runs" replace />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:runId" element={<RunPage />} />
        <Route path="/compare" element={<ComparePage />} />
      </Routes>
    </div>
  )
}
