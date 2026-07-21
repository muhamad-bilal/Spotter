import L from 'leaflet'
import { useEffect, useMemo } from 'react'
import { MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from 'react-leaflet'

import { prepareRoute } from '../../lib/mapGeometry.js'
import { stopMeta } from '../../lib/stops.js'
import MapLegend from './MapLegend.jsx'
import 'leaflet/dist/leaflet.css'
import './RouteMap.css'

const SINGLE_POINT_ZOOM = 11

/**
 * A pin built from a div rather than Leaflet's default image marker.
 *
 * Two reasons: the default icon's asset paths break under a bundler, and a div
 * can take its colour straight from the CSS custom properties, so the pins
 * follow the theme and always match the legend.
 */
function pinFor(kind) {
  const { glyph, label } = stopMeta(kind)
  return L.divIcon({
    className: '',
    html: `<span class="pin pin--${kind}"><span class="pin__glyph">${glyph}</span></span>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    popupAnchor: [0, -13],
    // Screen readers get the kind; the glyph alone would be meaningless.
    alt: label,
  })
}

function formatMoment(value) {
  if (!value) return null
  // Naive local datetimes from the API -- parsed as local time, which is
  // exactly right: the whole trip is in home-terminal time.
  const when = new Date(value)
  if (Number.isNaN(when.getTime())) return value
  return new Intl.DateTimeFormat('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(when)
}

/** Frames the whole trip. Lives inside MapContainer so it can reach the map. */
function FitToRoute({ bounds, isDegenerate }) {
  const map = useMap()

  useEffect(() => {
    if (!bounds) return
    if (isDegenerate) {
      map.setView(bounds[0], SINGLE_POINT_ZOOM)
      return
    }
    map.fitBounds(bounds, { padding: [36, 36] })
  }, [map, bounds, isDegenerate])

  return null
}

export default function RouteMap({ route }) {
  const { line, stops, bounds, hasLine, hasAnything, droppedStops } = useMemo(
    () => prepareRoute(route),
    [route],
  )

  const isDegenerate =
    Boolean(bounds) &&
    bounds[0][0] === bounds[1][0] &&
    bounds[0][1] === bounds[1][1]

  if (!hasAnything) {
    return (
      <section className="card" aria-labelledby="map-heading">
        <div className="card__header">
          <h2 className="card__title" id="map-heading">
            Route map
          </h2>
        </div>
        <div className="card__body map__unavailable">
          <p>
            No mappable coordinates came back for this trip, so the route cannot be
            drawn. The schedule and daily logs below are unaffected.
          </p>
        </div>
      </section>
    )
  }

  return (
    <section className="card" aria-labelledby="map-heading">
      <div className="card__header">
        <h2 className="card__title" id="map-heading">
          Route map
        </h2>
        <span className="card__hint">
          {stops.length} {stops.length === 1 ? 'stop' : 'stops'}
        </span>
      </div>

      <div className="map">
        <MapContainer
          className="map__canvas"
          center={bounds[0]}
          zoom={SINGLE_POINT_ZOOM}
          scrollWheelZoom={false}
          attributionControl
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            maxZoom={19}
          />

          {hasLine && (
            <>
              {/* Drawn twice: a wide dark casing under a bright core, so the
                  line stays readable over both pale and busy tiles. */}
              <Polyline positions={line} pathOptions={{ className: 'route-line__casing' }} />
              <Polyline positions={line} pathOptions={{ className: 'route-line' }} />
            </>
          )}

          {stops.map((stop, index) => (
            <Marker
              key={`${stop.kind}-${index}`}
              position={[stop.lat, stop.lng]}
              icon={pinFor(stop.kind)}
            >
              <Popup>
                <span className="popup__kind" style={{ color: `var(--stop-${stop.kind})` }}>
                  {stopMeta(stop.kind).label}
                </span>
                {stop.label && <span className="popup__label">{stop.label}</span>}
                <dl className="popup__times">
                  <dt>Arrive</dt>
                  <dd className="tnum">{formatMoment(stop.arrive_at)}</dd>
                  <dt>Depart</dt>
                  <dd className="tnum">{formatMoment(stop.depart_at)}</dd>
                </dl>
              </Popup>
            </Marker>
          ))}

          <FitToRoute bounds={bounds} isDegenerate={isDegenerate} />
        </MapContainer>
      </div>

      <div className="card__body map__footer">
        <MapLegend stops={stops} />
        {droppedStops > 0 && (
          <p className="map__note">
            {droppedStops} {droppedStops === 1 ? 'stop has' : 'stops have'} no
            coordinates and {droppedStops === 1 ? 'is' : 'are'} not shown.
          </p>
        )}
      </div>
    </section>
  )
}
