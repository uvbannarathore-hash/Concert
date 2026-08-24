import { useEffect, useState } from 'react'
import { adminApi } from '../lib/adminApi'

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
            { id: 'assistant', label: '🤖 AI Agent', icon: '⚡' },
            { id: 'events', label: '📅 Event Setup', icon: '📝' },
            { id: 'pricing', label: '🎟️ Ticket Rates', icon: '🏷️' },
            { id: 'bookings', label: '📋 Bookings List', icon: '🧾' },
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => setTab(item.id)}
              className={`flex items-center gap-3 px-4 py-3 rounded-xl text-xs font-mono uppercase tracking-wider border transition-all duration-300 flex-shrink-0 w-auto md:w-full text-left ${
                tab === item.id 
                  ? 'bg-spot text-void border-spot font-bold shadow-md shadow-spot/10' 
                  : 'border-white/[0.04] bg-white/[0.01] text-haze hover:border-white/[0.1] hover:text-paper'
              }`}
            >
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </div>

        {/* Dynamic Panels (Right Column) */}
        <div className="md:col-span-9 space-y-6">
          
          {/* Messages Alerts */}
          {msg && <div className="border border-go/20 bg-go/5 text-go text-xs font-mono rounded-xl p-4">{msg}</div>}
          {error && <div className="border border-spot/20 bg-spot/5 text-spot text-xs font-mono rounded-xl p-4">{error}</div>}

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
                          ⚙️
                        </span>
                      )}
                    </div>
                  )
                })}
                {chatSending && (
                  <div className="flex gap-3 items-end justify-start animate-pulse">
                    <span className="w-7 h-7 rounded-full border border-spot2/20 bg-spot2/5 text-spot2 font-mono text-xs flex items-center justify-center flex-shrink-0">
                      🤖
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
                    📎 {chatImage.name}
                    <button type="button" onClick={() => setChatImage(null)} className="text-[9px] hover:text-white font-bold">✕</button>
                  </span>
                )}
                {venueLocation && (
                  <span className="flex items-center gap-1.5 text-[10px] font-mono text-spot2 bg-spot2/5 border border-spot2/15 px-2.5 py-1 rounded-md">
                    📍 {venueLocation.name || venueLocation.address.split(',')[0]}
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
                  📎
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
                  📍
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
                  <span className="text-xl">📅</span>
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
                          <p className="text-[11px] text-haze font-mono mt-0.5">
                            📍 {e.venue_name}, {e.city} · 📅 {e.event_date} · 🕒 {e.event_time}
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
                <span className="text-xl">🎟️</span>
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
                        <p className="text-xs text-haze mt-1.5">
                          🎟️ <span className="font-bold text-paper">{eventObj.artist_name || `Ref ID: ${b.event_id}`}</span> · <span className="uppercase">{b.category}</span> · <span className="font-bold text-spot2">{b.seats_booked} seats</span>
                        </p>
                        {eventObj.event_date && (
                          <p className="text-[10px] font-mono text-haze/50 mt-1">
                            📍 {eventObj.venue_name}, {eventObj.city} · 📅 {eventObj.event_date}
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

        </div>

      </div>
    </div>
  )
}

function Field({ label, value, onChange, placeholder, type = 'text' }) {
  return (
    <div>
      <label className="block text-xs font-mono text-haze/70 mb-1.5 uppercase">{label}</label>
      <input
        type={type}
        required
        className="field font-mono text-sm py-2.5"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </div>
  )
}