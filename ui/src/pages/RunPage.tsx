import React, { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ApiClient } from '../api/client'
import type { RunManifest } from '../api/types'
import { Panel } from '../components/Panel'
import { Table } from '../components/Table'

export function RunPage() {
  const { runId } = useParams()
  const api = useMemo(() => new ApiClient('/api'), [])
  const [m, setM] = useState<RunManifest | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (!runId) return
    api.readManifest(runId).then(setM).catch(e => setErr(String(e)))
  }, [api, runId])

  if (!runId) return <div />

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 14 }}>
      <Panel title="Run">
        {err ? <div style={{ color: 'crimson' }}>{err}</div> : null}
        {m ? (
          <div style={{ display: 'grid', gap: 8 }}>
            <div><span style={{ fontWeight: 700 }}>run_id</span> {m.run_id}</div>
            <div><span style={{ fontWeight: 700 }}>created_at</span> {m.created_at}</div>
            <div><span style={{ fontWeight: 700 }}>tool_version</span> {m.tool_version}</div>
            <div><span style={{ fontWeight: 700 }}>artifacts_root_hash</span> {m.artifacts_root_hash}</div>
          </div>
        ) : <div>Loading</div>}
      </Panel>

      <Panel title="Artifacts">
        {m ? (
          <Table
            columns={[
              { key: 'path', label: 'path' },
              { key: 'size', label: 'size' },
              { key: 'sha256', label: 'sha256' }
            ]}
            rows={m.artifacts.slice(0, 200)}
          />
        ) : null}
      </Panel>
    </div>
  )
}
