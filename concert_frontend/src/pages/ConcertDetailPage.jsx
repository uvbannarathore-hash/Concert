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

  const hasAdminToken = Boolean(localStorage.getItem('admin_token') || localStorage.getItem('adminToken'))
  const isAdmin = Boolean(
    parsedUser?.is_admin === true ||
    parsedUser?.is_admin === 'true' ||
    hasAdminToken ||
    api.getUser?.()?.is_admin === true
  )

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
      theme: { color: '#ff3d6e' },
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
        ondismiss: async () => {
          setStatus('')
          try {
            await api.cancelBooking(order.booking_id)
          } catch (e) {
            // best-effort cleanup; ignore
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

  const formatDate = (dateStr) => {
    try {
      const date = new Date(dateStr)
      if (isNaN(date.getTime())) return dateStr
      return date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })
    } catch {
      return dateStr
    }
  }

  if (error && !event) {
    return (
      <div className="max-w-md mx-auto px-6 py-24 text-center">
        <div className="border border-spot/20 bg-spot/5 text-spot rounded-2xl p-6 text-sm font-mono">
          ⚠️ Error fetching concert details: {error}
        </div>
        <button onClick={() => navigate('/')} className="btn-ghost text-xs mt-6">Back to home</button>
      </div>
    )
  }

  if (!event) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-24 flex items-center justify-center">
        <div className="space-y-4 text-center">
          <div className="w-10 h-10 border-4 border-spot border-t-transparent rounded-full animate-spin mx-auto"></div>
          <p className="text-sm font-mono text-haze">Securing server connections...</p>
        </div>
      </div>
    )
  }

  const total = selected ? selected.price_inr * seats : 0

  // --- Success State UI (Styled physical pass stub) ---
  if (status === 'done') {
    return (
      <div className="max-w-md mx-auto px-6 py-16 animate-scale-in">
        <p className="eyebrow text-center mb-2">🎉 TRANSACTION CONFIRMED</p>
        <h1 className="font-display text-4xl text-center text-paper mb-8 uppercase tracking-wide">YOUR PASS IS LOCKED</h1>

        {/* Physical ticket pass representation */}
        <div className="bg-stage rounded-2xl border border-white/[0.04] shadow-2xl overflow-hidden relative">
          
          {/* Top Pass Half */}
          <div className="p-6 relative border-b-2 border-dashed border-void/80 bg-gradient-to-b from-stage2/40 to-stage">
            {/* Cutouts on the sides */}
            <div className="absolute w-6 h-6 rounded-full bg-void -left-3 bottom-[-12px] border-r border-white/[0.04]"></div>
            <div className="absolute w-6 h-6 rounded-full bg-void -right-3 bottom-[-12px] border-l border-white/[0.04]"></div>

            <div className="flex items-start justify-between">
              <span className="text-[10px] font-mono uppercase tracking-wider text-spot bg-spot/5 border border-spot/20 px-2 py-0.5 rounded">
                OFFICIAL ENTRY PASS
              </span>
              <span className="font-mono text-xs text-spot2 font-semibold">₹{total}</span>
            </div>

            <h2 className="font-display text-3xl tracking-wide mt-4 uppercase text-paper leading-tight">{event.artist_name}</h2>
            <p className="text-xs text-haze/80 font-semibold mt-1 flex items-center gap-1">📍 {event.venue_name}, {event.city}</p>
            
            <div className="grid grid-cols-2 gap-4 mt-6 text-left">
              <div>
                <span className="text-[10px] font-mono text-haze/50 block uppercase">DATE</span>
                <span className="text-xs font-semibold text-paper">{event.event_date}</span>
              </div>
              <div>
                <span className="text-[10px] font-mono text-haze/50 block uppercase">TIME</span>
                <span className="text-xs font-semibold text-paper">{event.event_time}</span>
              </div>
            </div>
          </div>

          {/* Bottom Stub Half */}
          <div className="p-6 bg-stage/85 flex flex-col items-center">
            <div className="w-full space-y-2 font-mono text-xs text-haze mb-6">
              <div className="flex justify-between"><span>CATEGORY</span><span className="text-paper font-semibold">{selected.category}</span></div>
              <div className="flex justify-between"><span>TOTAL SEATS</span><span className="text-paper font-semibold">{seats}</span></div>
              <div className="flex justify-between"><span>BOOKING ID</span><span className="text-paper font-semibold">{confirmedId}</span></div>
              <div className="flex justify-between"><span>PAYMENT STATUS</span><span className="text-go font-semibold">SUCCESS</span></div>
            </div>

            {/* Mock Ticket Barcode */}
            <div className="w-full bg-white/5 border border-white/[0.02] p-4 rounded-xl flex flex-col items-center gap-1.5 shadow-inner">
              <div className="h-10 w-full flex justify-between overflow-hidden opacity-80 mix-blend-screen px-4">
                {Array.from({ length: 42 }).map((_, i) => (
                  <div 
                    key={i} 
                    className="bg-paper" 
                    style={{ 
                      width: `${(i % 3 === 0 ? 3 : i % 2 === 0 ? 1 : 2)}px`, 
                      opacity: i % 7 === 0 ? 0.3 : 1 
                    }} 
                  />
                ))}
              </div>
              <span className="text-[10px] font-mono tracking-[0.3em] text-haze/50 mt-1">{confirmedId}</span>
            </div>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row gap-3 mt-8">
          <button onClick={() => navigate('/bookings')} className="btn-spot flex-1 text-sm">View My Bookings</button>
          <button onClick={() => navigate('/')} className="btn-ghost flex-1 text-sm">Browse More Shows</button>
        </div>
      </div>
    )
  }

  // --- Selection State UI (Default layout) ---
  return (
    <div className="max-w-6xl mx-auto px-6 py-12 animate-fade-in-up">
      <div className="grid md:grid-cols-12 gap-8 lg:gap-12">
        
        {/* Left Column: Event details */}
        <div className="md:col-span-7 space-y-6">
          <div className="relative rounded-2xl overflow-hidden shadow-2xl border border-white/[0.04] aspect-[16/10] bg-void">
            {event.image_url ? (
              <img
                src={event.image_url}
                alt={event.artist_name}
                className="w-full h-full object-cover object-center"
              />
            ) : (
              <div className="absolute inset-0 bg-gradient-to-tr from-stage2/40 to-void flex items-center justify-center">
                <span className="font-display text-5xl text-edge">LIVEWIRE</span>
              </div>
            )}
            <div className="absolute inset-0 bg-gradient-to-t from-void via-transparent to-transparent"></div>
          </div>

          <div className="space-y-2">
            <p className="eyebrow">{event.city} · {formatDate(event.event_date)}</p>
            <h1 className="font-display text-5xl sm:text-6xl tracking-wide uppercase text-paper">{event.artist_name}</h1>
            <p className="text-base text-haze flex items-center gap-1">
              📍 {event.venue_name} — {event.event_time}
            </p>
          </div>

          <div className="border-t border-white/[0.04] pt-6">
            <h3 className="font-display text-lg tracking-wider text-paper uppercase mb-3">About this event</h3>
            <p className="text-sm text-haze leading-relaxed">
              Experience the energy live. Ensure you arrive at least 30 minutes early. Food, beverage, and mockups will be available. Pass is digital-only and subject to strict verification on site.
            </p>
          </div>
        </div>

        {/* Right Column: Ticket categories select */}
        <div className="md:col-span-5 space-y-6">
          <div className="bg-stage/20 border border-white/[0.04] p-6 rounded-2xl">
            <h2 className="font-display text-2xl tracking-wide text-paper uppercase mb-4">SELECT CATEGORY</h2>
            
            <div className="space-y-3">
              {tickets.map((t) => {
                const soldOut = t.available_seats <= 0
                const isSelected = selected?.category === t.category
                return (
                  <button
                    key={t.category}
                    disabled={soldOut}
                    onClick={() => setSelected(t)}
                    className={`w-full text-left rounded-xl border p-4 transition-all duration-300 outline-none flex items-center justify-between ${
                      soldOut
                        ? 'border-edge bg-stage/10 opacity-30 cursor-not-allowed'
                        : isSelected
                        ? 'border-spot bg-spot/5 shadow-[0_0_15px_rgba(255,61,110,0.1)]'
                        : 'border-white/[0.06] bg-white/[0.01] hover:border-white/[0.12] hover:bg-white/[0.02]'
                    }`}
                  >
                    <div>
                      <span className="font-display text-lg tracking-wider text-paper uppercase block">{t.category}</span>
                      <span className="text-[10px] text-haze font-mono block mt-0.5">
                        {soldOut ? 'Sold out' : `${t.available_seats} seats remaining`}
                      </span>
                    </div>
                    <span className="font-mono text-base text-spot2 font-semibold">₹{t.price_inr}</span>
                  </button>
                )
              })}
            </div>

            {selected && (
              <div className="border-t border-white/[0.04] pt-6 mt-6 space-y-6 animate-scale-in">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-mono text-haze uppercase tracking-wider">Number of seats</label>
                  <input
                    type="number"
                    min={1}
                    max={selected.available_seats}
                    value={seats}
                    onChange={(e) => setSeats(Math.max(1, Number(e.target.value)))}
                    className="field w-24 text-center font-mono !py-1.5"
                    disabled={status === 'paying'}
                  />
                </div>

                <div className="flex items-end justify-between border-t border-white/[0.04] pt-4">
                  <div>
                    <span className="text-[10px] font-mono text-haze uppercase block">Total Due</span>
                    <span className="font-display text-3xl text-spot2">₹{selected.price_inr * seats}</span>
                  </div>
                  
                  {isAdmin ? (
                    <div className="bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-mono py-2.5 px-4 rounded-xl max-w-[200px]">
                      Admins cannot book tickets
                    </div>
                  ) : (
                    <button onClick={handlePay} disabled={status === 'paying'} className="btn-spot text-sm">
                      {status === 'paying' ? 'Opening Payment…' : `Pay ₹${total}`}
                    </button>
                  )}
                </div>

                {error && (
                  <p className="text-spot text-xs font-mono mt-3 text-right">
                    ❌ {error}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  )
}