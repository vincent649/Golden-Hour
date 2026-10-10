// Thin client for the GoldenHour API. In development Vite proxies /api to the backend.
const BASE = import.meta.env.VITE_API_URL || ''

async function req(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`
    try {
      const j = await res.json()
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail ?? j)
    } catch {
      /* body was not JSON */
    }
    throw new Error(msg)
  }
  return res.json()
}

export const api = {
  health: () => req('/api/health'),
  state: () => req('/api/state'),
  incidents: () => req('/api/incidents'),
  createIncident: (body) => req('/api/incidents', { method: 'POST', body: JSON.stringify(body) }),
  resolve: (id, outcome) =>
    req(`/api/incidents/${id}/resolve`, { method: 'POST', body: JSON.stringify({ outcome }) }),
  hotspots: () => req('/api/hotspots'),
  registry: () => req('/api/registry'),
  firstAid: (lang) => req(`/api/first-aid?lang=${lang}`),
  reset: () => req('/api/reset', { method: 'POST' }),
  csvUrl: `${BASE}/api/registry.csv`,
}
