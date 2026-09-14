import { useEffect, useState } from 'react'
import { adminApi } from '../lib/adminApi'
import { api } from '../lib/api'
import { Bot, BarChart3, Calendar, Ticket, Receipt, Tag, Inbox, Armchair, Mic, Building2, MapPin, Paperclip, Settings } from 'lucide-react'
import AnalyticsDashboard from '../components/AnalyticsDashboard'

const emptyEvent = {
  artist_id: '', artist_name: '', venue_id: '', venue_name: '',
  city: '', event_date: '', event_time: '', event_type: 'Concert',
}
const EVENT_TYPES = ['Concert', 'Movie', 'Comedy Show', 'Music Show', 'Play', 'Sports']
const emptyTicket = { event_id: '', category: '', price_inr: '', total_seats: '' }

export default function AdminPage() {
  const [tab, setTab] = useState('assistant') // assistant | events | pricing | bookings
  const [forbidden, setForbidden] = useState(false)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  const [eventForm, setEventForm] = useState(emptyEvent)
  const [ticketForm, setTicketForm] = useState(emptyTicket)
  const [bookings, setBookings] = useState([])
  const [submissions, setSubmissions] = useState([])
  const [submissionsLoading, setSubmissionsLoading] = useState(false)
  const [submissionFilter, setSubmissionFilter] = useState('Pending')
  const [processingSubmissionId, setProcessingSubmissionId] = useState(null)

  // Coupons
  const emptyCoupon = { code: '', discount_type: 'percentage', discount_value: '', max_uses: '', max_uses_per_user: 1, event_id: '', valid_from: '', valid_until: '' }
  const [couponForm, setCouponForm] = useState(emptyCoupon)
  const [coupons, setCoupons] = useState([])
  const [couponsLoading, setCouponsLoading] = useState(false)

  // Artists
  const [artists, setArtists] = useState([])
  const [artistsLoading, setArtistsLoading] = useState(false)
  const [editingArtistId, setEditingArtistId] = useState(null)
  const [artistForm, setArtistForm] = useState({ bio: '', facebook: '', instagram: '', twitter: '', website: '' })

  // Venues
  const [venues, setVenues] = useState([])
  const [venuesLoading, setVenuesLoading] = useState(false)
  const [editingVenueId, setEditingVenueId] = useState(null)
  const [venueForm, setVenueForm] = useState({ address: '', capacity: '', latitude: '', longitude: '' })

  // Seat layout builder
  const [seatEventId, setSeatEventId] = useState('')
  const [seatRowForm, setSeatRowForm] = useState({ category: '', seat_row: '', seat_count: '', start_number: '1' })
  const [seatLayout, setSeatLayout] = useState([])
  const [seatLayoutLoading, setSeatLayoutLoading] = useState(false)

  const [showPastEvents, setShowPastEvents] = useState(false)
  const [pastEvents, setPastEvents] = useState([])
  const [pastEventsLoading, setPastEventsLoading] = useState(false)

  const [chatMessages, setChatMessages] = useState([
    { role: 'assistant', text: "Welcome to the backstage panel. I'm your AI Admin Assistant. I can create, update, or cancel events, edit ticket pricing, or summarize sales. Type below to get started, and feel free to upload poster images (📎) or map coordinates (📍)." },
  ])
  const [chatInput, setChatInput] = useState('')
  const [chatImage, setChatImage] = useState(null)
  const [chatSending, setChatSending] = useState(false)

  const [showLocationPicker, setShowLocationPicker] = useState(false)
  const [venueLocation, setVenueLocation] = useState(null)
  const [locationQuery, setLocationQuery] = useState('')
  const [locationResults, setLocationResults] = useState([])
  const [locationSearching, setLocationSearching] = useState(false)

  function flash(setter, text) {
    setter(text)
    setTimeout(() => setter(''), 3500)
  }

  useEffect(() => {
    if (!showLocationPicker || locationQuery.trim().length < 3) {
      setLocationResults([])
      return
    }
    const timer = setTimeout(async () => {
      setLocationSearching(true)
      try {
        const res = await fetch(
          `https://nominatim.openstreetmap.org/search?format=json&addressdetails=1&limit=5&q=${encodeURIComponent(locationQuery)}`
        )
        const data = await res.json()
        setLocationResults(data || [])
      } catch (err) {
        console.warn('Venue search failed', err)
        setLocationResults([])
      } finally {
        setLocationSearching(false)
      }
    }, 500)

    return () => clearTimeout(timer)
  }, [locationQuery, showLocationPicker])

  function selectLocationResult(place) {
    setVenueLocation({
      name: place.display_name.split(',')[0],
      address: place.display_name,
      latitude: parseFloat(place.lat),
      longitude: parseFloat(place.lon),
    })
    setShowLocationPicker(false)
    setLocationQuery('')
    setLocationResults([])
  }

  async function handleCreateEvent(e) {
    e.preventDefault()
    setError('')
    try {
      const res = await adminApi.createEvent(eventForm)
      flash(setMsg, `Event successfully created: ${res.event_id}`)
      setEventForm(emptyEvent)
    } catch (err) {
      if (err.message.includes('403')) setForbidden(true)
      flash(setError, err.message)
    }
  }

  async function handleAddTicket(e) {
    e.preventDefault()
    setError('')
    try {
      await adminApi.addTicketCategory({
        ...ticketForm,
        price_inr: Number(ticketForm.price_inr),
        total_seats: Number(ticketForm.total_seats),
      })
      flash(setMsg, 'Ticket category successfully added.')
      setTicketForm(emptyTicket)
    } catch (err) {
      if (err.message.includes('403')) setForbidden(true)
      flash(setError, err.message)
    }
  }

  async function handleAdminChatSend(e) {
    e.preventDefault()
    const text = chatInput.trim()
    if (!text || chatSending) return

    const tags = [
      chatImage ? `📎 ${chatImage.name}` : null,
      venueLocation ? `📍 ${venueLocation.name || venueLocation.address}` : null,
    ].filter(Boolean).join(' ')

    setChatMessages((m) => [...m, { role: 'user', text: tags ? `${text} ${tags}` : text }])
    setChatInput('')
    setChatSending(true)
    setError('')

    const imageToSend = chatImage
    const locationToSend = venueLocation

    try {
      const res = await adminApi.chat(text, imageToSend, locationToSend)
      setChatMessages((m) => [...m, { role: 'assistant', text: res.reply }])
    } catch (err) {
      if (err.message.includes('403')) setForbidden(true)
      setChatMessages((m) => [...m, { role: 'assistant', text: `Error: ${err.message}` }])
    } finally {
      setChatSending(false)
      setChatImage(null)
      setVenueLocation(null)
    }
  }

  function loadBookings() {
    adminApi
      .allBookings()
      .then((data) => setBookings(data.bookings || []))
      .catch((err) => {
        if (err.message.includes('403')) setForbidden(true)
        setError(err.message)
      })
  }

  function loadPastEvents() {
    setPastEventsLoading(true)
    adminApi
      .listConcerts()
      .then((data) => {
        const today = new Date().toISOString().split('T')[0]
        const past = (data.events || []).filter(
          (e) => e.event_date < today || e.status === 'Completed' || e.status === 'Cancelled'
        )
        past.sort((a, b) => (a.event_date < b.event_date ? 1 : -1))
        setPastEvents(past)
      })
      .catch((err) => {
        if (err.message.includes('403')) setForbidden(true)
        setError(err.message)
      })
      .finally(() => setPastEventsLoading(false))
  }

  useEffect(() => {
    if (tab === 'bookings') loadBookings()
  }, [tab])

  function loadSubmissions() {
    setSubmissionsLoading(true)
    adminApi
      .getShowSubmissions(submissionFilter)
      .then((data) => setSubmissions(data.submissions || []))
      .catch((err) => {
        if (err.message.includes('403')) setForbidden(true)
        setError(err.message)
      })
      .finally(() => setSubmissionsLoading(false))
  }

  useEffect(() => {
    if (tab === 'submissions') loadSubmissions()
  }, [tab, submissionFilter])

  function loadCoupons() {
    setCouponsLoading(true)
    api.adminGetCoupons()
      .then(data => setCoupons(data.coupons || []))
      .catch(err => setError(err.message))
      .finally(() => setCouponsLoading(false))
  }

  function loadArtists() {
    setArtistsLoading(true)
    api.getArtists()
      .then(data => setArtists(data.artists || []))
      .catch(err => setError(err.message))
      .finally(() => setArtistsLoading(false))
  }

  function loadVenues() {
    setVenuesLoading(true)
    api.getVenues()
      .then(data => setVenues(data.venues || []))
      .catch(err => setError(err.message))
      .finally(() => setVenuesLoading(false))
  }

  useEffect(() => {
    if (tab === 'coupons') loadCoupons()
    if (tab === 'artists') loadArtists()
    if (tab === 'venues') loadVenues()
  }, [tab])

  async function handleCreateCoupon(e) {
    e.preventDefault()
    setError('')
    try {
      const payload = {
        ...couponForm,
        discount_value: parseFloat(couponForm.discount_value),
        max_uses: parseInt(couponForm.max_uses, 10),
        max_uses_per_user: parseInt(couponForm.max_uses_per_user, 10),
      }
      if (!payload.event_id) delete payload.event_id
      if (!payload.valid_from) delete payload.valid_from
      if (!payload.valid_until) delete payload.valid_until
      
      await api.adminCreateCoupon(payload)
      flash(setMsg, 'Coupon successfully created.')
      setCouponForm(emptyCoupon)
      loadCoupons()
    } catch (err) {
      flash(setError, err.message)
    }
  }

  async function handleToggleCoupon(id, currentState) {
    try {
      await api.adminToggleCoupon(id, !currentState)
      loadCoupons()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleApproveSubmission(id) {
    setProcessingSubmissionId(id)
    try {
      const res = await adminApi.approveShowSubmission(id)
      setMsg('Show approved and published.')
      loadSubmissions()

      // Seat-map setup is a separate, easy-to-forget step (see Seat
      // Layout tab) - offer to jump straight there with the new
      // event's ID pre-filled, instead of relying on the admin to
      // remember to come back for it later.
      if (res?.event_id && window.confirm(
        `Event ${res.event_id} is live. Set up an interactive seat map for it now? (Choose "Cancel" to keep the plain quantity-based booking flow instead.)`
      )) {
        setSeatEventId(res.event_id)
        setTab('seatmap')
        setSeatLayout([]) // brand new event - nothing to load yet, skip the round trip
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setProcessingSubmissionId(null)
    }
  }

  async function handleRejectSubmission(id) {
    const reason = window.prompt('Reason for rejecting this submission (shown to the organizer):')
    if (reason === null) return
    setProcessingSubmissionId(id)
    try {
      await adminApi.rejectShowSubmission(id, reason)
      setMsg('Submission rejected.')
      loadSubmissions()
    } catch (err) {
      setError(err.message)
    } finally {
      setProcessingSubmissionId(null)
    }
  }

  function loadSeatLayout() {
    if (!seatEventId.trim()) return
    setSeatLayoutLoading(true)
    adminApi
      .getSeatLayout(seatEventId.trim())
      .then((data) => setSeatLayout(data.seats || []))
      .catch((err) => setError(err.message))
      .finally(() => setSeatLayoutLoading(false))
  }

  async function handleAddSeatRow(e) {
    e.preventDefault()
    setError('')
    try {
      await adminApi.addSeatRow({
        event_id: seatEventId.trim(),
        category: seatRowForm.category.trim(),
        seat_row: seatRowForm.seat_row.trim().toUpperCase(),
        seat_count: parseInt(seatRowForm.seat_count, 10),
        start_number: parseInt(seatRowForm.start_number || '1', 10),
      })
      setMsg(`Row ${seatRowForm.seat_row.toUpperCase()} added.`)
      setSeatRowForm({ category: '', seat_row: '', seat_count: '', start_number: '1' })
      loadSeatLayout()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteSeatRow(row) {
    if (!window.confirm(`Delete all seats in row ${row}? This cannot be undone.`)) return
    try {
      await adminApi.deleteSeatRow(seatEventId.trim(), row)
      setMsg(`Row ${row} deleted.`)
      loadSeatLayout()
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    if (tab === 'events' && showPastEvents) loadPastEvents()
  }, [tab, showPastEvents])

  if (forbidden) {
    return (
      <div className="max-w-lg mx-auto px-6 py-24 text-center">
        <p className="eyebrow mb-3">Backstage Access Required</p>
        <h1 className="font-display text-4xl mb-4 text-paper">NOT ON THE LIST</h1>
        <p className="text-haze text-sm leading-relaxed">
          Your account is not configured with administrative privileges. Please flip the
          <code className="mx-1.5 px-2 py-0.5 bg-stage2 border border-white/[0.04] rounded font-mono text-xs text-spot2">is_admin</code>
          flag inside public.users schema in Supabase.
        </p>
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-12 animate-fade-in-up">
      <div className="mb-8">
        <p className="eyebrow mb-1">Backstage control center</p>
        <h1 className="font-display text-5xl tracking-wide uppercase text-paper">ADMIN PANEL</h1>
        <p className="text-xs text-haze mt-1">Deploy listings, customize prices, and coordinate bookings</p>
      </div>

      <div className="grid md:grid-cols-12 gap-8 items-start">
        
        {/* Navigation Sidebar (Left Column) */}
        <div className="md:col-span-3 flex flex-row md:flex-col gap-2 overflow-x-auto md:overflow-visible pb-3 md:pb-0 border-b md:border-b-0 md:border-r border-white/[0.04] pr-0 md:pr-6">
          {[
            { id: 'assistant', label: 'AI Agent', icon: Bot },
            { id: 'analytics', label: 'Analytics', icon: BarChart3 },
            { id: 'events', label: 'Event Setup', icon: Calendar },
            { id: 'pricing', label: 'Ticket Rates', icon: Ticket },
            { id: 'bookings', label: 'Bookings List', icon: Receipt },
            { id: 'coupons', label: 'Promo Codes', icon: Tag },
            { id: 'submissions', label: 'Show Submissions', icon: Inbox },
            { id: 'seatmap', label: 'Seat Layout', icon: Armchair },
            { id: 'artists', label: 'Artists', icon: Mic },
            { id: 'venues', label: 'Venues', icon: Building2 },
          ].map((item) => {
            const Icon = item.icon
            return (
              <button
                key={item.id}
                onClick={() => setTab(item.id)}
                className={`flex items-center gap-3 px-4 py-3 rounded-xl text-xs font-mono uppercase tracking-wider border transition-all duration-300 flex-shrink-0 w-auto md:w-full text-left ${
                  tab === item.id 
                    ? 'bg-spot text-void border-spot font-bold shadow-md shadow-spot/10' 
                    : 'border-white/[0.04] bg-white/[0.01] text-haze hover:border-white/[0.1] hover:text-paper'
                }`}
              >
                <Icon className="w-4 h-4 flex-shrink-0" />
                <span>{item.label}</span>
              </button>
            )
          })}
        </div>

        {/* Dynamic Panels (Right Column) */}
        <div className="md:col-span-9 space-y-6">
          
          {/* Messages Alerts */}
          {msg && <div className="border border-go/20 bg-go/5 text-go text-xs font-mono rounded-xl p-4">{msg}</div>}
          {error && <div className="border border-spot/20 bg-spot/5 text-spot text-xs font-mono rounded-xl p-4">{error}</div>}

          {/* 0. Analytics Dashboard Panel */}
          {tab === 'analytics' && (
            <AnalyticsDashboard />
          )}

          {/* 1. AI Assistant Panel */}
          {tab === 'assistant' && (
            <div className="bg-stage/20 border border-white/[0.04] rounded-2xl p-5 flex flex-col h-[55vh] shadow-2xl relative">
              <div className="flex-1 overflow-y-auto space-y-4 pr-1 mb-4 scrollbar-none">
                {chatMessages.map((m, i) => {
                  const isUser = m.role === 'user'
                  return (
                    <div key={i} className={`flex gap-3 items-end ${isUser ? 'justify-end' : 'justify-start'} animate-scale-in`}>
                      {!isUser && (
                        <span className="w-7 h-7 rounded-full border border-spot2/20 bg-spot2/5 text-spot2 font-mono text-xs flex items-center justify-center flex-shrink-0">
                          🤖
                        </span>
                      )}
                      <div
                        className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap leading-relaxed shadow-md ${
                          isUser
                            ? 'bg-gradient-to-r from-spot to-[#ff5c84] text-void font-semibold rounded-br-sm'
                            : 'bg-stage border border-white/[0.04] text-paper rounded-bl-sm'
                        }`}
                      >
                        {m.text}
                      </div>
                      {isUser && (
                        <span className="w-7 h-7 rounded-full border border-spot/20 bg-spot/5 text-spot font-mono text-xs flex items-center justify-center flex-shrink-0">
                          <Settings className="w-3.5 h-3.5" />
                        </span>
                      )}
                    </div>
                  )
                })}
                {chatSending && (
                  <div className="flex gap-3 items-end justify-start animate-pulse">
                    <span className="w-7 h-7 rounded-full border border-spot2/20 bg-spot2/5 text-spot2 font-mono text-xs flex items-center justify-center flex-shrink-0">
                      <Bot className="w-3.5 h-3.5" />
                    </span>
                    <div className="bg-stage border border-white/[0.04] rounded-2xl rounded-bl-sm px-4 py-3 text-sm text-haze">
                      Working on it…
                    </div>
                  </div>
                )}
              </div>

              {/* Autocomplete Input or Tags */}
              <div className="flex flex-wrap gap-2 mb-3">
                {chatImage && (
                  <span className="flex items-center gap-1.5 text-[10px] font-mono text-spot bg-spot/5 border border-spot/15 px-2.5 py-1 rounded-md">
                    <Paperclip className="w-3 h-3 text-spot" /> {chatImage.name}
                    <button type="button" onClick={() => setChatImage(null)} className="text-[9px] hover:text-white font-bold">✕</button>
                  </span>
                )}
                {venueLocation && (
                  <span className="flex items-center gap-1.5 text-[10px] font-mono text-spot2 bg-spot2/5 border border-spot2/15 px-2.5 py-1 rounded-md">
                    <MapPin className="w-3 h-3 text-spot2" /> {venueLocation.name || venueLocation.address.split(',')[0]}
                    <button type="button" onClick={() => setVenueLocation(null)} className="text-[9px] hover:text-white font-bold">✕</button>
                  </span>
                )}
              </div>

              {showLocationPicker && (
                <div className="mb-3 relative animate-scale-in">
                  <input
                    className="field !py-2.5 text-xs font-mono"
                    value={locationQuery}
                    onChange={(e) => setLocationQuery(e.target.value)}
                    placeholder="Search venue (e.g. DY Patil Stadium Mumbai)..."
                    autoFocus
                  />
                  {locationSearching && <p className="text-[10px] font-mono text-haze mt-1 px-2">Searching Nominatim geocoding index...</p>}
                  {locationResults.length > 0 && (
                    <div className="absolute z-30 w-full mt-1 bg-stage border border-white/[0.06] rounded-xl overflow-hidden shadow-2xl">
                      {locationResults.map((place, i) => (
                        <button
                          key={i}
                          type="button"
                          onClick={() => selectLocationResult(place)}
                          className="block w-full text-left px-4 py-2 text-xs text-paper hover:bg-spot hover:text-void transition duration-150 truncate border-b border-white/[0.02]"
                        >
                          {place.display_name}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Chat action form */}
              <form onSubmit={handleAdminChatSend} className="flex gap-2 border-t border-white/[0.04] pt-4 flex-shrink-0">
                <input
                  className="field text-sm"
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  placeholder="e.g. 'Create a Diljit concert in Pune on Dec 20, 8 PM'"
                  disabled={chatSending}
                />
                
                {/* File Upload button wrapper */}
                <label className="btn-ghost !px-3 cursor-pointer flex items-center justify-center text-sm shadow-md" title="Attach flyers/poster image">
                  <Paperclip className="w-4 h-4 text-haze hover:text-paper" />
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    disabled={chatSending}
                    onChange={(e) => setChatImage(e.target.files[0] || null)}
                  />
                </label>

                {/* Pin location button */}
                <button
                  type="button"
                  onClick={() => setShowLocationPicker((s) => !s)}
                  className="btn-ghost !px-3 flex items-center justify-center text-sm shadow-md"
                  disabled={chatSending}
                  title="Search & attach geocoding coordinates"
                >
                  <MapPin className="w-4 h-4 text-haze hover:text-paper" />
                </button>

                <button type="submit" disabled={chatSending || !chatInput.trim()} className="btn-spot !px-6 text-sm font-bold disabled:opacity-40">
                  Send
                </button>
              </form>
            </div>
          )}

          {/* 2. Setup Events Form Panel */}
          {tab === 'events' && (
            <div className="space-y-6">
              <form onSubmit={handleCreateEvent} className="glass-card bg-stage/15 border border-white/[0.04] rounded-2xl p-6 space-y-4 shadow-2xl">
                <div className="flex items-center gap-2 mb-2">
                  <Calendar className="w-5 h-5 text-spot" />
                  <h2 className="font-display text-xl tracking-wide uppercase text-paper">Deploy Event Listing</h2>
                </div>

                <div>
                  <label className="block text-xs font-mono text-haze mb-1.5 uppercase">Genre / Category</label>
                  <select
                    className="field font-mono text-sm py-2.5"
                    value={eventForm.event_type}
                    onChange={(e) => setEventForm({ ...eventForm, event_type: e.target.value })}
                  >
                    {EVENT_TYPES.map((t) => (
                      <option key={t} value={t} className="bg-stage text-paper">{t}</option>
                    ))}
                  </select>
                </div>

                <div className="grid sm:grid-cols-2 gap-4">
                  <Field label={eventForm.event_type === 'Movie' ? 'Movie Title' : 'Artist Name'} value={eventForm.artist_name} onChange={(v) => setEventForm({ ...eventForm, artist_name: v })} placeholder="e.g. Diljit Dosanjh" />
                  <Field label="Artist ID (Ref)" value={eventForm.artist_id} onChange={(v) => setEventForm({ ...eventForm, artist_id: v })} placeholder="e.g. ART01" />
                  <Field label="Venue Name" value={eventForm.venue_name} onChange={(v) => setEventForm({ ...eventForm, venue_name: v })} placeholder="e.g. DY Patil Stadium" />
                  <Field label="Venue ID (Ref)" value={eventForm.venue_id} onChange={(v) => setEventForm({ ...eventForm, venue_id: v })} placeholder="e.g. VEN02" />
                  <Field label="City" value={eventForm.city} onChange={(v) => setEventForm({ ...eventForm, city: v })} placeholder="e.g. Mumbai" />
                  <Field label="Show Date" value={eventForm.event_date} onChange={(v) => setEventForm({ ...eventForm, event_date: v })} placeholder="e.g. 2026-12-20" />
                  <Field label="Show Time" value={eventForm.event_time} onChange={(v) => setEventForm({ ...eventForm, event_time: v })} placeholder="e.g. 7:00 PM" />
                </div>
                
                <button type="submit" className="btn-spot w-full text-sm font-bold mt-2">Deploy Listing</button>
              </form>

              {/* Past / Completed listings selector */}
              <div className="bg-stage/20 border border-white/[0.04] rounded-2xl p-6 shadow-xl">
                <button
                  type="button"
                  onClick={() => setShowPastEvents((s) => !s)}
                  className="flex items-center justify-between w-full text-left outline-none"
                >
                  <h2 className="font-display text-xl tracking-wide uppercase text-paper">Past & Closed Listings</h2>
                  <span className="text-haze text-xs font-mono">{showPastEvents ? 'HIDE ▲' : 'SHOW ▼'}</span>
                </button>

                {showPastEvents && (
                  <div className="mt-5 space-y-3 animate-scale-in">
                    {pastEventsLoading && <p className="text-xs font-mono text-haze">Loading past records...</p>}
                    {!pastEventsLoading && pastEvents.length === 0 && (
                      <p className="text-xs font-mono text-haze">No archived events found.</p>
                    )}
                    {pastEvents.map((e) => (
                      <div
                        key={e.event_id}
                        className="border border-white/[0.04] bg-white/[0.01] rounded-xl p-4 flex justify-between items-center"
                      >
                        <div>
                          <p className="font-body font-bold text-paper text-sm">{e.artist_name}</p>
                          <p className="text-[11px] text-haze font-mono mt-0.5 flex items-center gap-1.5">
                            <MapPin className="w-3 h-3 text-spot flex-shrink-0" /> {e.venue_name}, {e.city} · <Calendar className="w-3 h-3 text-spot2 flex-shrink-0 inline" /> {e.event_date} · {e.event_time}
                          </p>
                        </div>
                        <span className="text-xs font-mono text-spot border border-spot/20 bg-spot/5 px-2 py-0.5 rounded uppercase">
                          {e.status}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 3. Ticket Pricing Rates Panel */}
          {tab === 'pricing' && (
            <form onSubmit={handleAddTicket} className="glass-card bg-stage/15 border border-white/[0.04] rounded-2xl p-6 space-y-4 shadow-2xl">
              <div className="flex items-center gap-2 mb-2">
                <Ticket className="w-5 h-5 text-spot" />
                <h2 className="font-display text-xl tracking-wide uppercase text-paper">Add Ticket Category</h2>
              </div>
              
              <div className="grid sm:grid-cols-2 gap-4">
                <Field label="Event ID (Ref)" value={ticketForm.event_id} onChange={(v) => setTicketForm({ ...ticketForm, event_id: v })} placeholder="e.g. EVT1785938" />
                <Field label="Category Title" value={ticketForm.category} onChange={(v) => setTicketForm({ ...ticketForm, category: v })} placeholder="e.g. VIP Lounge / General Admission" />
                <Field label="Ticket Rate (INR)" value={ticketForm.price_inr} onChange={(v) => setTicketForm({ ...ticketForm, price_inr: v })} placeholder="5000" type="number" />
                <Field label="Initial Ticket Volume" value={ticketForm.total_seats} onChange={(v) => setTicketForm({ ...ticketForm, total_seats: v })} placeholder="150" type="number" />
              </div>
              <button type="submit" className="btn-spot w-full text-sm font-bold mt-2">Publish Category</button>
            </form>
          )}

          {/* 4. Bookings List Database Panel */}
          {tab === 'bookings' && (
            <div className="space-y-4">
              <h2 className="font-display text-xl text-paper uppercase tracking-wider mb-2">Booked Entries</h2>
              {bookings.length === 0 && <p className="text-xs font-mono text-haze">No user purchases logged in database.</p>}
              
              <div className="space-y-3">
                {bookings.map((b) => {
                  const eventObj = b.events || {}
                  return (
                    <div key={b.booking_id} className="border border-white/[0.04] bg-white/[0.01] rounded-xl p-4 flex justify-between items-center flex-wrap gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs text-paper font-semibold">{b.booking_id}</span>
                          <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded border border-white/[0.06] text-haze">
                            User ID: {b.user_id.split('-')[0]}...
                          </span>
                        </div>
                        <p className="text-xs text-haze mt-1.5 flex items-center gap-1">
                          <Ticket className="w-3.5 h-3.5 text-spot inline" /> <span className="font-bold text-paper">{eventObj.artist_name || `Ref ID: ${b.event_id}`}</span> · <span className="uppercase">{b.category}</span> · <span className="font-bold text-spot2">{b.seats_booked} seats</span>
                        </p>
                        {eventObj.event_date && (
                          <p className="text-[10px] font-mono text-haze/50 mt-1 flex items-center gap-1">
                            <MapPin className="w-3 h-3 text-spot inline" /> {eventObj.venue_name}, {eventObj.city} · <Calendar className="w-3 h-3 text-spot2 inline" /> {eventObj.event_date}
                          </p>
                        )}
                      </div>
                      
                      <div className="text-right flex items-center gap-3">
                        <span className="text-[11px] font-mono uppercase px-2.5 py-0.5 rounded-full border border-go/20 bg-go/5 text-go">
                          {b.status}
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* 5. Show Submissions Review Panel */}
          {tab === 'submissions' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between flex-wrap gap-3">
                <h2 className="font-display text-xl text-paper uppercase tracking-wider">Show Submissions</h2>
                <div className="flex gap-2">
                  {['Pending', 'Approved', 'Rejected', 'all'].map((s) => (
                    <button
                      key={s}
                      onClick={() => setSubmissionFilter(s)}
                      className={`text-[10px] font-mono uppercase px-3 py-1.5 rounded-lg border transition ${
                        submissionFilter === s
                          ? 'bg-spot text-void border-spot font-bold'
                          : 'border-white/[0.06] text-haze hover:text-paper'
                      }`}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>

              {submissionsLoading && <p className="text-xs font-mono text-haze">Loading…</p>}
              {!submissionsLoading && submissions.length === 0 && (
                <p className="text-xs font-mono text-haze">No {submissionFilter !== 'all' ? submissionFilter.toLowerCase() : ''} submissions.</p>
              )}

              <div className="space-y-3">
                {submissions.map((s) => {
                  const submitter = s.users || {}
                  return (
                    <div key={s.id} className="border border-white/[0.04] bg-white/[0.01] rounded-xl p-4 space-y-3">
                      <div className="flex justify-between items-start flex-wrap gap-3">
                        <div>
                          <p className="font-mono text-sm text-paper font-semibold">{s.artist_name} · {s.event_type}</p>
                          <p className="text-xs text-haze mt-1">
                            📍 {s.venue_name}, {s.city} · 📅 {s.event_date} at {s.event_time}
                          </p>
                          <p className="text-[11px] text-haze/60 mt-1">
                            Submitted by: {submitter.name || submitter.email || s.submitted_by_user_id}
                            {s.organizer_contact_phone && ` · ${s.organizer_contact_phone}`}
                          </p>
                          {s.organizer_notes && (
                            <p className="text-[11px] text-haze/60 mt-1 italic">"{s.organizer_notes}"</p>
                          )}
                        </div>
                        <span className={`text-[10px] font-mono uppercase px-2.5 py-0.5 rounded-full border ${
                          s.status === 'Approved' ? 'border-go/20 bg-go/5 text-go' :
                          s.status === 'Rejected' ? 'border-spot/20 bg-spot/5 text-spot' :
                          'border-spot2/20 bg-spot2/5 text-spot2'
                        }`}>
                          {s.status}
                        </span>
                      </div>

                      <div className="flex flex-wrap gap-2">
                        {(s.categories || []).map((c, i) => (
                          <span key={i} className="text-[10px] font-mono px-2 py-1 rounded border border-white/[0.06] text-haze">
                            {c.category}: ₹{c.price} ({c.seats} seats)
                          </span>
                        ))}
                      </div>

                      {s.status === 'Rejected' && s.rejection_reason && (
                        <p className="text-[11px] text-spot">Rejection reason: {s.rejection_reason}</p>
                      )}
                      {s.status === 'Approved' && s.created_event_id && (
                        <p className="text-[11px] text-go">Published as event_id: {s.created_event_id}</p>
                      )}

                      {s.status === 'Pending' && (
                        <div className="flex gap-3 pt-2 border-t border-white/[0.04]">
                          <button
                            onClick={() => handleApproveSubmission(s.id)}
                            disabled={processingSubmissionId === s.id}
                            className="text-xs font-mono uppercase px-3 py-1.5 rounded-lg border border-go/30 text-go hover:bg-go/10 disabled:opacity-40"
                          >
                            {processingSubmissionId === s.id ? 'Working…' : '✓ Approve & Publish'}
                          </button>
                          <button
                            onClick={() => handleRejectSubmission(s.id)}
                            disabled={processingSubmissionId === s.id}
                            className="text-xs font-mono uppercase px-3 py-1.5 rounded-lg border border-spot/30 text-spot hover:bg-spot/10 disabled:opacity-40"
                          >
                            ✕ Reject
                          </button>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* 6. Seat Layout Builder Panel */}
          {tab === 'seatmap' && (
            <div className="space-y-6">
              <h2 className="font-display text-xl text-paper uppercase tracking-wider">Seat Layout Builder</h2>
              <p className="text-xs text-haze -mt-3">
                Add rows one at a time to enable the interactive seat-map booking experience for an event.
                Events with no rows defined here keep using the plain quantity-based booking flow.
              </p>

              <div className="flex gap-2 max-w-md">
                <input
                  value={seatEventId}
                  onChange={(e) => setSeatEventId(e.target.value)}
                  placeholder="Event ID (e.g. EVT1788...)"
                  className="flex-1 bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper focus:outline-none focus:border-spot/40"
                />
                <button onClick={loadSeatLayout} className="text-xs font-mono uppercase px-4 py-2 rounded-lg border border-white/[0.06] text-haze hover:text-paper">
                  Load
                </button>
              </div>

              {seatEventId && (
                <>
                  <form onSubmit={handleAddSeatRow} className="bg-stage/20 border border-white/[0.04] rounded-xl p-4 grid grid-cols-2 sm:grid-cols-5 gap-3 items-end">
                    <div>
                      <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">Category</label>
                      <input
                        required
                        value={seatRowForm.category}
                        onChange={(e) => setSeatRowForm((f) => ({ ...f, category: e.target.value }))}
                        placeholder="Recliner"
                        className="w-full bg-void border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-sm text-paper"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">Row Letter</label>
                      <input
                        required
                        value={seatRowForm.seat_row}
                        onChange={(e) => setSeatRowForm((f) => ({ ...f, seat_row: e.target.value }))}
                        placeholder="P"
                        maxLength={3}
                        className="w-full bg-void border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-sm text-paper"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">Seat Count</label>
                      <input
                        required
                        type="number"
                        min="1"
                        value={seatRowForm.seat_count}
                        onChange={(e) => setSeatRowForm((f) => ({ ...f, seat_count: e.target.value }))}
                        placeholder="11"
                        className="w-full bg-void border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-sm text-paper"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">Start #</label>
                      <input
                        type="number"
                        min="1"
                        value={seatRowForm.start_number}
                        onChange={(e) => setSeatRowForm((f) => ({ ...f, start_number: e.target.value }))}
                        className="w-full bg-void border border-white/[0.06] rounded-lg px-2.5 py-1.5 text-sm text-paper"
                      />
                    </div>
                    <button type="submit" className="btn-spot text-xs h-[38px]">+ Add Row</button>
                  </form>

                  <div className="space-y-2">
                    {seatLayoutLoading && <p className="text-xs font-mono text-haze">Loading…</p>}
                    {!seatLayoutLoading && seatLayout.length === 0 && (
                      <p className="text-xs font-mono text-haze">No seat rows defined yet for this event.</p>
                    )}
                    {Object.entries(
                      seatLayout.reduce((acc, s) => {
                        acc[s.seat_row] = acc[s.seat_row] || { category: s.category, count: 0, statuses: {} }
                        acc[s.seat_row].count += 1
                        acc[s.seat_row].statuses[s.status] = (acc[s.seat_row].statuses[s.status] || 0) + 1
                        return acc
                      }, {})
                    ).map(([row, info]) => (
                      <div key={row} className="flex items-center justify-between bg-white/[0.01] border border-white/[0.04] rounded-lg px-4 py-2.5">
                        <div className="text-xs font-mono text-paper">
                          Row <span className="text-spot2 font-bold">{row}</span> — {info.category} — {info.count} seats
                          <span className="text-haze/50 ml-2">
                            ({info.statuses.Available || 0} available, {info.statuses.Booked || 0} booked)
                          </span>
                        </div>
                        <button
                          onClick={() => handleDeleteSeatRow(row)}
                          className="text-[10px] font-mono uppercase text-spot hover:text-[#ff5c84]"
                        >
                          Delete
                        </button>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {/* 7. Coupons / Promo Codes Panel */}
          {tab === 'coupons' && (
            <div className="space-y-6">
              <form onSubmit={handleCreateCoupon} className="glass-card bg-stage/15 border border-white/[0.04] rounded-2xl p-6 space-y-4 shadow-2xl">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xl">🎫</span>
                  <h2 className="font-display text-xl tracking-wide uppercase text-paper">Create Promo Code</h2>
                </div>
                
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  <Field label="Coupon Code" value={couponForm.code} onChange={v => setCouponForm({ ...couponForm, code: v.toUpperCase() })} placeholder="e.g. EARLYBIRD20" required />
                  <div>
                    <label className="block text-xs font-mono text-haze mb-1.5 uppercase">Discount Type</label>
                    <select className="field font-mono text-sm py-2.5" value={couponForm.discount_type} onChange={e => setCouponForm({ ...couponForm, discount_type: e.target.value })}>
                      <option value="percentage">Percentage (%)</option>
                      <option value="fixed">Fixed Amount (₹)</option>
                    </select>
                  </div>
                  <Field label="Discount Value" value={couponForm.discount_value} onChange={v => setCouponForm({ ...couponForm, discount_value: v })} placeholder="e.g. 20 or 500" type="number" required />
                  <Field label="Max Total Uses" value={couponForm.max_uses} onChange={v => setCouponForm({ ...couponForm, max_uses: v })} placeholder="e.g. 100" type="number" required />
                  <Field label="Max Uses Per User" value={couponForm.max_uses_per_user} onChange={v => setCouponForm({ ...couponForm, max_uses_per_user: v })} type="number" required />
                  <Field label="Event ID (Optional)" value={couponForm.event_id} onChange={v => setCouponForm({ ...couponForm, event_id: v })} placeholder="Limit to specific event" />
                </div>
                
                <div className="grid sm:grid-cols-2 gap-4">
                  <Field label="Valid From (Optional)" value={couponForm.valid_from} onChange={v => setCouponForm({ ...couponForm, valid_from: v })} type="datetime-local" />
                  <Field label="Valid Until (Optional)" value={couponForm.valid_until} onChange={v => setCouponForm({ ...couponForm, valid_until: v })} type="datetime-local" />
                </div>
                <button type="submit" className="btn-spot w-full text-sm font-bold mt-2">Create Coupon</button>
              </form>

              <div className="space-y-4">
                <h2 className="font-display text-xl text-paper uppercase tracking-wider mb-2">Active Promo Codes</h2>
                {couponsLoading && <p className="text-xs font-mono text-haze">Loading…</p>}
                {!couponsLoading && coupons.length === 0 && <p className="text-xs font-mono text-haze">No coupons created.</p>}
                
                <div className="space-y-3">
                  {coupons.map((c) => (
                    <div key={c.id} className="border border-white/[0.04] bg-white/[0.01] rounded-xl p-4 flex justify-between items-center gap-4">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-lg text-paper font-bold tracking-widest uppercase">{c.code}</span>
                          <span className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded border ${c.is_active ? 'border-go/20 text-go bg-go/5' : 'border-spot2/20 text-spot2 bg-spot2/5'}`}>
                            {c.is_active ? 'Active' : 'Disabled'}
                          </span>
                        </div>
                        <p className="text-xs text-haze mt-1 font-mono">
                          {c.discount_type === 'percentage' ? `${c.discount_value}% OFF` : `₹${c.discount_value} OFF`} 
                          {c.event_id ? ` · Event: ${c.event_id}` : ' · All Events'}
                        </p>
                        <p className="text-[10px] font-mono text-haze/60 mt-1">
                          Uses: {c.current_uses} / {c.max_uses} (Max {c.max_uses_per_user} per user)
                        </p>
                      </div>
                      <button onClick={() => handleToggleCoupon(c.id, c.is_active)} className="text-xs font-mono uppercase px-3 py-1.5 rounded-lg border border-white/[0.06] text-haze hover:text-paper">
                        {c.is_active ? 'Disable' : 'Enable'}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* 8. Admin Artists Panel */}
          {tab === 'artists' && (
            <div className="space-y-4">
              <h2 className="font-display text-xl text-paper uppercase tracking-wider mb-2">Artist Management</h2>
              {artistsLoading && <p className="text-xs font-mono text-haze">Loading…</p>}
              {!artistsLoading && artists.length === 0 && <p className="text-xs font-mono text-haze">No artists found.</p>}

              <div className="space-y-4">
                {artists.map((artist) => {
                  const isEditing = editingArtistId === artist.artist_id
                  const links = artist.social_links || {}
                  
                  return (
                    <div key={artist.artist_id} className="border border-white/[0.04] bg-white/[0.01] rounded-xl p-5 flex flex-col gap-4">
                      <div className="flex justify-between items-start">
                        <div className="flex gap-4">
                          <div className="w-16 h-16 rounded-full overflow-hidden bg-stage flex-shrink-0 border border-white/[0.05] relative group">
                            {artist.image_url ? (
                              <img src={artist.image_url} alt={artist.name} className="w-full h-full object-cover" />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center font-display text-2xl text-paper/30">{artist.name.charAt(0)}</div>
                            )}
                            {isEditing && (
                              <label className="absolute inset-0 bg-void/60 flex items-center justify-center cursor-pointer opacity-0 group-hover:opacity-100 transition text-[10px] font-mono text-paper text-center">
                                Upload
                                <input
                                  type="file"
                                  accept="image/*"
                                  className="hidden"
                                  onChange={async (e) => {
                                    if (!e.target.files[0]) return
                                    try {
                                      await api.adminUploadArtistImage(artist.artist_id, e.target.files[0])
                                      flash(setMsg, 'Image uploaded successfully')
                                      loadArtists()
                                    } catch (err) {
                                      flash(setError, err.message)
                                    }
                                  }}
                                />
                              </label>
                            )}
                          </div>
                          <div>
                            <h3 className="font-display text-xl text-paper tracking-wide uppercase">{artist.name}</h3>
                            <p className="text-[10px] font-mono text-spot2 mt-1">{artist.artist_id}</p>
                          </div>
                        </div>
                        
                        {!isEditing ? (
                          <button
                            onClick={() => {
                              setEditingArtistId(artist.artist_id)
                              setArtistForm({
                                bio: artist.bio || '',
                                facebook: links.facebook || '',
                                instagram: links.instagram || '',
                                twitter: links.twitter || '',
                                website: links.website || ''
                              })
                            }}
                            className="text-xs font-mono uppercase px-3 py-1.5 rounded-lg border border-white/[0.06] text-haze hover:text-paper"
                          >
                            Edit
                          </button>
                        ) : (
                          <div className="flex gap-2">
                            <button
                              onClick={() => setEditingArtistId(null)}
                              className="text-xs font-mono uppercase px-3 py-1.5 rounded-lg border border-white/[0.06] text-haze hover:text-paper"
                            >
                              Cancel
                            </button>
                            <button
                              onClick={async () => {
                                try {
                                  const payload = {
                                    bio: artistForm.bio,
                                    social_links: {
                                      facebook: artistForm.facebook,
                                      instagram: artistForm.instagram,
                                      twitter: artistForm.twitter,
                                      website: artistForm.website
                                    }
                                  }
                                  await api.adminUpdateArtist(artist.artist_id, payload)
                                  flash(setMsg, 'Artist profile updated.')
                                  setEditingArtistId(null)
                                  loadArtists()
                                } catch (err) {
                                  flash(setError, err.message)
                                }
                              }}
                              className="text-xs font-mono uppercase px-3 py-1.5 rounded-lg border border-go/40 bg-go/10 text-go hover:bg-go/20"
                            >
                              Save
                            </button>
                          </div>
                        )}
                      </div>

                      {isEditing ? (
                        <div className="grid md:grid-cols-2 gap-4 mt-2 border-t border-white/[0.04] pt-4">
                          <div className="md:col-span-2">
                            <label className="block text-[10px] font-mono text-haze mb-1.5 uppercase tracking-wider">Biography</label>
                            <textarea
                              value={artistForm.bio}
                              onChange={(e) => setArtistForm({ ...artistForm, bio: e.target.value })}
                              className="w-full bg-void border border-white/[0.06] rounded-xl px-3 py-2 text-sm text-paper h-24 font-body"
                              placeholder="Artist biography..."
                            />
                          </div>
                          <div>
                            <label className="block text-[10px] font-mono text-haze mb-1.5 uppercase tracking-wider">Instagram URL</label>
                            <input value={artistForm.instagram} onChange={(e) => setArtistForm({ ...artistForm, instagram: e.target.value })} className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper font-mono" />
                          </div>
                          <div>
                            <label className="block text-[10px] font-mono text-haze mb-1.5 uppercase tracking-wider">Twitter URL</label>
                            <input value={artistForm.twitter} onChange={(e) => setArtistForm({ ...artistForm, twitter: e.target.value })} className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper font-mono" />
                          </div>
                          <div>
                            <label className="block text-[10px] font-mono text-haze mb-1.5 uppercase tracking-wider">Facebook URL</label>
                            <input value={artistForm.facebook} onChange={(e) => setArtistForm({ ...artistForm, facebook: e.target.value })} className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper font-mono" />
                          </div>
                          <div>
                            <label className="block text-[10px] font-mono text-haze mb-1.5 uppercase tracking-wider">Website URL</label>
                            <input value={artistForm.website} onChange={(e) => setArtistForm({ ...artistForm, website: e.target.value })} className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper font-mono" />
                          </div>
                        </div>
                      ) : (
                        <div className="mt-2 text-sm text-haze/80 font-body">
                          {artist.bio ? <p className="line-clamp-2">{artist.bio}</p> : <p className="italic text-haze/40">No bio provided.</p>}
                          {Object.values(links).some(Boolean) && (
                            <div className="flex gap-3 mt-3 text-[10px] font-mono text-spot">
                              {Object.entries(links).map(([k, v]) => v ? <a key={k} href={v} target="_blank" rel="noreferrer" className="hover:underline">{k}</a> : null)}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* 9. Admin Venues Panel */}
          {tab === 'venues' && (
            <div className="space-y-4">
              <h2 className="font-display text-xl text-paper uppercase tracking-wider mb-2">Venue Management</h2>
              {venuesLoading && <p className="text-xs font-mono text-haze">Loading…</p>}
              {!venuesLoading && venues.length === 0 && <p className="text-xs font-mono text-haze">No venues found.</p>}

              <div className="space-y-4">
                {venues.map((venue) => {
                  const isEditing = editingVenueId === venue.venue_id
                  
                  return (
                    <div key={venue.venue_id} className="border border-white/[0.04] bg-white/[0.01] rounded-xl p-5 flex flex-col gap-4">
                      <div className="flex justify-between items-start">
                        <div className="flex gap-4">
                          <div className="w-16 h-16 rounded-xl overflow-hidden bg-stage flex-shrink-0 border border-white/[0.05] relative group">
                            {venue.image_url ? (
                              <img src={venue.image_url} alt={venue.name} className="w-full h-full object-cover" />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center font-display text-2xl text-paper/30">{venue.name.charAt(0)}</div>
                            )}
                            {isEditing && (
                              <label className="absolute inset-0 bg-void/60 flex items-center justify-center cursor-pointer opacity-0 group-hover:opacity-100 transition text-[10px] font-mono text-paper text-center">
                                Upload
                                <input
                                  type="file"
                                  accept="image/*"
                                  className="hidden"
                                  onChange={async (e) => {
                                    if (!e.target.files[0]) return
                                    try {
                                      await api.adminUploadVenueImage(venue.venue_id, e.target.files[0])
                                      flash(setMsg, 'Image uploaded successfully')
                                      loadVenues()
                                    } catch (err) {
                                      flash(setError, err.message)
                                    }
                                  }}
                                />
                              </label>
                            )}
                          </div>
                          <div>
                            <h3 className="font-display text-xl text-paper tracking-wide uppercase">{venue.name}</h3>
                            <p className="text-xs text-haze mt-0.5">{venue.city}</p>
                            <p className="text-[10px] font-mono text-spot2 mt-1">{venue.venue_id}</p>
                          </div>
                        </div>
                        
                        {!isEditing ? (
                          <button
                            onClick={() => {
                              setEditingVenueId(venue.venue_id)
                              setVenueForm({
                                address: venue.address || '',
                                capacity: venue.capacity || '',
                                latitude: venue.latitude || '',
                                longitude: venue.longitude || ''
                              })
                            }}
                            className="text-xs font-mono uppercase px-3 py-1.5 rounded-lg border border-white/[0.06] text-haze hover:text-paper"
                          >
                            Edit
                          </button>
                        ) : (
                          <div className="flex gap-2">
                            <button
                              onClick={() => setEditingVenueId(null)}
                              className="text-xs font-mono uppercase px-3 py-1.5 rounded-lg border border-white/[0.06] text-haze hover:text-paper"
                            >
                              Cancel
                            </button>
                            <button
                              onClick={async () => {
                                try {
                                  const payload = {
                                    address: venueForm.address || null,
                                    capacity: venueForm.capacity ? parseInt(venueForm.capacity, 10) : null,
                                    latitude: venueForm.latitude ? parseFloat(venueForm.latitude) : null,
                                    longitude: venueForm.longitude ? parseFloat(venueForm.longitude) : null,
                                  }
                                  await api.adminUpdateVenue(venue.venue_id, payload)
                                  flash(setMsg, 'Venue profile updated.')
                                  setEditingVenueId(null)
                                  loadVenues()
                                } catch (err) {
                                  flash(setError, err.message)
                                }
                              }}
                              className="text-xs font-mono uppercase px-3 py-1.5 rounded-lg border border-go/40 bg-go/10 text-go hover:bg-go/20"
                            >
                              Save
                            </button>
                          </div>
                        )}
                      </div>

                      {isEditing ? (
                        <div className="grid md:grid-cols-2 gap-4 mt-2 border-t border-white/[0.04] pt-4">
                          <div className="md:col-span-2">
                            <label className="block text-[10px] font-mono text-haze mb-1.5 uppercase tracking-wider">Address</label>
                            <input value={venueForm.address} onChange={(e) => setVenueForm({ ...venueForm, address: e.target.value })} className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper font-mono" />
                          </div>
                          <div>
                            <label className="block text-[10px] font-mono text-haze mb-1.5 uppercase tracking-wider">Capacity</label>
                            <input type="number" value={venueForm.capacity} onChange={(e) => setVenueForm({ ...venueForm, capacity: e.target.value })} className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper font-mono" />
                          </div>
                          <div>
                            <label className="block text-[10px] font-mono text-haze mb-1.5 uppercase tracking-wider">Latitude</label>
                            <input type="number" step="any" value={venueForm.latitude} onChange={(e) => setVenueForm({ ...venueForm, latitude: e.target.value })} className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper font-mono" />
                          </div>
                          <div>
                            <label className="block text-[10px] font-mono text-haze mb-1.5 uppercase tracking-wider">Longitude</label>
                            <input type="number" step="any" value={venueForm.longitude} onChange={(e) => setVenueForm({ ...venueForm, longitude: e.target.value })} className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper font-mono" />
                          </div>
                        </div>
                      ) : (
                        <div className="mt-2 text-sm text-haze/80 font-body">
                          {venue.address && <p className="mb-1 text-xs">📍 {venue.address}</p>}
                          {venue.capacity && <p className="mb-1 text-[11px] font-mono opacity-60">Capacity: {venue.capacity}</p>}
                          {venue.latitude != null && <p className="text-[10px] font-mono opacity-40 mt-2">Lat: {venue.latitude}, Lng: {venue.longitude}</p>}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

        </div>

      </div>
    </div>
  )
}

function Field({ label, value, onChange, placeholder, type = 'text', required = false }) {
  return (
    <div>
      <label className="block text-xs font-mono text-haze mb-1.5 uppercase">{label}</label>
      <input
        type={type}
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="field font-mono text-sm py-2.5"
      />
    </div>
  )
}