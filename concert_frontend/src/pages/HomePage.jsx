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

  // Only show events that haven't happened yet and aren't cancelled/completed.
  // This is a safety net on top of the backend's own status updates - even if
  // an event's status hasn't been flipped to "Completed" yet server-side,
  // a past date always hides it here immediately.
  const today = new Date().toISOString().split('T')[0] // "YYYY-MM-DD"
  const visibleEvents = events.filter(
    (e) => e.event_date >= today && e.status !== 'Cancelled' && e.status !== 'Completed'
  )

  const cities = [...new Set(visibleEvents.map((e) => e.city))]

  // Group events that are the same title/artist at the same venue, city,
  // and date into a single card with multiple showtime buttons - matches
  // how BookMyShow groups multiple showtimes of the same movie/screen.
  function groupEvents(list) {
    const groups = new Map()

    for (const e of list) {
      const key = `${e.artist_name}|${e.venue_name}|${e.city}|${e.event_date}`
      if (!groups.has(key)) {
        groups.set(key, {
          ...e,
          showtimes: [],
        })
      }
      groups.get(key).showtimes.push({
        event_id: e.event_id,
        event_time: e.event_time,
        status: e.status,
      })
    }

    // Sort showtimes within each group chronologically (simple string sort
    // works fine for "HH:MM AM/PM" only if consistent format; adjust if needed)
    for (const g of groups.values()) {
      g.showtimes.sort((a, b) => a.event_time.localeCompare(b.event_time))
    }

    return Array.from(groups.values())
  }

  const groupedEvents = groupEvents(visibleEvents)

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
          <a
          href="https://t.me/Apra_shaktibot?text=Hi%20Apra%2C%20I%20want%20help%20with%20booking%20tickets."
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 mt-6 px-6 py-3 rounded-full bg-spot2 text-void font-bold font-body border border-spot2 hover:scale-105 transition-transform"
>
          💬 Chat with Apra on Telegram
          </a>
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

        {!loading && !error && groupedEvents.length === 0 && (
          <div className="text-center py-20 border border-dashed border-edge rounded-2xl">
            <p className="font-display text-2xl mb-2">NOTHING BOOKED HERE YET</p>
            <p className="text-haze">Check back soon, or try a different city.</p>
          </div>
        )}

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {groupedEvents.map((group) => (
            <ConcertCard key={`${group.artist_name}|${group.venue_name}|${group.city}|${group.event_date}`} event={group} />
          ))}
        </div>
      </section>
    </div>
  )
}