import { useEffect } from 'react'
import L from 'leaflet'
import { MapContainer, TileLayer, Marker, useMap, useMapEvents } from 'react-leaflet'

export function icon(html, cls = '', size = 26) {
  return L.divIcon({
    html,
    className: `gh-icon ${cls}`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

function ClickHandler({ onClick }) {
  useMapEvents({ click: (e) => onClick && onClick([e.latlng.lat, e.latlng.lng]) })
  return null
}

/** Fits the map to a set of [lat, lng] points whenever `fitKey` changes. */
function FitTo({ points, fitKey }) {
  const map = useMap()
  useEffect(() => {
    if (points && points.length > 1) {
      map.fitBounds(L.latLngBounds(points), { padding: [50, 50], maxZoom: 15 })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey, map])
  return null
}

export function CrashMarker({ position }) {
  return <Marker position={position} icon={icon('', 'crash', 22)} zIndexOffset={900} />
}

export default function MapView({ center, zoom = 13, onClick, fit, fitKey, height = '100%', children }) {
  return (
    <MapContainer center={center} zoom={zoom} style={{ height, width: '100%' }} preferCanvas>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {onClick && <ClickHandler onClick={onClick} />}
      {fit && <FitTo points={fit} fitKey={fitKey} />}
      {children}
    </MapContainer>
  )
}
