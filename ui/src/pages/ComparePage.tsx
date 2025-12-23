import React, { useEffect, useMemo, useState } from 'react'
import { ApiClient } from '../api/client'
import type { RunManifest } from '../api/types'
import { Panel } from '../components/Panel'
import { JsonView } from '../components/JsonView'

type DiffRow = { path: string; left?: string; right?: string }

function diffArtifacts(a: RunManifest, b: RunManifest): DiffRow[] {
  const left = new Map(a.artifacts.map(x => [x.path, x.sha256]))
  const right = new Map(b.artifacts.map(x => [x.path, x.sha256]))
  const paths = new Set<string>([...left.keys(), ...right.keys()])
  const rows: DiffRow[] = []
  for (const p of Array.from(paths).sort()) {
    const l = left.get(p)
    const r = right.get(p)
    if (l !== r) rows.push({ path: p, left: l, right: r })
  }
  return rows
}

export function ComparePage() {
  const api = useMemo(() => new ApiClient('/api'), [])
  const [aId, setAId] = useState('')
  const [bId, setBId] = useState('')
  const [a, setA] = useState<RunManifest | null>(null)
  const [b, setB] = useState<RunManifest | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    setA(null)
    setB(null)
    setErr(null)
  }, [aId, bId])

  async function load() {
    setErr(null)
    try {
      const [am, bm] = await Promise.all([api.readManifest(aId), api.readManifest(bId)])
      setA(am)
      setB(bm)
    } catch (e) {
      setErr(String(e))
    }
  }

  const rows = a && b ? diffArtifacts(a, b) : []

  return (
    <div style={{ display: 'grid', gap: 14 }}>
      <Panel title="Compare runs">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: 10, alignItems: 'end' }}>
          <div>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>Left run_id</div>
            <input value={aId} onChange={e => setAId(e.target.value)} style={{ width: '100%', padding: 8, borderRadius: 10, border: '1px solid #333' }} />
          </div>
          <div>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>Right run_id</div>
            <input value={bId} onChange={e => setBId(e.target.value)} style={{ width: '100%', padding: 8, borderRadius: 10, border: '1px solid #333' }} />
          </div>
          <button onClick={load} style={{ padding: '8px 14px', borderRadius: 10, border: '1px solid #333' }}>Load</button>
        </div>
        {err ? <div style={{ color: 'crimson', marginTop: 10 }}>{err}</div> : null}
      </Panel>

      <Panel title="Artifact diffs">
        <div style={{ fontFamily: 'ui-monospace, SFMono-Regular', fontSize: 12, display: 'grid', gap: 6 }}>
          {rows.slice(0, 300).map(r => (
            <div key={r.path} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, border: '1px solid #222', borderRadius: 10, padding: 10 }}>
              <div>{r.path}</div>
              <div>{r.left ?? ''}</div>
              <div>{r.right ?? ''}</div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Manifests">
        {a ? <JsonView value={a} /> : null}
        {b ? <JsonView value={b} /> : null}
      </Panel>
    </div>
  )
}
