import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { label, time } from '../utils.js'

export default function Registry({ version }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.registry().then(setData).catch((e) => setError(e.message))
  }, [version])

  if (error) return <div className="page"><div className="notice bad">{error}</div></div>
  if (!data) return <div className="page"><p className="muted">Loading...</p></div>
  const s = data.summary

  return (
    <div className="page">
      <div className="row between">
        <div>
          <h2>Trauma registry</h2>
          <p className="muted">One structured record per incident, created automatically.</p>
        </div>
        <a className="btn ghost" href={api.csvUrl}>
          Export CSV
        </a>
      </div>

      <div className="tiles">
        <div className="tile"><span className="stat">{s.total}</span><span className="muted small">incidents</span></div>
        <div className="tile"><span className="stat">{s.avg_response_min == null ? '-' : Number(s.avg_response_min).toFixed(1)}</span><span className="muted small">avg response (min)</span></div>
        <div className="tile"><span className="stat">{s.within_golden_hour}</span><span className="muted small">within golden hour</span></div>
        <div className="tile"><span className="stat red">{s.critical}</span><span className="muted small">critical</span></div>
      </div>

      {data.rows.length === 0 ? (
        <div className="notice">No incidents yet. Report a crash from the dispatch console or the Bystander Copilot.</div>
      ) : (
        <div className="table-wrap">
          <table className="full">
            <thead>
              <tr>
                <th>Incident</th>
                <th>Reported</th>
                <th>Source</th>
                <th>Severity</th>
                <th>Ambulance</th>
                <th>Response</th>
                <th>Hospital</th>
                <th>Total</th>
                <th>Golden hour</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.incident_id}>
                  <td className="mono">{r.incident_id}</td>
                  <td>{time(r.reported_at)}</td>
                  <td>{label(r.source)}</td>
                  <td><span className={`chip sev ${r.severity}`}>{r.severity}</span></td>
                  <td>{r.ambulance ?? '-'}</td>
                  <td>{r.response_time_min != null ? `${r.response_time_min} min` : '-'}</td>
                  <td>{r.hospital ?? '-'}</td>
                  <td>{r.projected_total_min != null ? `${r.projected_total_min} min` : '-'}</td>
                  <td>{r.within_golden_hour == null ? '-' : r.within_golden_hour ? 'Yes' : 'No'}</td>
                  <td>{r.outcome ? label(r.outcome) : r.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
