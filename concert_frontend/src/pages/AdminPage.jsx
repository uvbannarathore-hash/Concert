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
    { role: 'assistant', text: "I'm your admin assistant. Ask me to create, update, cancel, or delete events, check seat availability, or pull revenue reports. You can also attach an image (📎) when creating or updating an event to set its poster." },
  ])
  const [chatInput, setChatInput] = useState('')
  const [chatImage, setChatImage] = useState(null)
  const [chatSending, setChatSending] = useState(false)

  function flash(setter, text) {
    setter(text)
    setTimeout(() => setter(''), 3500)
  }

  async function handleCreateEvent(e) {
    e.preventDefault()
    setError('')
    try {
      const res = await adminApi.createEvent(eventForm)
      flash(setMsg, `Event created: ${res.event_id}`)
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
      flash(setMsg, 'Ticket category added')
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

    setChatMessages((m) => [...m, { role: 'user', text: chatImage ? `${text} 📎 ${chatImage.name}` : text }])
    setChatInput('')
    setChatSending(true)
    setError('')

    const imageToSend = chatImage

    try {
      const res = await adminApi.chat(text, imageToSend)
      setChatMessages((m) => [...m, { role: 'assistant', text: res.reply }])
    } catch (err) {
      if (err.message.includes('403')) setForbidden(true)
      setChatMessages((m) => [...m, { role: 'assistant', text: `Error: ${err.message}` }])
    } finally {
      setChatSending(false)
      setChatImage(null)
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
        // most recent first
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
        <p className="eyebrow mb-3">Backstage only</p>
        <h1 className="font-display text-4xl mb-4">NOT ON THE LIST</h1>
        <p className="text-haze">
          Your account doesn't have admin access. Ask an existing admin to flip your
          <code className="mx-1 px-2 py-0.5 bg-stage rounded font-mono text-sm">is_admin</code>
          flag in Supabase.
        </p>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-14">
      <p className="eyebrow mb-3">Backstage</p>
      <h1 className="font-display text-5xl tracking-wide mb-8">ADMIN PANEL</h1>

      <div className="flex gap-2 mb-8">
        {['assistant', 'events', 'pricing', 'bookings'].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-full text-sm font-body border capitalize transition ${
              tab === t ? 'bg-spot text-void border-spot font-bold' : 'border-edge text-haze hover:border-haze'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {msg && <p className="text-sm text-go bg-go/10 border border-go/30 rounded-lg px-3 py-2 mb-4">{msg}</p>}
      {error && <p className="text-sm text-spot bg-spot/10 border border-spot/30 rounded-lg px-3 py-2 mb-4">{error}</p>}

      {tab === 'assistant' && (
        <div className="bg-stage border border-edge rounded-2xl p-5 flex flex-col h-[60vh]">
          <div className="flex-1 overflow-y-auto space-y-3 pr-1 mb-4">
            {chatMessages.map((m, i) => (
              <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap leading-relaxed ${
                    m.role === 'user'
                      ? 'bg-spot text-void font-medium rounded-br-sm'
                      : 'bg-stage2 border border-edge text-paper rounded-bl-sm'
                  }`}
                >
                  {m.text}
                </div>
              </div>
            ))}
            {chatSending && (
              <div className="flex justify-start">
                <div className="bg-stage2 border border-edge rounded-2xl rounded-bl-sm px-4 py-3 text-sm text-haze">
                  Working on it…
                </div>
              </div>
            )}
          </div>

          {chatImage && (
            <div className="flex items-center gap-2 mb-2 text-xs text-haze bg-stage2 border border-edge rounded-lg px-3 py-2 w-fit">
              <span>📎 {chatImage.name}</span>
              <button
                type="button"
                onClick={() => setChatImage(null)}
                className="text-spot hover:underline"
              >
                Remove
              </button>
            </div>
          )}

          <form onSubmit={handleAdminChatSend} className="flex gap-2">
            <input
              className="field"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              placeholder='e.g. "Create a Diljit Dosanjh concert in Pune on 10 Nov, 8 PM"'
            />
            <label className="btn-spot !px-3 cursor-pointer flex items-center" title="Attach event poster image">
              📎
              <input
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => setChatImage(e.target.files[0] || null)}
              />
            </label>
            <button type="submit" disabled={chatSending} className="btn-spot !px-6">
              Send
            </button>
          </form>
        </div>
      )}

      {tab === 'events' && (
        <div className="space-y-6">
          <form onSubmit={handleCreateEvent} className="bg-stage border border-edge rounded-2xl p-6 space-y-4">
            <h2 className="font-display text-xl tracking-wide mb-2">NEW LISTING</h2>
            <div>
              <label className="block text-sm text-haze mb-1.5">Type</label>
              <select
                className="field"
                value={eventForm.event_type}
                onChange={(e) => setEventForm({ ...eventForm, event_type: e.target.value })}
              >
                {EVENT_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div className="grid sm:grid-cols-2 gap-4">
              <Field label={eventForm.event_type === 'Movie' ? 'Movie Title' : 'Artist / Title'} value={eventForm.artist_name} onChange={(v) => setEventForm({ ...eventForm, artist_name: v })} placeholder="Arijit Singh" />
              <Field label="Artist/Title ID" value={eventForm.artist_id} onChange={(v) => setEventForm({ ...eventForm, artist_id: v })} placeholder="ART01" />
              <Field label="Venue ID" value={eventForm.venue_id} onChange={(v) => setEventForm({ ...eventForm, venue_id: v })} placeholder="VEN01" />
              <Field label="Venue Name" value={eventForm.venue_name} onChange={(v) => setEventForm({ ...eventForm, venue_name: v })} placeholder="DY Patil Stadium" />
              <Field label="City" value={eventForm.city} onChange={(v) => setEventForm({ ...eventForm, city: v })} placeholder="Mumbai" />
              <Field label="Date" value={eventForm.event_date} onChange={(v) => setEventForm({ ...eventForm, event_date: v })} placeholder="2026-12-20" />
              <Field label="Time" value={eventForm.event_time} onChange={(v) => setEventForm({ ...eventForm, event_time: v })} placeholder="7:00 PM" />
            </div>
            <button type="submit" className="btn-spot">Create event</button>
          </form>

          {/* Past / Completed events */}
          <div className="bg-stage border border-edge rounded-2xl p-6">
            <button
              type="button"
              onClick={() => setShowPastEvents((s) => !s)}
              className="flex items-center justify-between w-full text-left"
            >
              <h2 className="font-display text-xl tracking-wide">PAST EVENTS</h2>
              <span className="text-haze text-sm">{showPastEvents ? 'Hide ▲' : 'Show ▼'}</span>
            </button>

            {showPastEvents && (
              <div className="mt-4 space-y-3">
                {pastEventsLoading && <p className="text-haze text-sm">Loading past events…</p>}
                {!pastEventsLoading && pastEvents.length === 0 && (
                  <p className="text-haze text-sm">No past events yet.</p>
                )}
                {pastEvents.map((e) => (
                  <div
                    key={e.event_id}
                    className="border border-edge rounded-xl p-4 flex justify-between flex-wrap gap-2"
                  >
                    <div>
                      <p className="font-body font-bold">{e.artist_name}</p>
                      <p className="text-xs text-haze">
                        {e.venue_name}, {e.city} · {e.event_date} · {e.event_time}
                      </p>
                    </div>
                    <span className="text-xs font-mono text-haze self-center">{e.status}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'pricing' && (
        <form onSubmit={handleAddTicket} className="bg-stage border border-edge rounded-2xl p-6 space-y-4">
          <h2 className="font-display text-xl tracking-wide mb-2">ADD TICKET CATEGORY</h2>
          <div className="grid sm:grid-cols-2 gap-4">
            <Field label="Event ID" value={ticketForm.event_id} onChange={(v) => setTicketForm({ ...ticketForm, event_id: v })} placeholder="EVT01" />
            <Field label="Category" value={ticketForm.category} onChange={(v) => setTicketForm({ ...ticketForm, category: v })} placeholder="VIP / Gold / Silver / General" />
            <Field label="Price (INR)" value={ticketForm.price_inr} onChange={(v) => setTicketForm({ ...ticketForm, price_inr: v })} placeholder="5000" type="number" />
            <Field label="Total Seats" value={ticketForm.total_seats} onChange={(v) => setTicketForm({ ...ticketForm, total_seats: v })} placeholder="2000" type="number" />
          </div>
          <button type="submit" className="btn-spot">Add category</button>
        </form>
      )}

      {tab === 'bookings' && (
        <div className="space-y-3">
          {bookings.length === 0 && <p className="text-haze">No bookings yet.</p>}
          {bookings.map((b) => (
            <div key={b.booking_id} className="bg-stage border border-edge rounded-xl p-4 flex justify-between flex-wrap gap-2">
              <div>
                <p className="font-mono text-sm">{b.booking_id}</p>
                <p className="text-xs text-haze">{b.event_id} · {b.category} · {b.seats_booked} seats</p>
              </div>
              <div className="text-right">
                <p className="text-xs font-mono text-haze">{b.user_id}</p>
                <p className="text-xs text-spot2">{b.status}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Field({ label, value, onChange, placeholder, type = 'text' }) {
  return (
    <div>
      <label className="block text-sm text-haze mb-1.5">{label}</label>
      <input
        type={type}
        required
        className="field"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </div>
  )
}