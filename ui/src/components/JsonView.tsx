import React, { useMemo, useState } from 'react'

export function JsonView(props: { value: unknown }) {
  const [collapsed, setCollapsed] = useState(true)
  const text = useMemo(() => JSON.stringify(props.value, null, 2), [props.value])
  return (
    <div>
      <button onClick={() => setCollapsed(!collapsed)} style={{ marginBottom: 8 }}>
        {collapsed ? 'Expand' : 'Collapse'}
      </button>
      <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', border: '1px solid #222', borderRadius: 12, padding: 12, maxHeight: collapsed ? 220 : 800, overflow: 'auto' }}>
        {text}
      </pre>
    </div>
  )
}
