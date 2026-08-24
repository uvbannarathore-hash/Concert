import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import ConcertCard from '../components/ConcertCard'

export default function HomePage() {
  const [events, setEvents] = useState([])
  const [city, setCity] = useState('')
  const [eventType, setEventType] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [profile, setProfile] = useState(null)
  const [userLocation, setUserLocation] = useState(null)

  const CATEGORIES = ['Concert', 'Movie', 'Comedy Show', 'Music Show', 'Play', 'Sports']

  useEffect(() => {
    if (!navigator.geolocation) return
    navigator.geolocation.getCurrentPosition(
      (pos) => setUserLocation({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => {},
      { timeout: 8000 }
    )
  }, [])

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

  const today = new Date().toISOString().split('T')[0]
  
  // Filter out expired events
  const activeEvents = events.filter(
    (e) => e.event_date >= today && e.status !== 'Cancelled' && e.status !== 'Completed'
  )

  // Local Search Filter
  const searchedEvents = activeEvents.filter((e) => {
    const term = searchQuery.toLowerCase().trim()
    if (!term) return true
    return (
      e.artist_name.toLowerCase().includes(term) ||
      e.venue_name.toLowerCase().includes(term) ||
      e.city.toLowerCase().includes(term) ||
      (e.event_type && e.event_type.toLowerCase().includes(term))
    )
  })

  // Extract cities from active events list
  const cities = [...new Set(activeEvents.map((e) => e.city))]

  // Group events by same details but different showtimes
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

    for (const g of groups.values()) {
      g.showtimes.sort((a, b) => a.event_time.localeCompare(b.event_time))
    }

    return Array.from(groups.values())
  }

  const groupedEvents = groupEvents(searchedEvents)

  return (
    <div className="animate-fade-in-up">
      {/* Hero mesh section */}
      <section className="relative overflow-hidden border-b border-white/[0.04] bg-spot-radial pt-24 pb-20 px-6">
        <div className="absolute inset-0 bg-[linear-gradient(to_bottom,transparent_70%,#050409_100%)] pointer-events-none" />
        <div className="max-w-6xl mx-auto relative z-10">
          <p className="eyebrow mb-4">
            {profile?.name ? `${timeGreeting()}, ${profile.name.split(' ')[0]}` : 'LIVE, TONIGHT, EVERYWHERE'}
          </p>
          
          <h1 className="font-display text-5xl sm:text-6xl md:text-8xl leading-[0.9] tracking-tight max-w-4xl text-paper">
            FEEL THE STAGE<br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-spot via-[#ff5c84] to-spot2">FROM ROW ONE.</span>
          </h1>
          
          <p className="text-haze text-base sm:text-lg mt-6 max-w-xl leading-relaxed">
            Instant tickets for your favorite events. Ask our AI booking assistant anything, pay in seconds, and secure your spot under the spotlight.
          </p>

          <div className="flex flex-wrap gap-3 mt-8">
            <a
              href="https://t.me/Apra_shaktibot?text=Hi%20Apra%2C%20I%20want%20help%20with%20booking%20tickets."
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-void border border-white/[0.08] hover:border-spot/40 text-paper font-semibold hover:-translate-y-0.5 active:translate-y-0 transition-all duration-300 shadow-lg text-sm"
            >
              <svg className="w-4 h-4 text-[#229ED9]" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69.01-.03.01-.14-.07-.2-.08-.06-.19-.04-.27-.02-.12.02-1.96 1.25-5.54 3.69-.52.36-1 .53-1.42.52-.47-.01-1.37-.26-2.03-.48-.82-.27-1.47-.42-1.42-.88.03-.24.35-.49.97-.74 3.79-1.65 6.32-2.73 7.57-3.26 3.61-1.53 4.36-1.8 4.85-1.8.11 0 .35.03.5.15.13.1.17.25.18.36z"/>
              </svg>
              Chat on Telegram
            </a>
            
            <a
              href="#shows"
              className="btn-spot !px-6 !py-3 text-sm flex items-center justify-center"
            >
              View Shows 👇
            </a>
          </div>
        </div>
      </section>

      {/* Categories Horizontal Selector */}
      <section className="max-w-6xl mx-auto px-6 pt-12" id="shows">
        <div className="flex gap-2.5 overflow-x-auto pb-2 scrollbar-none">
          <button
            onClick={() => setEventType('')}
            className={`px-5 py-2.5 rounded-xl text-xs font-mono uppercase tracking-wider border transition-all duration-300 flex-shrink-0 ${
              eventType === '' 
                ? 'bg-spot2 text-void border-spot2 font-bold shadow-md shadow-spot2/10' 
                : 'border-white/[0.04] bg-white/[0.01] text-haze hover:text-paper hover:border-white/[0.1]'
            }`}
          >
            All Genres
          </button>
          {CATEGORIES.map((c) => (
            <button
              key={c}
              onClick={() => setEventType(c)}
              className={`px-5 py-2.5 rounded-xl text-xs font-mono uppercase tracking-wider border transition-all duration-300 flex-shrink-0 ${
                eventType === c 
                  ? 'bg-spot2 text-void border-spot2 font-bold shadow-md shadow-spot2/10' 
                  : 'border-white/[0.04] bg-white/[0.01] text-haze hover:text-paper hover:border-white/[0.1]'
              }`}
            >
              {c}s
            </button>
          ))}
        </div>
      </section>

      {/* Main Events Search & Listing Section */}
      <section className="max-w-6xl mx-auto px-6 py-14">
        
        {/* Dynamic Filter Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-10 border-b border-white/[0.03] pb-6">
          <div>
            <h2 className="font-display text-4xl tracking-wide uppercase text-paper">
              {searchQuery ? 'Search Results' : 'On Sale Now'}
            </h2>
            <p className="text-xs text-haze/60 font-mono mt-1">
              Showing {groupedEvents.length} unique events
            </p>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            {/* Search Input */}
            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search artists, venues, cities..."
                className="field !py-2 !pl-10 !pr-4 text-sm w-full sm:w-64"
              />
              <svg className="w-4 h-4 text-haze/60 absolute left-3.5 top-3" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
              </svg>
              {searchQuery && (
                <button 
                  onClick={() => setSearchQuery('')}
                  className="absolute right-3.5 top-2.5 text-xs text-haze hover:text-paper"
                >
                  ✕
                </button>
              )}
            </div>

            {/* City Badges Dropdown/Selector */}
            <div className="flex gap-1.5 overflow-x-auto pb-1 sm:pb-0">
              <button
                onClick={() => setCity('')}
                className={`px-3 py-2 rounded-lg text-xs font-mono border transition-all duration-200 ${
                  city === '' 
                    ? 'bg-spot text-void border-spot font-bold shadow-md shadow-spot/10' 
                    : 'border-white/[0.04] bg-white/[0.01] text-haze hover:border-white/[0.1] hover:text-paper'
                }`}
              >
                All Cities
              </button>
              {cities.map((c) => (
                <button
                  key={c}
                  onClick={() => setCity(c)}
                  className={`px-3 py-2 rounded-lg text-xs font-mono border transition-all duration-200 ${
                    city === c 
                      ? 'bg-spot text-void border-spot font-bold shadow-md shadow-spot/10' 
                      : 'border-white/[0.04] bg-white/[0.01] text-haze hover:border-white/[0.1] hover:text-paper'
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Loading Skeletons */}
        {loading && (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 animate-pulse">
            {[1, 2, 3].map((n) => (
              <div key={n} className="border border-white/[0.04] bg-stage2/20 rounded-2xl h-80 flex flex-col justify-between p-5">
                <div className="bg-stage2/60 h-40 rounded-xl w-full"></div>
                <div className="space-y-2 mt-4">
                  <div className="bg-stage2/60 h-6 rounded w-3/4"></div>
                  <div className="bg-stage2/60 h-4 rounded w-1/2"></div>
                </div>
                <div className="bg-stage2/60 h-8 rounded w-1/3 mt-4"></div>
              </div>
            ))}
          </div>
        )}

        {/* Error message */}
        {error && (
          <div className="border border-spot/20 bg-spot/5 text-spot rounded-2xl p-6 text-center text-sm font-mono max-w-md mx-auto">
            ⚠️ Network error: {error}
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && groupedEvents.length === 0 && (
          <div className="text-center py-24 border border-dashed border-white/[0.06] rounded-2xl max-w-2xl mx-auto bg-stage2/5">
            <span className="text-4xl">🎫</span>
            <p className="font-display text-2xl mb-2 text-paper mt-3 uppercase tracking-wide">Nothing matches your search</p>
            <p className="text-sm text-haze max-w-sm mx-auto">Check back soon, clear your filters, or type another search term.</p>
            <button 
              onClick={() => { setCity(''); setEventType(''); setSearchQuery(''); }}
              className="btn-ghost !px-5 !py-2 text-xs mt-6"
            >
              Reset Filters
            </button>
          </div>
        )}

        {/* Events Grid */}
        {!loading && !error && (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {groupedEvents.map((group) => (
              <ConcertCard
                key={`${group.artist_name}|${group.venue_name}|${group.city}|${group.event_date}`}
                event={group}
                userLocation={userLocation}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}