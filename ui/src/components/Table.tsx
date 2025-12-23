import React from 'react'

export function Table<T extends object>(props: {
  columns: { key: keyof T; label: string }[]
  rows: T[]
}) {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr>
          {props.columns.map(c => (
            <th key={String(c.key)} style={{ textAlign: 'left', padding: 8, borderBottom: '1px solid #333' }}>
              {c.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {props.rows.map((r, i) => (
          <tr key={i}>
            {props.columns.map(c => (
              <td key={String(c.key)} style={{ padding: 8, borderBottom: '1px solid #222' }}>
                {String(r[c.key])}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
