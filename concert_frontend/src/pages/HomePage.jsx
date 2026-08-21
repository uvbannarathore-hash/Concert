import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import ConcertCard from '../components/ConcertCard'

export default function HomePage() {
  const [events, setEvents] = useState([])
  const [city, setCity] = useState('')
  const [eventType, setEventType] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [profile, setProfile] = useState(null)

  const CATEGORIES = ['Concert', 'Movie', 'Comedy Show', 'Music Show', 'Play', 'Sports']

  useEffect(() => {
    setLoading(true)
    api
      .listConcerts(city || undefined, eventType || undefined)
      .then((data) => setEvents(data.events || []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [city, eventType])

  useEffect(() => {
    if (api.isLoggedIn()) {
      api.myProfile().then(setProfile).catch(() => {})
    }
  }, [])

  function timeGreeting() {
    const h = new Date().getHours()
    if (h < 12) return 'Good morning'
    if (h < 17) return 'Good afternoon'
    return 'Good evening'
  }

  const cities = [...new Set(events.map((e) => e.city))]

  return (
    <div>
      {/* Hero */}
      <section className="bg-spot-radial border-b border-edge">
        <div className="max-w-6xl mx-auto px-6 pt-20 pb-16">
          <p className="eyebrow mb-4">
            {profile?.name ? `${timeGreeting()}, ${profile.name.split(' ')[0]}` : 'Live, tonight, everywhere'}
          </p>
          <h1 className="font-display text-6xl md:text-7xl leading-[0.95] tracking-wide max-w-3xl">
            FEEL THE SET
            <br />
            <span className="text-spot">FROM ROW ONE.</span>
          </h1>
          <p className="text-haze mt-6 max-w-lg text-lg">
            Tickets for the artists your group chat won't stop talking about.
            Book in seconds, ask our assistant anything.
          </p>
        </div>
      </section>

      {/* Category tabs */}
      <section className="max-w-6xl mx-auto px-6 pt-10">
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => setEventType('')}
            className={`px-4 py-1.5 rounded-full text-sm font-body border transition ${
              eventType === '' ? 'bg-spot2 text-void border-spot2 font-bold' : 'border-edge text-haze hover:border-haze'
            }`}
          >
            Everything
          </button>
          {CATEGORIES.map((c) => (
            <button
              key={c}
              onClick={() => setEventType(c)}
              className={`px-4 py-1.5 rounded-full text-sm font-body border transition ${
                eventType === c ? 'bg-spot2 text-void border-spot2 font-bold' : 'border-edge text-haze hover:border-haze'
              }`}
            >
              {c}s
            </button>
          ))}
        </div>
      </section>

      {/* Listing */}
      <section className="max-w-6xl mx-auto px-6 py-14">
        <div className="flex items-center justify-between mb-8 flex-wrap gap-4">
          <h2 className="font-display text-3xl tracking-wide">ON SALE NOW</h2>
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={() => setCity('')}
              className={`px-4 py-1.5 rounded-full text-sm font-body border transition ${
                city === '' ? 'bg-spot text-void border-spot font-bold' : 'border-edge text-haze hover:border-haze'
              }`}
            >
              All cities
            </button>
            {cities.map((c) => (
              <button
                key={c}
                onClick={() => setCity(c)}
                className={`px-4 py-1.5 rounded-full text-sm font-body border transition ${
                  city === c ? 'bg-spot text-void border-spot font-bold' : 'border-edge text-haze hover:border-haze'
                }`}
              >
                {c}
              </button>
            ))}
          </div>
        </div>

        {loading && <p className="text-haze">Loading shows…</p>}
        {error && <p className="text-spot">{error}</p>}

        {!loading && !error && events.length === 0 && (
          <div className="text-center py-20 border border-dashed border-edge rounded-2xl">
            <p className="font-display text-2xl mb-2">NOTHING BOOKED HERE YET</p>
            <p className="text-haze">Check back soon, or try a different city.</p>
          </div>
        )}

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {events.map((event) => (
            <ConcertCard key={event.event_id} event={event} />
          ))}
        </div>
      </section>
    </div>
  )
}
