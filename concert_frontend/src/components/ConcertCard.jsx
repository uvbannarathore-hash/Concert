import { Link } from 'react-router-dom'
import { useState } from 'react'
import { api } from '../lib/api'

const statusStyles = {
  Upcoming: 'text-go border-go/40 bg-go/10',
  'Sold Out': 'text-spot border-spot/40 bg-spot/10',
  Cancelled: 'text-haze border-edge bg-stage2',
  Completed: 'text-haze border-edge bg-stage2',
}

export default function ConcertCard({ event, wishlisted = false, onWishlistChange }) {
  const style = statusStyles[event.status] || statusStyles.Upcoming
  const [saved, setSaved] = useState(wishlisted)
  const [busy, setBusy] = useState(false)

  async function toggleWishlist(e) {
    e.preventDefault()
    e.stopPropagation()
    if (!api.isLoggedIn() || busy) return
    setBusy(true)
    try {
      if (saved) {
        await api.removeFromWishlist(event.event_id)
        setSaved(false)
      } else {
        await api.addToWishlist(event.event_id)
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
    <Link
      to={`/concerts/${event.event_id}`}
      className="group block rounded-2xl border border-edge bg-stage overflow-hidden
                 hover:border-spot/50 hover:-translate-y-1 transition-all duration-300 relative"
    >
      <div className="h-36 bg-gradient-to-br from-stage2 to-void relative flex items-end justify-between p-5">
        <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 bg-spot-radial" />
        <span className="relative text-[11px] font-mono uppercase tracking-wider px-2.5 py-1 rounded-full border border-spot2/40 text-spot2 bg-spot2/10">
          {event.event_type || 'Concert'}
        </span>
        <span className={`relative text-[11px] font-mono uppercase tracking-wider px-2.5 py-1 rounded-full border ${style}`}>
          {event.status}
        </span>

        {api.isLoggedIn() && (
          <button
            onClick={toggleWishlist}
            aria-label={saved ? 'Remove from wishlist' : 'Add to wishlist'}
            className="absolute top-3 right-3 z-10 w-8 h-8 rounded-full bg-void/70 backdrop-blur
                       flex items-center justify-center hover:scale-110 transition disabled:opacity-50"
            disabled={busy}
          >
            <svg
              width="16" height="16" viewBox="0 0 24 24"
              fill={saved ? '#FF3D6E' : 'none'}
              stroke={saved ? '#FF3D6E' : '#8B87A0'}
              strokeWidth="2"
            >
              <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.6z" />
            </svg>
          </button>
        )}
      </div>
      <div className="p-5">
        <h3 className="font-display text-2xl leading-none tracking-wide mb-2">
          {event.artist_name}
        </h3>
        <p className="text-sm text-haze mb-3">{event.venue_name}, {event.city}</p>
        <div className="flex items-center justify-between text-xs font-mono text-haze border-t border-edge pt-3">
          <span>{event.event_date}</span>
          <span>{event.event_time}</span>
        </div>
      </div>
    </Link>
  )
}
