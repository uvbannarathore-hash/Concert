import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import ConcertCard from '../components/ConcertCard'
import { Link } from 'react-router-dom'

export default function WishlistPage() {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  function load() {
    setLoading(true)
    api
      .getWishlist()
      .then((data) => setEvents(data.wishlist || []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  return (
    <div className="max-w-6xl mx-auto px-6 py-12 animate-fade-in-up">
      <div className="mb-10">
        <p className="eyebrow mb-1">Your bookmarks</p>
        <h1 className="font-display text-5xl tracking-wide uppercase text-paper">MY WISHLIST</h1>
        <p className="text-xs text-haze mt-1">Quickly access shows you have saved for later</p>
      </div>

      {loading && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 animate-pulse">
          {[1, 2].map((n) => (
            <div key={n} className="border border-white/[0.04] bg-stage2/20 rounded-2xl h-80"></div>
          ))}
        </div>
      )}
      
      {error && (
        <div className="border border-spot/20 bg-spot/5 text-spot text-xs font-mono rounded-xl p-4 mb-6 max-w-md mx-auto">
          ⚠️ Connection failure: {error}
        </div>
      )}

      {!loading && events.length === 0 && (
        <div className="text-center py-20 border border-dashed border-white/[0.06] rounded-2xl bg-stage2/5 max-w-xl mx-auto">
          <span className="text-4xl font-mono text-spot">❤️</span>
          <p className="font-display text-2xl mb-2 text-paper mt-3 uppercase tracking-wide">Wishlist is empty</p>
          <p className="text-sm text-haze max-w-xs mx-auto">Tap the bookmark heart button on any show card while browsing to save it here.</p>
          <Link to="/" className="btn-spot text-xs mt-6 inline-block">Explore Shows</Link>
        </div>
      )}

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {events.map((event) => (
          <ConcertCard key={event.event_id} event={event} wishlisted onWishlistChange={load} />
        ))}
      </div>
    </div>
  )
}
