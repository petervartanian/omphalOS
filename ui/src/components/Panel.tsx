import React from 'react'

export function Panel(props: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ border: '1px solid #333', borderRadius: 12, padding: 16 }}>
      <div style={{ fontWeight: 700, marginBottom: 10 }}>{props.title}</div>
      <div>{props.children}</div>
    </section>
  )
}
