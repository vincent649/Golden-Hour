import { useEffect, useState } from 'react'
import { Circle, CircleMarker, Marker, Tooltip } from 'react-leaflet'
import MapView, { icon } from './MapView.jsx'
import { api } from '../api.js'

const SEV_COLOR = { minor: '#8A949E', serious: '#C77700', critical: '#B3261E' }

export default function Hotspots({ state }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.hotspots().then(setData).catch((e) => setError(e.message))
  }, [])

  if (error) return <div className="page"><div className="notice bad">{error}</div></div>
  if (!data) return <div className="page"><p className="muted">Analysing accident history...</p></div>
  const m = data.metrics

  return (
    <div className="console">
      <div className="map-wrap">
        <MapView center={[state.city.lat, state.city.lng]} zoom={13}>
          {data.accidents.map((p, i) => (
            <CircleMarker
              key={i}
              center={[p.lat, p.lng]}
              radius={3}
              pathOptions={{ color: SEV_COLOR[p.severity], fillColor: SEV_COLOR[p.severity], fillOpacity: 0.45, weight: 0 }}
            />
          ))}
          {data.hotspots.map((h) => (
            <Circle
              key={h.id}
              center={[h.lat, h.lng]}
              radius={650}
              pathOptions={{ color: '#1F2933', weight: 1.5, dashArray: '4 6', fillOpacity: 0 }}
            />
          ))}
          {data.hotspots.map((h) => (
            <Marker key={`tag-${h.id}`} position={[h.lat + 0.0066, h.lng]} icon={icon(h.id, 'zone-tag', 26)} interactive={false} />
          ))}
          {data.stations.map((s) => (
            <Marker key={s.id} position={[s.lat, s.lng]} icon={icon(s.id, 'station', 30)} zIndexOffset={800}>
              <Tooltip direction="top" offset={[0, -12]}>
                Recommended ambulance station {s.id} (covers {s.covers})
              </Tooltip>
            </Marker>
          ))}
        </MapView>
        <div className="legend">
          <span><i className="sw dot minor" /> minor</span>
          <span><i className="sw dot serious" /> serious</span>
          <span><i className="sw dot critical" /> critical</span>
          <span>S1 to S3: recommended stations</span>
        </div>
      </div>

      <aside className="panel">
        <div className="stack">
          <div className="card">
            <h4>Ambulance pre-positioning</h4>
            <p className="muted small">
              Accident locations are clustered (DBSCAN) into hotspots. Stations are added greedily where they cut the
              accident-weighted travel time the most.
            </p>
            <div className="stats">
              <div>
                <span className="stat">{m.avg_eta_before_min}</span>
                <span className="muted small">min average, today</span>
              </div>
              <div>
                <span className="stat red">{m.avg_eta_after_min}</span>
                <span className="muted small">min with {data.stations.length} new stations</span>
              </div>
              <div>
                <span className="stat">{m.improvement_pct}%</span>
                <span className="muted small">faster</span>
              </div>
            </div>
            <p className="muted small">{m.note}</p>
          </div>
          <div className="card">
            <h4>Hotspots</h4>
            <table className="mini">
              <thead>
                <tr>
                  <th>Zone</th>
                  <th>Crashes</th>
                  <th>Critical</th>
                  <th>ETA now</th>
                  <th>ETA after</th>
                </tr>
              </thead>
              <tbody>
                {data.hotspots.map((h) => (
                  <tr key={h.id}>
                    <td>{h.id}</td>
                    <td>{h.count}</td>
                    <td>{Math.round(h.critical_share * 100)}%</td>
                    <td>{h.eta_before_min} min</td>
                    <td>{h.eta_after_min} min</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </aside>
    </div>
  )
}
