import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiClient } from '../api/client'
import type { RunIndexEntry } from '../api/types'
import { Panel } from '../components/Panel'
import { Table } from '../components/Table'

export function RunsPage() {
  const api = useMemo(() => new ApiClient('/api'), [])
  const [rows, setRows] = useState<RunIndexEntry[]>([])
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.listRuns().then(setRows).catch(e => setErr(String(e)))
  }, [api])

  return (
    <Panel title="Runs">
      {err ? <div style={{ color: 'crimson' }}>{err}</div> : null}
      <Table
        columns={[
          { key: 'run_id', label: 'run_id' },
          { key: 'created_at', label: 'created_at' },
          { key: 'root_hash', label: 'root_hash' }
        ]}
        rows={rows}
      />
      <div style={{ marginTop: 12 }}>
        {rows.slice(0, 8).map(r => (
          <div key={r.run_id} style={{ marginTop: 6 }}>
            <Link to={`/runs/${encodeURIComponent(r.run_id)}`}>{r.run_id}</Link>
          </div>
        ))}
      </div>
    </Panel>
  )
}
