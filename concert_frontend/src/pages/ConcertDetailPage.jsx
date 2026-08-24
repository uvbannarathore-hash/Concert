import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

const METHODS = [
  { id: 'Card', label: 'Card' },
  { id: 'UPI', label: 'UPI' },
  { id: 'Wallet', label: 'Wallet' },
]

export default function ConcertDetailPage() {
  const { eventId } = useParams()
  const navigate = useNavigate()

  // --- COMPREHENSIVE ADMIN CHECK ---
  const rawUser = localStorage.getItem('user') || localStorage.getItem('admin') || '{}'
  let parsedUser = {}
  try {
    parsedUser = JSON.parse(rawUser)
  } catch (e) {
    parsedUser = {}
  }

  // Token ya User object dono se admin verify karo
  const hasAdminToken = Boolean(localStorage.getItem('admin_token') || localStorage.getItem('adminToken'))
  const isAdmin = Boolean(
    parsedUser?.is_admin === true || 
    parsedUser?.is_admin === 'true' || 
    hasAdminToken ||
    api.getUser?.()?.is_admin === true
  )
  // ---------------------------------

  const [event, setEvent] = useState(null)
  const [tickets, setTickets] = useState([])
  const [selected, setSelected] = useState(null)
  const [seats, setSeats] = useState(1)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('') // '', 'payment', 'booking', 'done'
  const [confirmedId, setConfirmedId] = useState('')
  const [paymentId, setPaymentId] = useState('')

  const [method, setMethod] = useState('Card')
  const [cardNumber, setCardNumber] = useState('')
  const [cardExpiry, setCardExpiry] = useState('')
  const [cardCvv, setCardCvv] = useState('')
  const [upiId, setUpiId] = useState('')

  useEffect(() => {
    api
      .getConcert(eventId)
      .then((data) => {
        setEvent(data.event)
        setTickets(data.ticket_categories || [])
      })
      .catch((err) => setError(err.message))
  }, [eventId])

  function goToPayment() {
    if (!api.isLoggedIn() && !hasAdminToken) {
      navigate('/login')
      return
    }
    if (isAdmin) {
      setError('Admin accounts cannot book tickets. Please use a regular customer account.')
      return
    }
    setError('')
    setStatus('payment')
  }

  function paymentDetailsValid() {
    if (method === 'Card') return cardNumber.length >= 12 && cardExpiry.length >= 4 && cardCvv.length >= 3
    if (method === 'UPI') return upiId.includes('@')
    return true
  }

  async function handlePay() {
    if (isAdmin) {
      setError('Admin accounts cannot book tickets.')
      return
    }
    setError('')
    setStatus('booking')
    await new Promise((r) => setTimeout(r, 1400))
    try {
      const res = await api.createBooking(eventId, selected.category, seats, method)
      setConfirmedId(res.booking_id)
      setPaymentId(res.payment_id)
      setStatus('done')
    } catch (err) {
      setError(err.message)
      setStatus('payment')
    }
  }

  if (error && !event) {
    return <div className="max-w-3xl mx-auto px-6 py-20 text-center text-spot">{error}</div>
  }
  if (!event) {
    return <div className="max-w-3xl mx-auto px-6 py-20 text-haze">Loading…</div>
  }

  const total = selected ? selected.price_inr * seats : 0

  if (status === 'done') {
    return (
      <div className="max-w-xl mx-auto px-6 py-24 text-center">
        <p className="eyebrow mb-4">You're in</p>
        <h1 className="font-display text-5xl mb-4">TICKET LOCKED</h1>
        <p className="text-haze mb-8">
          {seats} × {selected.category} for {event.artist_name} at {event.venue_name}.
        </p>
        <div className="bg-stage border border-edge rounded-2xl p-5 mb-10 text-left space-y-2 font-mono text-sm">
          <div className="flex justify-between"><span className="text-haze">Booking ID</span><span>{confirmedId}</span></div>
          <div className="flex justify-between"><span className="text-haze">Payment ID</span><span className="text-go">{paymentId}</span></div>
          <div className="flex justify-between"><span className="text-haze">Amount paid</span><span className="text-spot2">₹{total}</span></div>
        </div>
        <div className="flex gap-3 justify-center">
          <button onClick={() => navigate('/bookings')} className="btn-spot">View my bookings</button>
          <button onClick={() => navigate('/')} className="btn-ghost">Browse more shows</button>
        </div>
      </div>
    )
  }

  if (status === 'payment' || status === 'booking') {
    return (
      <div className="max-w-md mx-auto px-6 py-14">
        <p className="eyebrow mb-3">Almost there</p>
        <h1 className="font-display text-4xl tracking-wide mb-1">CHECKOUT</h1>
        <p className="text-haze text-sm mb-8">
          Simulated payment — no real card is charged, this is a demo flow.
        </p>

        <div className="bg-stage border border-edge rounded-2xl p-5 mb-6">
          <div className="flex justify-between text-sm mb-1">
            <span className="text-haze">{seats} × {selected.category}</span>
            <span>₹{selected.price_inr} each</span>
          </div>
          <div className="flex justify-between items-center border-t border-edge pt-3 mt-3">
            <span className="font-display text-xl tracking-wide">TOTAL</span>
            <span className="font-display text-2xl text-spot2">₹{total}</span>
          </div>
        </div>

        <div className="flex gap-2 mb-5">
          {METHODS.map((m) => (
            <button
              key={m.id}
              onClick={() => setMethod(m.id)}
              disabled={status === 'booking'}
              className={`flex-1 py-2 rounded-full text-sm font-body border transition ${
                method === m.id ? 'bg-spot text-void border-spot font-bold' : 'border-edge text-haze hover:border-haze'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>

        {method === 'Card' && (
          <div className="space-y-3 mb-6">
            <input
              className="field"
              placeholder="Card number"
              maxLength={19}
              value={cardNumber}
              disabled={status === 'booking'}
              onChange={(e) => setCardNumber(e.target.value.replace(/\D/g, ''))}
            />
            <div className="flex gap-3">
              <input
                className="field"
                placeholder="MM/YY"
                maxLength={5}
                value={cardExpiry}
                disabled={status === 'booking'}
                onChange={(e) => setCardExpiry(e.target.value)}
              />
              <input
                className="field"
                placeholder="CVV"
                maxLength={4}
                value={cardCvv}
                disabled={status === 'booking'}
                onChange={(e) => setCardCvv(e.target.value.replace(/\D/g, ''))}
              />
            </div>
          </div>
        )}

        {method === 'UPI' && (
          <input
            className="field mb-6"
            placeholder="yourname@upi"
            value={upiId}
            disabled={status === 'booking'}
            onChange={(e) => setUpiId(e.target.value)}
          />
        )}

        {method === 'Wallet' && (
          <p className="text-sm text-haze mb-6 bg-stage border border-edge rounded-xl px-4 py-3">
            Demo wallet balance: ₹50,000 — plenty for this booking.
          </p>
        )}

        {error && <p className="text-spot text-sm mb-4">{error}</p>}

        <button
          onClick={handlePay}
          disabled={!paymentDetailsValid() || status === 'booking'}
          className="btn-spot w-full"
        >
          {status === 'booking' ? 'Processing payment…' : `Pay ₹${total}`}
        </button>
        <button
          onClick={() => setStatus('')}
          disabled={status === 'booking'}
          className="text-sm text-haze hover:text-paper mt-4 w-full text-center"
        >
          ← Back to seat selection
        </button>
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
            
            {isAdmin ? (
              <div className="bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-mono py-2 px-4 rounded-xl">
                Admins cannot book tickets
              </div>
            ) : (
              <button onClick={goToPayment} className="btn-spot">
                Proceed to payment
              </button>
            )}
          </div>
        </div>
      )}

      {error && <p className="text-spot mt-4">{error}</p>}
    </div>
  )
}