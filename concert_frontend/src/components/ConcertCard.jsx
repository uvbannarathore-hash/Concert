import { Link } from 'react-router-dom'
import { useState } from 'react'
import { api } from '../lib/api'

const statusStyles = {
  Upcoming: 'text-go border-go/40 bg-go/10',
  'Sold Out': 'text-spot border-spot/40 bg-spot/10',
  Cancelled: 'text-haze border-edge bg-stage2',
  Completed: 'text-haze border-edge bg-stage2',
}

// `event` here represents a GROUP: same artist/title + venue + city + date,
// with a `showtimes` array of { event_id, event_time, status } for each
// individual time slot on that date.
export default function ConcertCard({ event, wishlisted = false, onWishlistChange }) {
  const showtimes = event.showtimes && event.showtimes.length > 0
    ? event.showtimes
    : [{ event_id: event.event_id, event_time: event.event_time, status: event.status }]

  // Use the first (earliest) showtime as the "primary" one for the poster
  // link and wishlist action - matches BookMyShow's per-title behaviour.
  const primary = showtimes[0]
  const overallStatus = showtimes.every((s) => s.status === 'Cancelled')
    ? 'Cancelled'
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
      // silent - wishlist toggle failing isn't critical enough to interrupt browsing
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="group block rounded-2xl border border-edge bg-stage overflow-hidden
                 hover:border-spot/50 hover:-translate-y-1 transition-all duration-300 relative"
    >
      <Link to={`/concerts/${primary.event_id}`} className="block">
        {/* Image */}
        <div className="h-48 relative overflow-hidden">
          {event.image_url ? (
            <img
              src={event.image_url}
              alt={event.artist_name || 'Event'}
              className="absolute inset-0 w-full h-full object-cover object-top
                         group-hover:scale-105 transition-transform duration-500"
              onError={(e) => {
                e.currentTarget.style.display = 'none'
              }}
            />
          ) : (
            <div className="absolute inset-0 bg-gradient-to-br from-stage2 to-void" />
          )}

          {/* Dark overlay */}
          <div className="absolute inset-0 bg-gradient-to-t from-void/80 via-void/20 to-transparent" />

          {/* Hover glow */}
          <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 bg-spot-radial" />

          {/* Event type */}
          <span className="absolute left-5 bottom-5 z-10 text-[11px] font-mono uppercase tracking-wider px-2.5 py-1 rounded-full border border-spot2/40 text-spot2 bg-spot2/10 backdrop-blur-sm">
            {event.event_type || 'Concert'}
          </span>

          {/* Status */}
          <span
            className={`absolute right-5 bottom-5 z-10 text-[11px] font-mono uppercase tracking-wider px-2.5 py-1 rounded-full border ${style} backdrop-blur-sm`}
          >
            {overallStatus}
          </span>

          {/* Wishlist */}
          {api.isLoggedIn() && (
            <button
              onClick={toggleWishlist}
              aria-label={saved ? 'Remove from wishlist' : 'Add to wishlist'}
              className="absolute top-3 right-3 z-20 w-8 h-8 rounded-full bg-void/70 backdrop-blur
                         flex items-center justify-center hover:scale-110 transition disabled:opacity-50"
              disabled={busy}
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill={saved ? '#FF3D6E' : 'none'}
                stroke={saved ? '#FF3D6E' : '#8B87A0'}
                strokeWidth="2"
              >
                <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.6z" />
              </svg>
            </button>
          )}
        </div>

        {/* Event details */}
        <div className="p-5 pb-3">
          <h3 className="font-display text-2xl leading-none tracking-wide mb-2">
            {event.artist_name}
          </h3>

          <p className="text-sm text-haze mb-3">
            {event.venue_name}, {event.city}
          </p>

          <div className="text-xs font-mono text-haze border-t border-edge pt-3">
            {event.event_date}
          </div>
        </div>
      </Link>

      {/* Showtime buttons - each links to its own specific event_id */}
      <div className="px-5 pb-5 flex flex-wrap gap-2">
        {showtimes.map((s) => (
          <Link
            key={s.event_id}
            to={`/concerts/${s.event_id}`}
            className={`text-xs font-mono px-3 py-1.5 rounded-lg border transition ${
              s.status === 'Cancelled'
                ? 'border-edge text-haze line-through pointer-events-none opacity-50'
                : s.status === 'Sold Out'
                ? 'border-spot/40 text-spot bg-spot/10'
                : 'border-edge text-paper hover:border-go hover:text-go hover:bg-go/10'
            }`}
          >
            {s.event_time}
          </Link>
        ))}
      </div>
    </div>
  )
}