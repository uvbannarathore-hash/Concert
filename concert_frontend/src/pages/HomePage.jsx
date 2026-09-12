import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import ConcertCard from '../components/ConcertCard'

const SLIDES = [
  {
    title: "FEEL THE STAGE FROM ROW ONE",
    subtitle: "Diljit Dosanjh, Arijit Singh, and live arena concerts. Secure your tickets in seconds.",
    cta: "Browse Concerts",
    category: "Concert",
    themeClass: "from-spot/30 via-void/50 to-void/90",
    badge: "🔥 SELLING FAST",
    badgeColor: "text-spot border-spot/20 bg-spot/5"
  },
  {
    title: "MIDNIGHT SESSIONS",
    subtitle: "Late-night sets, techno undergrounds, and exclusive club bookings near you.",
    cta: "Explore Music Shows",
    category: "Music Show",
    themeClass: "from-go/25 via-void/50 to-void/90",
    badge: "🎧 INDIE & TECHNO",
    badgeColor: "text-go border-go/20 bg-go/5"
  },
  {
    title: "STANDUP LAUGH SPECIALS",
    subtitle: "Live comedy tours, standup specials, and laugh riots. Sit front-row for a laugh.",
    cta: "Book Comedy Shows",
    category: "Comedy Show",
    themeClass: "from-spot2/25 via-void/50 to-void/90",
    badge: "🎤 LIVE COMEDY",
    badgeColor: "text-spot2 border-spot2/20 bg-spot2/5"
  }
]

export default function HomePage() {
  const [events, setEvents] = useState([])
  const [city, setCity] = useState('')
  const [eventType, setEventType] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [maxPrice, setMaxPrice] = useState(100000)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [profile, setProfile] = useState(null)
  const [userLocation, setUserLocation] = useState(null)
  const [recentlyViewed, setRecentlyViewed] = useState([])
  const [aiSearchResults, setAiSearchResults] = useState([])
  const [aiSearchLoading, setAiSearchLoading] = useState(false)
  const [aiSearchError, setAiSearchError] = useState('')
  const [recommendations, setRecommendations] = useState([])
  const [loadingRecommendations, setLoadingRecommendations] = useState(false)

  // Carousel State
  const [currentSlide, setCurrentSlide] = useState(0)
  const [isHovered, setIsHovered] = useState(false)

  // URL search parameter binding
  const [searchParams, setSearchParams] = useSearchParams()
  const searchQuery = searchParams.get('search') || ''

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
    try {
      const uid = localStorage.getItem('user_id')
      const storageKey = uid ? `recentlyViewedEvents_${uid}` : 'recentlyViewedEvents'
      const stored = localStorage.getItem(storageKey)
      if (stored) {
        const parsed = JSON.parse(stored)
        if (Array.isArray(parsed)) {
          setRecentlyViewed(parsed.filter(e => e && e.event_id))
        }
      } else {
        setRecentlyViewed([])
      }
    } catch (e) {
      console.warn('Failed to parse recentlyViewedEvents', e)
      setRecentlyViewed([])
    }
  }, [profile])

  useEffect(() => {
    setLoading(true)
    api
      .listConcerts(city || undefined, eventType || undefined, dateFrom || undefined, dateTo || undefined)
      .then((data) => setEvents(data.events || []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [city, eventType, dateFrom, dateTo])

  useEffect(() => {
    if (api.isLoggedIn()) {
      api.myProfile().then(setProfile).catch(() => {})
      setLoadingRecommendations(true)
      api.getRecommendations()
        .then((data) => setRecommendations(data.results || []))
        .catch((err) => console.warn('Failed to load recommendations', err))
        .finally(() => setLoadingRecommendations(false))
    }
  }, [])

  // Semantic search: fires when searchQuery changes
  useEffect(() => {
    if (!searchQuery.trim()) {
      setAiSearchResults([])
      setAiSearchError('')
      return
    }
    setAiSearchLoading(true)
    setAiSearchError('')
    api.semanticSearch(searchQuery.trim())
      .then((data) => setAiSearchResults(data.results || []))
      .catch(() => setAiSearchError('Semantic search failed. Showing keyword matches instead.'))
      .finally(() => setAiSearchLoading(false))
  }, [searchQuery])

  // Auto-rotate carousel slides
  useEffect(() => {
    if (isHovered) return
    const interval = setInterval(() => {
      setCurrentSlide((prev) => (prev + 1) % SLIDES.length)
    }, 5000)
    return () => clearInterval(interval)
  }, [isHovered])

  function timeGreeting() {
    const h = new Date().getHours()
    if (h < 12) return 'Good morning'
    if (h < 17) return 'Good afternoon'
    return 'Good evening'
  }

  const today = new Date().toISOString().split('T')[0]
  
  const activeEvents = events.filter(
    (e) => e.event_date >= today && e.status !== 'Cancelled' && e.status !== 'Completed'
  )

  const priceFilteredEvents = activeEvents.filter((e) => {
    if (!e.ticket_categories || e.ticket_categories.length === 0) return true;
    const minEventPrice = Math.min(...e.ticket_categories.map(c => Number(c.price_inr)));
    return minEventPrice <= maxPrice;
  })

  const searchedEvents = priceFilteredEvents.filter((e) => {
    const term = searchQuery.toLowerCase().trim()
    if (!term) return true
    return (
      e.artist_name.toLowerCase().includes(term) ||
      e.venue_name.toLowerCase().includes(term) ||
      e.city.toLowerCase().includes(term) ||
      (e.event_type && e.event_type.toLowerCase().includes(term))
    )
  })

  const cities = [...new Set(activeEvents.map((e) => e.city))]

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

  const handleSlideCtaClick = (category) => {
    setEventType(category)
    document.getElementById('shows')?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <div className="animate-fade-in-up">
      
      {/* Dynamic Auto-Playing Carousel Section */}
      <section 
        className="relative overflow-hidden border-b border-white/[0.04] bg-void h-[460px] flex items-center px-6 transition-all duration-500 ease-in-out"
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        {/* Dynamic Mesh Slide Gradients */}
        <div className={`absolute inset-0 bg-gradient-to-tr ${SLIDES[currentSlide].themeClass} transition-all duration-700 pointer-events-none`} />
        <div className="absolute inset-0 bg-[linear-gradient(to_bottom,transparent_75%,#050409_100%)] pointer-events-none" />
        
        <div className="max-w-6xl mx-auto relative z-10 w-full flex flex-col justify-center h-full pt-8">
          <div className="flex items-center gap-3 mb-4 animate-scale-in">
            <span className="text-[10px] font-mono tracking-widest text-haze/60 uppercase">
              {profile?.name ? `${timeGreeting()}, ${profile.name.split(' ')[0]}` : 'LIVE TICKET HUB'}
            </span>
            <span className={`text-[9px] font-mono px-2 py-0.5 rounded border uppercase tracking-wider ${SLIDES[currentSlide].badgeColor}`}>
              {SLIDES[currentSlide].badge}
            </span>
          </div>
          
          <h1 className="font-display text-4xl sm:text-5xl md:text-7xl leading-[0.95] tracking-tight max-w-4xl text-paper uppercase transition-all duration-300">
            {SLIDES[currentSlide].title}
          </h1>
          
          <p className="text-haze text-sm sm:text-base mt-4 max-w-xl leading-relaxed">
            {SLIDES[currentSlide].subtitle}
          </p>

          <div className="flex flex-wrap gap-3 mt-8">
            <button
              onClick={() => handleSlideCtaClick(SLIDES[currentSlide].category)}
              className="btn-spot !px-6 !py-2.5 text-xs font-bold uppercase tracking-wider"
            >
              {SLIDES[currentSlide].cta}
            </button>
            <a
              href="https://t.me/Apra_shaktibot?text=Hi%20Apra%2C%20I%20want%20help%20with%20booking%20tickets."
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full bg-void border border-white/[0.08] hover:border-spot/40 text-paper font-semibold hover:-translate-y-0.5 active:translate-y-0 transition-all duration-300 text-xs"
            >
              💬 Support on Telegram
            </a>
          </div>
        </div>

        {/* Carousel Navigation Arrow controls */}
        <button
          onClick={() => setCurrentSlide((prev) => (prev - 1 + SLIDES.length) % SLIDES.length)}
          className="absolute left-4 top-1/2 -translate-y-1/2 w-9 h-9 rounded-full bg-void/50 border border-white/[0.04] text-paper flex items-center justify-center hover:bg-void/80 hover:scale-105 active:scale-95 transition"
          aria-label="Previous slide"
        >
          ❮
        </button>
        <button
          onClick={() => setCurrentSlide((prev) => (prev + 1) % SLIDES.length)}
          className="absolute right-4 top-1/2 -translate-y-1/2 w-9 h-9 rounded-full bg-void/50 border border-white/[0.04] text-paper flex items-center justify-center hover:bg-void/80 hover:scale-105 active:scale-95 transition"
          aria-label="Next slide"
        >
          ❯
        </button>

        {/* Indicator dots */}
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex gap-2">
          {SLIDES.map((_, idx) => (
            <button
              key={idx}
              onClick={() => setCurrentSlide(idx)}
              className={`w-2 h-2 rounded-full transition-all duration-300 ${
                currentSlide === idx ? 'bg-spot w-6' : 'bg-white/20 hover:bg-white/40'
              }`}
              aria-label={`Go to slide ${idx + 1}`}
            />
          ))}
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

      {/* Recommended For You Section */}
      {api.isLoggedIn() && !searchQuery && (
        <section className="max-w-6xl mx-auto px-6 pt-10 pb-4">
          <h2 className="font-display text-2xl tracking-wide uppercase text-paper mb-6">Recommended For You</h2>
          {loadingRecommendations ? (
            <div className="flex gap-6 overflow-x-auto pb-4 scrollbar-none snap-x snap-mandatory">
              {[1, 2, 3].map((n) => (
                <div key={n} className="min-w-[280px] max-w-[280px] snap-start flex-shrink-0 animate-pulse">
                  <div className="border border-white/[0.04] bg-stage2/20 rounded-2xl h-80 flex flex-col justify-between p-5">
                    <div className="bg-stage2/60 h-40 rounded-xl w-full"></div>
                    <div className="space-y-2 mt-4">
                      <div className="bg-stage2/60 h-6 rounded w-3/4"></div>
                      <div className="bg-stage2/60 h-4 rounded w-1/2"></div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (() => {
            const filteredRecommendations = recommendations.filter(e => !eventType || e.event_type === eventType)
            const groupedRecommendations = groupEvents(filteredRecommendations)
            if (groupedRecommendations.length === 0) {
              return <p className="text-sm text-haze">No recommendations for this category.</p>
            }
            return (
              <div className="flex gap-6 overflow-x-auto pb-4 scrollbar-none snap-x snap-mandatory">
                {groupedRecommendations.map((e) => (
                  <div key={e.event_id} className="min-w-[280px] max-w-[280px] snap-start flex-shrink-0">
                    <ConcertCard event={e} />
                  </div>
                ))}
              </div>
            )
          })()}
        </section>
      )}

      {/* Recently Viewed Section */}
      {(() => {
        const validRecentlyViewed = recentlyViewed
          .map(e => {
            const liveEvent = events.find(ev => ev.event_id === e.event_id)
            const enriched = {
              ...e,
              artist_id: e.artist_id || liveEvent?.artist_id,
              venue_id: e.venue_id || liveEvent?.venue_id,
              event_type: e.event_type || liveEvent?.event_type,
              status: liveEvent ? liveEvent.status : (e.status || 'Upcoming'),
              showtimes: []
            }
            return enriched
          })
          .filter(e => {
            if (eventType && e.event_type && e.event_type !== eventType) return false
            return true
          })

        if (validRecentlyViewed.length === 0 || searchQuery) return null;

        return (
          <section className="max-w-6xl mx-auto px-6 pt-10 pb-4">
            <h2 className="font-display text-2xl tracking-wide uppercase text-paper mb-6">Recently Viewed</h2>
            <div className="flex gap-6 overflow-x-auto pb-4 scrollbar-none snap-x snap-mandatory">
              {validRecentlyViewed.map((e) => (
                <div key={e.event_id} className="min-w-[280px] max-w-[280px] snap-start flex-shrink-0">
                  <ConcertCard event={e} />
                </div>
              ))}
            </div>
          </section>
        )
      })()}

      {/* Main Events Search & Listing Section */}
      <section className="max-w-6xl mx-auto px-6 py-14">
        
        {/* Filter Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-10 border-b border-white/[0.03] pb-6">
          <div>
            <h2 className="font-display text-4xl tracking-wide uppercase text-paper">
              {searchQuery ? `Search: "${searchQuery}"` : 'On Sale Now'}
            </h2>
            <p className="text-xs text-haze/60 font-mono mt-1">
              {searchQuery
                ? aiSearchLoading
                  ? 'Running AI search...'
                  : `${aiSearchError ? 'Keyword' : 'Semantic'} results: ${aiSearchError ? groupedEvents.length : aiSearchResults.length} matches`
                : `Showing ${groupedEvents.length} active shows`}
            </p>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            {/* Reset / Status Info */}
            {searchQuery && (
              <button 
                onClick={() => {
                  const nextParams = new URLSearchParams(searchParams)
                  nextParams.delete('search')
                  setSearchParams(nextParams)
                }}
                className="text-xs text-spot hover:underline self-center py-1 font-mono uppercase tracking-wider"
              >
                Clear Search ✕
              </button>
            )}

            {/* Filter Controls Row */}
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="bg-void/50 border border-white/[0.04] text-paper text-xs p-2 rounded-lg"
              />
              <span className="text-haze">to</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="bg-void/50 border border-white/[0.04] text-paper text-xs p-2 rounded-lg"
              />
              
              <div className="flex flex-col gap-1 ml-0 sm:ml-4 min-w-[150px]">
                <label className="text-[10px] font-mono text-haze uppercase">Max Price: ₹{maxPrice === 100000 ? 'Any' : maxPrice}</label>
                <input
                  type="range"
                  min="0"
                  max="20000"
                  step="500"
                  value={maxPrice === 100000 ? 20000 : maxPrice}
                  onChange={(e) => setMaxPrice(Number(e.target.value) === 20000 ? 100000 : Number(e.target.value))}
                  className="accent-spot"
                />
              </div>
            </div>

            {/* City Badges */}
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

        {/* AI Search Loading Skeleton */}
        {aiSearchLoading && searchQuery && (
          <div className="flex flex-col items-center gap-4 py-16">
            <div className="w-8 h-8 rounded-full border-2 border-spot border-t-transparent animate-spin"/>
            <p className="text-haze text-sm font-mono">AI searching for "{searchQuery}"...</p>
          </div>
        )}

        {/* AI Error (fall through to keyword) */}
        {aiSearchError && searchQuery && !aiSearchLoading && (
          <p className="text-haze/60 text-xs font-mono mb-4">⚠ {aiSearchError}</p>
        )}

        {/* Semantic search results */}
        {!aiSearchLoading && searchQuery && !aiSearchError && aiSearchResults.length > 0 && (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {aiSearchResults.map((e) => (
              <ConcertCard key={e.event_id} event={{ ...e, showtimes: [] }} />
            ))}
          </div>
        )}

        {/* Semantic search no results */}
        {!aiSearchLoading && searchQuery && !aiSearchError && aiSearchResults.length === 0 && (
          <div className="text-center py-24 border border-dashed border-white/[0.06] rounded-2xl max-w-2xl mx-auto bg-stage2/5">
            <span className="text-4xl">🔍</span>
            <p className="font-display text-2xl mb-2 text-paper mt-3 uppercase tracking-wide">No semantic matches</p>
            <p className="text-sm text-haze max-w-sm mx-auto">Try a different phrase, or clear the search to browse all shows.</p>
          </div>
        )}

        {/* Normal loading state (when no search query) */}
        {loading && !searchQuery && (
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
        {error && !searchQuery && (
          <div className="border border-spot/20 bg-spot/5 text-spot rounded-2xl p-6 text-center text-sm font-mono max-w-md mx-auto">
            ⚠️ Network error: {error}
          </div>
        )}

        {/* Empty state — keyword fallback OR no search */}
        {!loading && !error && !searchQuery && groupedEvents.length === 0 && (
          <div className="text-center py-24 border border-dashed border-white/[0.06] rounded-2xl max-w-2xl mx-auto bg-stage2/5">
            <span className="text-4xl">🎫</span>
            <p className="font-display text-2xl mb-2 text-paper mt-3 uppercase tracking-wide">Nothing matches your search</p>
            <p className="text-sm text-haze max-w-sm mx-auto">Check back soon, clear your filters, or type another search term.</p>
            <button 
              onClick={() => {
                setCity('')
                setEventType('')
                setDateFrom('')
                setDateTo('')
                setMaxPrice(100000)
                setSearchParams({})
              }}
              className="btn-ghost !px-5 !py-2 text-xs mt-6"
            >
              Reset Filters
            </button>
          </div>
        )}

        {/* Events Grid — only shown when NOT in AI search mode */}
        {!searchQuery && !loading && !error && groupedEvents.length > 0 && (
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