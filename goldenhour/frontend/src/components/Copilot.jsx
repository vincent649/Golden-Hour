import { useEffect, useRef, useState } from 'react'
import MapView, { CrashMarker } from './MapView.jsx'
import { api } from '../api.js'
import { minutes } from '../utils.js'

const VOICE_LANG = { en: 'en-IN', hi: 'hi-IN', bn: 'bn-IN' }

export default function Copilot({ state, refresh, setSelectedId }) {
  const [lang, setLang] = useState('en')
  const [guide, setGuide] = useState(null)
  const [step, setStep] = useState(0)
  const [pick, setPick] = useState(null)
  const [sent, setSent] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [speaking, setSpeaking] = useState(false)
  const synthOk = useRef(typeof window !== 'undefined' && 'speechSynthesis' in window)

  useEffect(() => {
    let live = true
    api.firstAid(lang).then((g) => live && (setGuide(g), setStep(0))).catch((e) => live && setError(e.message))
    return () => {
      live = false
      if (synthOk.current) window.speechSynthesis.cancel()
    }
  }, [lang])

  const sos = async () => {
    setBusy(true)
    setError('')
    try {
      // A bystander usually cannot describe the crash, so the server falls back to assumed details.
      const inc = await api.createIncident({ lat: pick[0], lng: pick[1], source: 'bystander' })
      setSent(inc)
      setSelectedId(inc.id)
      refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const speak = () => {
    if (!synthOk.current || !guide) return
    const synth = window.speechSynthesis
    if (speaking) {
      synth.cancel()
      setSpeaking(false)
      return
    }
    const s = guide.steps[step]
    const u = new SpeechSynthesisUtterance(`${s.title}. ${s.text}`)
    u.lang = VOICE_LANG[lang]
    u.onend = () => setSpeaking(false)
    u.onerror = () => setSpeaking(false)
    setSpeaking(true)
    synth.speak(u)
  }

  const go = (n) => {
    if (synthOk.current) window.speechSynthesis.cancel()
    setSpeaking(false)
    setStep(n)
  }

  const cur = guide?.steps[step]

  return (
    <div className="copilot">
      <div className="phone">
        <div className="row between">
          <h3>Bystander Copilot</h3>
          <div className="seg" role="group" aria-label="Language">
            {Object.entries(guide?.languages || { en: 'English', hi: 'हिन्दी', bn: 'বাংলা' }).map(([k, v]) => (
              <button key={k} className={k === lang ? 'on' : ''} onClick={() => setLang(k)}>
                {v}
              </button>
            ))}
          </div>
        </div>

        {guide && <div className="notice good">{guide.legal}</div>}

        <div className="card">
          <h4>1. Send an alert</h4>
          {!sent ? (
            <>
              <p className="muted small">Tap where the crash is, then send. Help is dispatched automatically.</p>
              <div className="mini-map">
                <MapView center={[state.city.lat, state.city.lng]} zoom={12} onClick={setPick} height="200px">
                  {pick && <CrashMarker position={pick} />}
                </MapView>
              </div>
              {error && <div className="notice bad">{error}</div>}
              <button className="btn primary wide sos" disabled={!pick || busy} onClick={sos}>
                {busy ? 'Sending...' : 'Send SOS'}
              </button>
            </>
          ) : sent.ambulance ? (
            <div className="notice good">
              <b>Help is on the way.</b>
              <br />
              {sent.ambulance.name} ({sent.ambulance.type}) arrives in about {minutes(sent.ambulance.eta_s)}. The
              hospital <b>{sent.hospital.name}</b> has been alerted. Incident {sent.id}.
            </div>
          ) : (
            <div className="notice bad">{sent.warnings?.[0] || 'No ambulance available. Please call 112.'}</div>
          )}
        </div>

        {cur && (
          <div className="card">
            <div className="row between">
              <h4>2. While you wait</h4>
              <span className="muted small">
                Step {step + 1} of {guide.steps.length}
              </span>
            </div>
            <div className="stepcard">
              <p className="step-title">{cur.title}</p>
              <p className="step-text">{cur.text}</p>
            </div>
            <div className="row between">
              <button className="btn ghost" disabled={step === 0} onClick={() => go(step - 1)}>
                Back
              </button>
              {synthOk.current && (
                <button className="btn ghost" onClick={speak}>
                  {speaking ? 'Stop' : 'Read aloud'}
                </button>
              )}
              <button className="btn" disabled={step === guide.steps.length - 1} onClick={() => go(step + 1)}>
                Next
              </button>
            </div>
            <p className="muted small">Voice depends on the voices installed on your device.</p>
          </div>
        )}
        {guide && <p className="muted small">{guide.disclaimer} This text has not yet been clinically reviewed.</p>}
      </div>
    </div>
  )
}
