import React from 'react'
import type { Artifact } from '../api/types'
import { shortHash } from '../utils/hash'

export function ArtifactList(props: { artifacts: Artifact[] }) {
  return (
    <div style={{ display: 'grid', gap: 6 }}>
      {props.artifacts.map(a => (
        <div key={a.path} style={{ display: 'grid', gridTemplateColumns: '1fr 120px 160px', gap: 12, padding: 8, border: '1px solid #222', borderRadius: 10 }}>
          <div style={{ fontFamily: 'ui-monospace, SFMono-Regular', fontSize: 12 }}>{a.path}</div>
          <div style={{ textAlign: 'right' }}>{a.size}</div>
          <div style={{ fontFamily: 'ui-monospace, SFMono-Regular', fontSize: 12 }}>{shortHash(a.sha256, 18)}</div>
        </div>
      ))}
    </div>
  )
}
