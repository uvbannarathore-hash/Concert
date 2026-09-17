import { Link } from 'react-router-dom'
import { useState } from 'react'
import { api } from '../lib/api'
import { MapPin, Calendar, Navigation } from 'lucide-react'

const statusStyles = {
  Upcoming: 'text-go border-go/20 bg-go/5',
  'Sold Out': 'text-spot border-spot/20 bg-spot/5',
  Cancelled: 'text-haze border-edge bg-stage2/40 line-through',
  Completed: 'text-haze border-edge bg-stage2/40',
}

function getDistanceKm(lat1, lon1, lat2, lon2) {
  const R = 6371
  const dLat = ((lat2 - lat1) * Math.PI) / 180
  const dLon = ((lon2 - lon1) * Math.PI) / 180
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLon / 2) ** 2
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  return R * c
}

export default function ConcertCard({ event, wishlisted = false, onWishlistChange, userLocation = null }) {
  const showtimes = event.showtimes && event.showtimes.length > 0
    ? event.showtimes
    : [{ event_id: event.event_id, event_time: event.event_time, status: event.status }]

  const distanceKm =
    userLocation && event.latitude != null && event.longitude != null
      ? getDistanceKm(userLocation.lat, userLocation.lng, event.latitude, event.longitude)
      : null

  const primary = showtimes[0]
  const overallStatus = showtimes.every((s) => s.status === 'Cancelled')
    ? 'Cancelled'
    : showtimes.every((s) => s.status === 'Completed')
    ? 'Completed'
    : showtimes.every((s) => s.status === 'Sold Out')
    ? 'Sold Out'
    : 'Upcoming'
  const style = statusStyles[overallStatus] || statusStyles.Upcoming

  const [saved, setSaved] = useState(wishlisted)
  const [busy, setBusy] = useState(false)

  async function toggleWishlist(e) {
    e.preventDefault()
    e.stopPropagation()

    if (!api.isLoggedIn() || busy) return

    setBusy(true)

    try {
      if (saved) {
        await api.removeFromWishlist(primary.event_id)
        setSaved(false)
      } else {
        await api.addToWishlist(primary.event_id)
        setSaved(true)
      }
      onWishlistChange?.()
    } catch {
      // silent
    } finally {
      setBusy(false)
    }
  }

  // Format date nicely (e.g. "Mon, Dec 20")
  const formatDate = (dateStr) => {
    try {
      const date = new Date(dateStr)
      if (isNaN(date.getTime())) return dateStr
      return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })
    } catch {
      return dateStr
    }
  }

  return (
    <div
      className="glass-card glass-card-hover group rounded-2xl overflow-hidden hover:-translate-y-1.5 transition-all duration-300 relative shadow-lg flex flex-col h-full"
    >
      <div 
        onClick={() => window.location.href = `/concerts/${primary.event_id}`} 
        className="block flex-grow cursor-pointer"
      >
        {/* Poster Wrapper */}
        <div className="h-52 relative overflow-hidden bg-void">
          {event.image_url ? (
            <img
              src={event.image_url}
              alt={event.artist_name || 'Event'}
              className="absolute inset-0 w-full h-full object-contain object-center
                         group-hover:scale-105 transition-transform duration-700 ease-out"
              onError={(e) => {
                e.currentTarget.style.display = 'none'
              }}
            />
          ) : (
            <div className="absolute inset-0 bg-gradient-to-br from-stage2/40 to-void/90 flex items-center justify-center">
              <span className="font-display text-4xl text-edge select-none">LIVEWIRE</span>
            </div>
          )}

          {/* Elegant Dark Gradient overlays */}
          <div className="absolute inset-0 bg-gradient-to-t from-void/95 via-void/30 to-transparent" />
          <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 bg-spot-radial" />

          {/* Floating tags */}
          <span className="absolute left-4 bottom-4 z-10 text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-md border border-spot2/20 text-spot2 bg-spot2/5 backdrop-blur-md">
            {event.event_type || 'Concert'}
          </span>

          <span
            className={`absolute right-4 bottom-4 z-10 text-[10px] font-mono uppercase tracking-wider px-2.5 py-0.5 rounded-md border ${style} backdrop-blur-md`}
          >
            {overallStatus}
          </span>

          {/* Glass Wishlist Heart Button */}
          {api.isLoggedIn() && (
            <button
              onClick={toggleWishlist}
              aria-label={saved ? 'Remove from wishlist' : 'Add to wishlist'}
              className="absolute top-4 right-4 z-20 w-8 h-8 rounded-full border border-white/[0.08] bg-void/50 backdrop-blur-md
                         flex items-center justify-center hover:scale-110 active:scale-95 transition-all duration-200 disabled:opacity-50"
              disabled={busy}
            >
              <svg
                width="15"
                height="15"
                viewBox="0 0 24 24"
                fill={saved ? '#FF3D6E' : 'none'}
                stroke={saved ? '#FF3D6E' : '#8B87A0'}
                strokeWidth="2.5"
                className="transition-colors duration-200"
              >
                <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.6z" />
              </svg>
            </button>
          )}
        </div>

        {/* Details Wrapper */}
        <div className="p-5 flex flex-col justify-between flex-grow">
          <div>
            <h3 className="font-display text-2xl tracking-wide group-hover:text-spot transition-colors duration-300 leading-tight relative z-20">
              {event.artist_id ? (
                <Link 
                  to={`/artists/${event.artist_id}`}
                  onClick={(e) => e.stopPropagation()}
                  className="hover:underline decoration-spot/50 underline-offset-4"
                >
                  {event.artist_name}
                </Link>
              ) : (
                <span className="cursor-default">{event.artist_name}</span>
              )}
            </h3>

            <p className="text-xs font-semibold text-haze mt-1.5 flex items-center gap-1.5 flex-wrap relative z-20">
              <span className="flex items-center gap-1">
                <MapPin className="w-3.5 h-3.5 text-spot flex-shrink-0" />
                {event.venue_id ? (
                  <Link 
                    to={`/venues/${event.venue_id}`}
                    onClick={(e) => e.stopPropagation()}
                    className="hover:underline hover:text-spot2 transition-colors"
                  >
                    {event.venue_name}
                  </Link>
                ) : (
                  <span className="cursor-default">{event.venue_name}</span>
                )}, {event.city}
              </span>
              {distanceKm !== null && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full border border-white/[0.04] text-spot2 bg-spot2/5">
                  {distanceKm.toFixed(1)} km away
                </span>
              )}
            </p>
          </div>

          <div className="text-[11px] font-mono text-haze/70 border-t border-white/[0.03] pt-3.5 mt-4 flex items-center justify-between relative z-20">
            <span className="flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5 text-haze/70" />
              {formatDate(event.event_date)}
            </span>
            {event.latitude != null && event.longitude != null && (
              <a
                href={`https://www.google.com/maps/dir/?api=1&destination=${event.latitude},${event.longitude}`}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="text-[11px] text-spot2 hover:text-spot underline underline-offset-4 hover:scale-105 transition-transform inline-flex items-center gap-1 font-semibold"
              >
                <span>Directions</span>
                <Navigation className="w-3 h-3 text-spot2" />
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Showtime Trigger Links */}
      <div className="px-5 pb-5 pt-1 border-t border-white/[0.02] flex flex-wrap gap-2 mt-auto">
        {showtimes.map((s) => (
          <Link
            key={s.event_id}
            to={`/concerts/${s.event_id}`}
            className={`text-xs font-mono px-3 py-1.5 rounded-lg border transition-all duration-200 ${
              s.status === 'Cancelled'
                ? 'border-edge/50 text-haze/30 line-through pointer-events-none opacity-40'
                : s.status === 'Sold Out'
                ? 'border-spot/20 text-spot bg-spot/5 hover:bg-spot/10'
                : 'border-white/[0.06] bg-white/[0.02] text-paper hover:border-go/60 hover:text-go hover:bg-go/5'
            }`}
          >
            {s.event_time}
          </Link>
        ))}
      </div>
    </div>
  )
}