import { useEffect, useMemo, useRef, useState } from 'react'
import { Marker, Polyline, Tooltip } from 'react-leaflet'
import MapView, { CrashMarker, icon } from './MapView.jsx'
import { api } from '../api.js'
import { clock, label, minutes, pointAlong, time } from '../utils.js'

const SPEEDS = [15, 30, 60]

/** Simulated clock: sim seconds since the crash, played faster than real time.
 *  Changing speed keeps the current position; `replayKey` restarts it. */
function useSimulation(incident, speed, replayKey) {
  const [t, setT] = useState(0)
  const st = useRef({ id: null, key: null, t: 0, last: 0 })
  const id = incident?.id
  const total = incident?.timeline?.total_s
  useEffect(() => {
    if (!total) {
      setT(0)
      return undefined
    }
    const s = st.current
    if (s.id !== id || s.key !== replayKey) {
      s.id = id
      s.key = replayKey
      s.t = 0
    }
    s.last = performance.now()
    let raf
    const tick = (now) => {
      s.t = Math.min(total, s.t + ((now - s.last) / 1000) * speed)
      s.last = now
      setT(s.t)
      if (s.t < total) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [id, total, speed, replayKey])
  const fresh = st.current.id === id && st.current.key === replayKey
  return fresh ? t : 0
}

function whereIs(incident, t) {
  const { ambulance: a, hospital: h, timeline: tl, location } = incident
  const eta = tl.ambulance_eta_s
  const atScene = tl.scene_time_s
  const home = [location.lat, location.lng]
  if (t < eta) return { phase: 'En route to the scene', pos: pointAlong(a.route.coords, eta ? t / eta : 1) }
  if (t < eta + atScene) return { phase: 'At the scene', pos: home }
  if (t < tl.total_s)
    return {
      phase: 'Transporting to hospital',
      pos: pointAlong(h.route.coords, tl.transport_s ? (t - eta - atScene) / tl.transport_s : 1),
    }
  return { phase: 'Arrived at hospital', pos: h.route.coords[h.route.coords.length - 1] }
}

function Probabilities({ p }) {
  return (
    <div className="probs">
      {['minor', 'serious', 'critical'].map((k) => (
        <div key={k} className="prob-row">
          <span>{k}</span>
          <div className="bar">
            <div className={`fill ${k}`} style={{ width: `${Math.round((p?.[k] ?? 0) * 100)}%` }} />
          </div>
          <span className="num">{Math.round((p?.[k] ?? 0) * 100)}%</span>
        </div>
      ))}
    </div>
  )
}

function GoldenHourBar({ t, tl }) {
  const pct = Math.min(100, (t / tl.golden_hour_s) * 100)
  const proj = Math.min(100, (tl.total_s / tl.golden_hour_s) * 100)
  return (
    <div className="card">
      <div className="row between">
        <h4>Golden hour</h4>
        <span className={`chip ${tl.golden_hour_ok ? 'ok' : 'bad'}`}>
          {tl.golden_hour_ok ? 'Within 60 min' : 'Over 60 min'}
        </span>
      </div>
      <div className="clock">T+ {clock(t)}</div>
      <div className="gh-track" aria-label="Golden hour progress">
        <div className={`gh-fill ${tl.golden_hour_ok ? '' : 'late'}`} style={{ width: `${pct}%` }} />
        <div className="gh-mark" style={{ left: `${proj}%` }} title="Projected arrival at hospital" />
      </div>
      <div className="gh-scale">
        <span>0</span>
        <span>60 min</span>
      </div>
      <p className="muted small">
        Projected arrival at hospital at <b>{minutes(tl.total_s)}</b>
        {tl.golden_hour_ok ? ` (${minutes(tl.remaining_s)} to spare)` : ` (${minutes(-tl.remaining_s)} over)`}.{' '}
        {tl.assumptions}
      </p>
    </div>
  )
}

function Result({ incident, t, phase, speed, setSpeed, replay, onResolve, onClose, busy }) {
  const { ambulance: a, hospital: h, severity: s, pre_alert: pa, timeline: tl } = incident
  return (
    <div className="stack">
      <div className="row between">
        <div>
          <h3 className="mono">{incident.id}</h3>
          <p className="muted small">
            {label(incident.source)} report at {time(incident.created_at)} · routing: {incident.routing?.label}
          </p>
        </div>
        <button className="btn ghost" onClick={onClose}>
          New report
        </button>
      </div>

      {incident.warnings?.map((w) => (
        <div key={w} className="notice bad">
          {w}
        </div>
      ))}

      <div className="card">
        <div className="row between">
          <h4>Severity</h4>
          <span className={`chip sev ${s.value}`}>{s.value}</span>
        </div>
        <p className="muted small">
          {s.source === 'operator'
            ? 'Set by the operator (override). The bars show what the triage model estimated for the details entered.'
            : `Source: ${s.source}${s.confidence != null ? ` · model confidence ${Math.round(s.confidence * 100)}%` : ''}`}
        </p>
        <Probabilities p={s.probabilities} />
        <p className="muted small">Decision support from a demo model trained on simulated data. The operator can override it.</p>
      </div>

      {tl && (
        <>
          <div className="card">
            <div className="row between">
              <h4>Live status</h4>
              <div className="seg" role="group" aria-label="Simulation speed">
                {SPEEDS.map((v) => (
                  <button key={v} className={v === speed ? 'on' : ''} onClick={() => setSpeed(v)}>
                    {v}x
                  </button>
                ))}
              </div>
            </div>
            <p className="phase">{phase}</p>
            <button className="btn ghost small" onClick={replay}>
              Replay
            </button>
          </div>
          <GoldenHourBar t={t} tl={tl} />
        </>
      )}

      {a && (
        <div className="card">
          <h4>Stage 2 · Ambulance dispatched</h4>
          <p className="big">
            {a.name} <span className="chip">{a.type}</span> <span className="chip">{a.provider}</span>
          </p>
          <p>
            Arrives in <b>{minutes(a.eta_s)}</b> by road ({(a.route.distance_m / 1000).toFixed(1)} km).
          </p>
          <p className="muted small">{a.reason}.</p>
          {a.straight_line_nearest.differs_from_choice && (
            <div className="notice">
              The closest unit in a straight line was <b>{a.straight_line_nearest.name}</b> (
              {Math.round(a.straight_line_nearest.distance_m)} m away).{' '}
              {a.reason.startsWith('Shortest road travel time') ? (
                <>
                  Road travel time ranks <b>{a.name}</b> first.
                </>
              ) : (
                <>
                  <b>{a.name}</b> was chosen instead: {a.reason.charAt(0).toLowerCase() + a.reason.slice(1)}.
                </>
              )}
            </div>
          )}
          {a.alternatives.length > 0 && (
            <table className="mini">
              <thead>
                <tr>
                  <th>Next best</th>
                  <th>Type</th>
                  <th>ETA</th>
                </tr>
              </thead>
              <tbody>
                {a.alternatives.map((x) => (
                  <tr key={x.id}>
                    <td>{x.name}</td>
                    <td>{x.type}</td>
                    <td>{minutes(x.eta_s)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {h && (
        <div className="card">
          <h4>Stage 3 · Hospital matched</h4>
          <p className="big">{h.name}</p>
          <p>
            Level {h.trauma_level} · {minutes(h.eta_from_scene_s)} from the scene · {h.beds_available_after} beds
            left after this admission
          </p>
          <p className="muted small">{h.reason}</p>
          <div className="tags">
            {h.capabilities.map((c) => (
              <span key={c} className="chip">
                {c}
              </span>
            ))}
          </div>
          {h.nearest.rejected && (
            <div className="notice">
              The nearest hospital by road, <b>{h.nearest.name}</b> ({minutes(h.nearest.eta_s)}), was skipped.{' '}
              {h.nearest.rejected_reason}.
            </div>
          )}
          <table className="mini">
            <thead>
              <tr>
                <th>Candidate</th>
                <th>ETA</th>
                <th>Fit</th>
              </tr>
            </thead>
            <tbody>
              {h.candidates.slice(0, 4).map((c) => (
                <tr key={c.id} className={c.id === h.id ? 'chosen' : ''}>
                  <td>
                    {c.name.replace('Demo ', '')} (L{c.trauma_level})
                  </td>
                  <td>{minutes(c.eta_s)}</td>
                  <td>{c.eligible ? 'Suitable' : c.beds_available <= 0 ? 'No beds' : `Missing ${c.missing.length}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pa && (
        <div className="card prealert">
          <div className="row between">
            <h4>Hospital pre-alert</h4>
            <span className="muted small">sent {time(pa.issued_at)}</span>
          </div>
          <p className="muted small">To: {pa.hospital_name}</p>
          <dl>
            <dt>Severity</dt>
            <dd>{pa.severity}</dd>
            <dt>Crash</dt>
            <dd>{pa.crash_summary}</dd>
            <dt>Likely injuries</dt>
            <dd>{pa.likely_injuries.join(', ')}</dd>
            <dt>Arrival</dt>
            <dd>in about {pa.eta_minutes} min</dd>
            <dt>Prepare</dt>
            <dd>{pa.prepare.join(' · ')}</dd>
          </dl>
          <p className="muted small">{pa.likely_injuries_note}</p>
        </div>
      )}

      {incident.status === 'dispatched' && (
        <div className="card">
          <h4>Close this incident</h4>
          <div className="row wrap">
            <button className="btn" disabled={busy} onClick={() => onResolve('delivered_to_hospital')}>
              Delivered to hospital
            </button>
            <button className="btn ghost" disabled={busy} onClick={() => onResolve('treated_at_scene')}>
              Treated at scene
            </button>
            <button className="btn ghost" disabled={busy} onClick={() => onResolve('cancelled_false_alarm')}>
              False alarm
            </button>
          </div>
        </div>
      )}
      {incident.status !== 'dispatched' && incident.status !== 'unserved' && (
        <div className="notice">
          Closed: {label(incident.outcome)} at {time(incident.resolved_at)}. The record is in the trauma registry.
        </div>
      )}
    </div>
  )
}

function ReportForm({ state, pick, form, setForm, onSubmit, busy, error }) {
  const opts = state.options
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  return (
    <div className="stack">
      <div className="card">
        <h4>Report a crash</h4>
        <p className="muted small">
          {pick
            ? `Location set: ${pick[0].toFixed(4)}, ${pick[1].toFixed(4)}`
            : 'Click the map to place the crash location.'}
        </p>
        <div className="grid2">
          <label>
            Road type
            <select value={form.road_type} onChange={set('road_type')}>
              {opts.road_types.map((v) => (
                <option key={v} value={v}>
                  {label(v)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Vehicle involved
            <select value={form.vehicle} onChange={set('vehicle')}>
              {opts.vehicles.map((v) => (
                <option key={v} value={v}>
                  {label(v)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Speed zone (km/h)
            <select value={form.speed_zone} onChange={set('speed_zone')}>
              {opts.speed_zones.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </label>
          <label>
            People involved
            <input type="number" min="1" max="10" value={form.people} onChange={set('people')} />
          </label>
        </div>
        <label>
          Severity
          <select value={form.severity} onChange={set('severity')}>
            <option value="auto">Auto (use the triage model)</option>
            <option value="minor">Override: minor</option>
            <option value="serious">Override: serious</option>
            <option value="critical">Override: critical</option>
          </select>
        </label>
        {error && <div className="notice bad">{error}</div>}
        <button className="btn primary wide" disabled={!pick || busy} onClick={onSubmit}>
          {busy ? 'Dispatching...' : 'Dispatch'}
        </button>
      </div>
    </div>
  )
}

function IncidentList({ incidents, selectedId, onSelect }) {
  if (!incidents.length) return null
  return (
    <div className="card">
      <h4>Incidents</h4>
      <ul className="inc-list">
        {incidents.slice(0, 8).map((i) => (
          <li key={i.id}>
            <button className={i.id === selectedId ? 'on' : ''} onClick={() => onSelect(i.id)}>
              <span className="mono">{i.id}</span>
              <span className={`chip sev ${i.severity.value}`}>{i.severity.value}</span>
              <span className="muted small">
                {label(i.source)} · {time(i.created_at)} · {i.status}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function Console({ state, incidents, refresh, selectedId, setSelectedId }) {
  const [pick, setPick] = useState(null)
  const [form, setForm] = useState({ road_type: 'urban_arterial', vehicle: 'two_wheeler', speed_zone: 50, people: 1, severity: 'auto' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [speed, setSpeed] = useState(30)
  const [replayKey, setReplayKey] = useState(0)

  const incident = useMemo(() => incidents.find((i) => i.id === selectedId) || null, [incidents, selectedId])
  const t = useSimulation(incident, speed, replayKey)

  const where = incident?.timeline ? whereIs(incident, t) : null

  const submit = async () => {
    setBusy(true)
    setError('')
    try {
      const body = {
        lat: pick[0],
        lng: pick[1],
        source: 'operator',
        details: {
          road_type: form.road_type,
          vehicle: form.vehicle,
          speed_zone: Number(form.speed_zone),
          people: Number(form.people),
        },
      }
      if (form.severity !== 'auto') body.severity_override = form.severity
      const inc = await api.createIncident(body)
      await refresh()
      setSelectedId(inc.id)
      setPick(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const resolve = async (outcome) => {
    setBusy(true)
    try {
      await api.resolve(incident.id, outcome)
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const fit = incident?.timeline
    ? [
        ...incident.ambulance.route.coords,
        ...incident.hospital.route.coords,
      ]
    : null

  return (
    <div className="console">
      <div className="map-wrap">
        <MapView
          center={[state.city.lat, state.city.lng]}
          zoom={13}
          onClick={incident ? undefined : setPick}
          fit={fit}
          fitKey={selectedId}
        >
          {state.hospitals.map((h) => (
            <Marker
              key={h.id}
              position={[h.lat, h.lng]}
              icon={icon(`H<sub>${h.trauma_level}</sub>`, `hosp l${h.trauma_level}`, 28)}
            >
              <Tooltip direction="top" offset={[0, -12]}>
                {h.name}
                <br />
                Level {h.trauma_level} · {h.beds_available}/{h.beds_total} beds
              </Tooltip>
            </Marker>
          ))}
          {state.ambulances.map((a) => (
            <Marker
              key={a.id}
              position={[a.lat, a.lng]}
              icon={icon('A', `amb ${a.status}`, 20)}
              opacity={incident?.ambulance?.id === a.id ? 0 : 1}
            >
              <Tooltip direction="top" offset={[0, -8]}>
                {a.name} · {a.type} · {a.provider} · {a.status}
              </Tooltip>
            </Marker>
          ))}

          {!incident && pick && <CrashMarker position={pick} />}
          {incident && <CrashMarker position={[incident.location.lat, incident.location.lng]} />}
          {incident?.ambulance && (
            <Polyline positions={incident.ambulance.route.coords} pathOptions={{ color: '#B3261E', weight: 4, dashArray: '8 8' }} />
          )}
          {incident?.hospital && (
            <Polyline positions={incident.hospital.route.coords} pathOptions={{ color: '#1F2933', weight: 4 }} />
          )}
          {where && <Marker position={where.pos} icon={icon('A', 'amb active', 30)} zIndexOffset={1000} />}
        </MapView>
        <div className="legend">
          <span><i className="sw crash" /> Crash</span>
          <span><i className="sw line dash" /> Ambulance to scene</span>
          <span><i className="sw line" /> Scene to hospital</span>
          <span>H1 to H3: hospital trauma level</span>
        </div>
      </div>

      <aside className="panel">
        {incident ? (
          <Result
            incident={incident}
            t={t}
            phase={where?.phase}
            speed={speed}
            setSpeed={setSpeed}
            replay={() => setReplayKey((k) => k + 1)}
            onResolve={resolve}
            onClose={() => setSelectedId(null)}
            busy={busy}
          />
        ) : (
          <ReportForm state={state} pick={pick} form={form} setForm={setForm} onSubmit={submit} busy={busy} error={error} />
        )}
        <IncidentList incidents={incidents} selectedId={selectedId} onSelect={setSelectedId} />
      </aside>
    </div>
  )
}
