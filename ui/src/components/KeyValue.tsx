import React from 'react'

export function KeyValue(props: { k: string; v: React.ReactNode }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr', gap: 10, padding: '4px 0' }}>
      <div style={{ fontWeight: 700, opacity: 0.85 }}>{props.k}</div>
      <div style={{ wordBreak: 'break-word' }}>{props.v}</div>
    </div>
  )
}
