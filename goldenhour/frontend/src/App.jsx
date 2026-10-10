import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import Console from './components/Console.jsx'
import Copilot from './components/Copilot.jsx'
import Hotspots from './components/Hotspots.jsx'
import Registry from './components/Registry.jsx'

const TABS = [
  ['console', 'Dispatch console'],
  ['copilot', 'Bystander Copilot'],
  ['hotspots', 'Hotspots'],
  ['registry', 'Trauma registry'],
]

const saved = () => {
  try {
    const t = localStorage.getItem('gh-tab')
    return TABS.some(([k]) => k === t) ? t : 'console'
  } catch {
    return 'console'
  }
}

export default function App() {
  const [tab, setTab] = useState(saved)
  const [state, setState] = useState(null)
  const [incidents, setIncidents] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [error, setError] = useState('')
  const [version, setVersion] = useState(0)

  const refresh = useCallback(async () => {
    try {
      const [s, i] = await Promise.all([api.state(), api.incidents()])
      setState(s)
      setIncidents(i)
      setError('')
      setVersion((v) => v + 1)
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 5000) // picks up SOS alerts raised from other screens or devices
    return () => clearInterval(id)
  }, [refresh])

  const choose = (k) => {
    setTab(k)
    try {
      localStorage.setItem('gh-tab', k)
    } catch {
      /* storage can be blocked */
    }
  }

  const reset = async () => {
    if (!window.confirm('Reset the simulated fleet, hospital beds and the trauma registry?')) return
    await api.reset()
    setSelectedId(null)
    refresh()
  }

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="dot" />
          <span className="name">GoldenHour</span>
          <span className="tag">post-crash response</span>
        </div>
        <nav>
          {TABS.map(([k, v]) => (
            <button key={k} className={k === tab ? 'on' : ''} onClick={() => choose(k)}>
              {v}
            </button>
          ))}
        </nav>
        <div className="right">
          {state && (
            <span className={`badge ${state.routing.mode}`} title={state.routing.last_error || ''}>
              {state.routing.label}
            </span>
          )}
          <button className="link" onClick={reset}>
            Reset demo
          </button>
        </div>
      </header>

      {error && !state && (
        <div className="page">
          <div className="notice bad">
            Cannot reach the API ({error}). Start the backend with <code>uvicorn app.main:app --port 8000</code> from the
            backend folder.
          </div>
        </div>
      )}

      {state && (
        <main>
          {tab === 'console' && (
            <Console state={state} incidents={incidents} refresh={refresh} selectedId={selectedId} setSelectedId={setSelectedId} />
          )}
          {tab === 'copilot' && <Copilot state={state} refresh={refresh} setSelectedId={setSelectedId} />}
          {tab === 'hotspots' && <Hotspots state={state} />}
          {tab === 'registry' && <Registry version={version} />}
        </main>
      )}
      <footer className="foot">
        All fleet, hospital and accident data is simulated for this prototype. Not for real emergencies. In an emergency call 112.
      </footer>
    </div>
  )
}
