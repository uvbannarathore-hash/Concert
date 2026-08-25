import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

function loadRazorpayScript() {
  return new Promise((resolve) => {
    if (window.Razorpay) {
      resolve(true)
      return
    }
    const script = document.createElement('script')
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'
    script.onload = () => resolve(true)
    script.onerror = () => resolve(false)
    document.body.appendChild(script)
  })
}

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
  // Note: this is a display-only convenience check (localStorage is
  // client-controlled and can be tampered with). The real enforcement
  // happens server-side in /bookings/create-order and in the
  // book_ticket_transaction Postgres function, so this can never be
  // bypassed just by editing devtools/localStorage.
  // ---------------------------------

  const [event, setEvent] = useState(null)
  const [tickets, setTickets] = useState([])
  const [selected, setSelected] = useState(null)
  const [seats, setSeats] = useState(1)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('') // '', 'paying', 'done'
  const [confirmedId, setConfirmedId] = useState('')
  const [paymentId, setPaymentId] = useState('')

  useEffect(() => {
    api
      .getConcert(eventId)
      .then((data) => {
        setEvent(data.event)
        setTickets(data.ticket_categories || [])
      })
      .catch((err) => setError(err.message))
  }, [eventId])

  async function handlePay() {
    if (!api.isLoggedIn() && !hasAdminToken) {
      navigate('/login')
      return
    }
    if (isAdmin) {
      setError('Admin accounts cannot book tickets. Please use a regular customer account.')
      return
    }

    setError('')
    setStatus('paying')

    const scriptReady = await loadRazorpayScript()
    if (!scriptReady) {
      setError('Could not load payment gateway. Check your connection and try again.')
      setStatus('')
      return
    }

    let order
    try {
      order = await api.createOrder(eventId, selected.category, seats)
    } catch (err) {
      setError(err.message)
      setStatus('')
      return
    }

    const rzp = new window.Razorpay({
      key: order.razorpay_key_id,
      amount: order.amount,
      currency: order.currency,
      name: event.artist_name,
      description: `${seats} × ${selected.category} — ${event.venue_name}`,
      order_id: order.razorpay_order_id,
      prefill: {
        email: api.currentEmail?.() || '',
      },
      theme: { color: '#e11d48' },
      handler: async (response) => {
        try {
          const res = await api.verifyPayment({
            booking_id: order.booking_id,
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          })
          setConfirmedId(res.booking_id)
          setPaymentId(res.payment_id)
          setStatus('done')
        } catch (err) {
          setError(err.message)
          setStatus('')
        }
      },
      modal: {
        // User closed the widget without paying. The booking + seat hold
        // stay 'Pending' server-side - release the seats now instead of
        // leaving them stuck, so other users can book them again.
        ondismiss: async () => {
          setStatus('')
          try {
            await api.cancelBooking(order.booking_id)
          } catch (e) {
            // best-effort cleanup; ignore failures here
          }
        },
      },
    })

    rzp.on('payment.failed', () => {
      setError('Payment failed. Please try again.')
      setStatus('')
    })

    rzp.open()
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
              disabled={status === 'paying'}
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
              <button onClick={handlePay} disabled={status === 'paying'} className="btn-spot">
                {status === 'paying' ? 'Opening payment…' : `Pay ₹${total}`}
              </button>
            )}
          </div>
        </div>
      )}

      {error && <p className="text-spot mt-4">{error}</p>}
    </div>
  )
}