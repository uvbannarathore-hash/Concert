import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import ConcertCard from '../components/ConcertCard'

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
    <div className="max-w-6xl mx-auto px-6 py-14">
      <p className="eyebrow mb-3">Saved for later</p>
      <h1 className="font-display text-5xl tracking-wide mb-10">MY WISHLIST</h1>

      {loading && <p className="text-haze">Loading…</p>}
      {error && <p className="text-spot">{error}</p>}

      {!loading && events.length === 0 && (
        <div className="text-center py-20 border border-dashed border-edge rounded-2xl">
          <p className="font-display text-2xl mb-2">NOTHING SAVED YET</p>
          <p className="text-haze">Tap the heart on any show to keep it here.</p>
        </div>
      )}

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {events.map((event) => (
          <ConcertCard key={event.event_id} event={event} wishlisted onWishlistChange={load} />
        ))}
      </div>
    </div>
  )
}
