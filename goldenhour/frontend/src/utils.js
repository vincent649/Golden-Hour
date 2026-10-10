export const minutes = (s) => (s == null ? '-' : `${(s / 60).toFixed(1)} min`)

export const clock = (s) => {
  const t = Math.max(0, Math.floor(s))
  return `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`
}

export const label = (v) => String(v).replaceAll('_', ' ')

export const time = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '-')

// distance in metres between two [lat, lng] pairs (flat-earth is fine at city scale)
const dist = (a, b) => {
  const dy = (b[0] - a[0]) * 111320
  const dx = (b[1] - a[1]) * 111320 * Math.cos((a[0] * Math.PI) / 180)
  return Math.hypot(dx, dy)
}

/** Point at fraction f (0..1) of the way along a polyline of [lat, lng] points. */
export function pointAlong(coords, f) {
  if (!coords || coords.length === 0) return null
  if (coords.length === 1 || f <= 0) return coords[0]
  if (f >= 1) return coords[coords.length - 1]
  const seg = []
  let total = 0
  for (let i = 1; i < coords.length; i++) {
    const d = dist(coords[i - 1], coords[i])
    seg.push(d)
    total += d
  }
  let target = f * total
  for (let i = 0; i < seg.length; i++) {
    if (target <= seg[i] || i === seg.length - 1) {
      const r = seg[i] === 0 ? 0 : Math.min(1, target / seg[i])
      const a = coords[i]
      const b = coords[i + 1]
      return [a[0] + (b[0] - a[0]) * r, a[1] + (b[1] - a[1]) * r]
    }
    target -= seg[i]
  }
  return coords[coords.length - 1]
}
