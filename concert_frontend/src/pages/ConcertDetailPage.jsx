import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

export default function ConcertDetailPage() {
  const { eventId } = useParams()
  const navigate = useNavigate()

  const [event, setEvent] = useState(null)
  const [tickets, setTickets] = useState([])
  const [selected, setSelected] = useState(null)
  const [seats, setSeats] = useState(1)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('') // '', 'booking', 'done'
  const [confirmedId, setConfirmedId] = useState('')

  useEffect(() => {
    api
      .getConcert(eventId)
      .then((data) => {
        setEvent(data.event)
        setTickets(data.ticket_categories || [])
      })
      .catch((err) => setError(err.message))
  }, [eventId])

  async function handleBook() {
    if (!api.isLoggedIn()) {
      navigate('/login')
      return
    }
    setError('')
    setStatus('booking')
    try {
      const res = await api.createBooking(eventId, selected.category, seats)
      setConfirmedId(res.booking_id)
      setStatus('done')
    } catch (err) {
      setError(err.message)
      setStatus('')
    }
  }

  if (error && !event) {
    return <div className="max-w-3xl mx-auto px-6 py-20 text-center text-spot">{error}</div>
  }
  if (!event) {
    return <div className="max-w-3xl mx-auto px-6 py-20 text-haze">Loading…</div>
  }

  if (status === 'done') {
    return (
      <div className="max-w-xl mx-auto px-6 py-24 text-center">
        <p className="eyebrow mb-4">You're in</p>
        <h1 className="font-display text-5xl mb-4">TICKET LOCKED</h1>
        <p className="text-haze mb-8">
          {seats} × {selected.category} for {event.artist_name} at {event.venue_name}.
        </p>
        <p className="font-mono text-sm text-spot2 mb-10">Booking ID: {confirmedId}</p>
        <div className="flex gap-3 justify-center">
          <button onClick={() => navigate('/bookings')} className="btn-spot">View my bookings</button>
          <button onClick={() => navigate('/')} className="btn-ghost">Browse more shows</button>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-14">
      <p className="eyebrow mb-3">{event.city} · {event.event_date}</p>
      <h1 className="font-display text-6xl tracking-wide mb-2">{event.artist_name}</h1>
      <p className="text-haze text-lg mb-10">{event.venue_name} — {event.event_time}</p>

      <h2 className="font-display text-2xl tracking-wide mb-4">SELECT YOUR SPOT</h2>
      <div className="grid sm:grid-cols-2 gap-3 mb-8">
        {tickets.map((t) => {
          const soldOut = t.available_seats <= 0
          const isSelected = selected?.category === t.category
          return (
            <button
              key={t.category}
              disabled={soldOut}
              onClick={() => setSelected(t)}
              className={`text-left rounded-xl border p-4 transition ${
                soldOut
                  ? 'border-edge bg-stage/50 opacity-40 cursor-not-allowed'
                  : isSelected
                  ? 'border-spot bg-spot/10'
                  : 'border-edge bg-stage hover:border-haze'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-display text-xl tracking-wide">{t.category}</span>
                <span className="font-mono text-spot2">₹{t.price_inr}</span>
              </div>
              <span className="text-xs text-haze font-mono">
                {soldOut ? 'Sold out' : `${t.available_seats} seats left`}
              </span>
            </button>
          )
        })}
      </div>

      {selected && (
        <div className="bg-stage border border-edge rounded-2xl p-6 flex items-end justify-between flex-wrap gap-4">
          <div>
            <label className="block text-sm text-haze mb-2">Number of seats</label>
            <input
              type="number"
              min={1}
              max={selected.available_seats}
              value={seats}
              onChange={(e) => setSeats(Math.max(1, Number(e.target.value)))}
              className="field w-28"
            />
          </div>
          <div className="text-right">
            <p className="text-xs text-haze font-mono mb-1">Total</p>
            <p className="font-display text-3xl text-spot2 mb-3">₹{selected.price_inr * seats}</p>
            <button onClick={handleBook} disabled={status === 'booking'} className="btn-spot">
              {status === 'booking' ? 'Booking…' : 'Confirm booking'}
            </button>
          </div>
        </div>
      )}

      {error && <p className="text-spot mt-4">{error}</p>}
    </div>
  )
}
