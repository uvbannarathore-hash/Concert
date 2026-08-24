import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

const METHODS = [
  { id: 'Card', label: '💳 Card' },
  { id: 'UPI', label: '📱 UPI' },
  { id: 'Wallet', label: '👜 Wallet' },
]

export default function ConcertDetailPage() {
  const { eventId } = useParams()
  const navigate = useNavigate()

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
    if (!api.isLoggedIn()) {
      navigate('/login')
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
    setError('')
    setStatus('booking')
    await new Promise((r) => setTimeout(r, 1600))
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

  // Format credit card number for visual display
  const formatCardNumDisplay = (num) => {
    const defaultCard = '•••• •••• •••• ••••'
    if (!num) return defaultCard
    let out = ''
    for (let i = 0; i < 16; i++) {
      if (i > 0 && i % 4 === 0) out += ' '
      out += num[i] || '•'
    }
    return out
  }

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

  // --- Checkout State UI ---
  if (status === 'payment' || status === 'booking') {
    return (
      <div className="max-w-4xl mx-auto px-6 py-12 animate-scale-in">
        <button
          onClick={() => setStatus('')}
          disabled={status === 'booking'}
          className="text-xs text-haze hover:text-paper hover:scale-95 transition-transform inline-flex items-center gap-1 mb-6 outline-none"
        >
          ← Back to selection
        </button>

        <div className="grid md:grid-cols-12 gap-8">
          {/* Form details */}
          <div className="md:col-span-7 bg-stage/20 border border-white/[0.04] p-6 rounded-2xl">
            <p className="eyebrow mb-1">SECURE CHECKOUT</p>
            <h2 className="font-display text-3xl text-paper uppercase mb-6">Payment Method</h2>

            <div className="flex gap-2.5 mb-6">
              {METHODS.map((m) => (
                <button
                  key={m.id}
                  onClick={() => setMethod(m.id)}
                  disabled={status === 'booking'}
                  className={`flex-1 py-2.5 rounded-xl text-xs font-mono uppercase tracking-wider border transition-all duration-300 ${
                    method === m.id 
                      ? 'bg-spot text-void border-spot font-bold shadow-md shadow-spot/10' 
                      : 'border-white/[0.06] bg-white/[0.01] text-haze hover:border-white/[0.1] hover:text-paper'
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>

            {method === 'Card' && (
              <div className="space-y-4 mb-6">
                <div>
                  <label className="block text-xs text-haze/70 font-mono mb-1.5 uppercase">Card Number</label>
                  <input
                    className="field"
                    placeholder="4000 1234 5678 9010"
                    maxLength={16}
                    value={cardNumber}
                    disabled={status === 'booking'}
                    onChange={(e) => setCardNumber(e.target.value.replace(/\D/g, ''))}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs text-haze/70 font-mono mb-1.5 uppercase">Expiry Date</label>
                    <input
                      className="field"
                      placeholder="MM/YY"
                      maxLength={5}
                      value={cardExpiry}
                      disabled={status === 'booking'}
                      onChange={(e) => setCardExpiry(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-haze/70 font-mono mb-1.5 uppercase">CVV</label>
                    <input
                      className="field"
                      placeholder="123"
                      type="password"
                      maxLength={3}
                      value={cardCvv}
                      disabled={status === 'booking'}
                      onChange={(e) => setCardCvv(e.target.value.replace(/\D/g, ''))}
                    />
                  </div>
                </div>
              </div>
            )}

            {method === 'UPI' && (
              <div className="mb-6">
                <label className="block text-xs text-haze/70 font-mono mb-1.5 uppercase">UPI Virtual Payment Address</label>
                <input
                  className="field"
                  placeholder="yourname@upi"
                  value={upiId}
                  disabled={status === 'booking'}
                  onChange={(e) => setUpiId(e.target.value)}
                />
              </div>
            )}

            {method === 'Wallet' && (
              <div className="mb-6 border border-white/[0.04] bg-stage2/40 p-4 rounded-xl flex items-center justify-between">
                <div>
                  <p className="text-xs text-haze/50 uppercase font-mono">WALLET BALANCE</p>
                  <p className="text-2xl font-display text-spot2 mt-0.5">₹50,000</p>
                </div>
                <span className="text-xs text-go font-semibold bg-go/5 border border-go/10 px-2.5 py-1 rounded-full">
                  AUTO-APPROVED
                </span>
              </div>
            )}

            {error && (
              <div className="border border-spot/20 bg-spot/5 text-spot text-xs font-mono rounded-xl p-4 mb-4">
                ❌ Booking Failed: {error}
              </div>
            )}

            <button
              onClick={handlePay}
              disabled={!paymentDetailsValid() || status === 'booking'}
              className="btn-spot w-full text-sm font-bold flex items-center justify-center gap-2"
            >
              {status === 'booking' ? (
                <>
                  <span className="w-4 h-4 border-2 border-void border-t-transparent rounded-full animate-spin"></span>
                  Processing Payment...
                </>
              ) : (
                `Confirm & Pay ₹${total}`
              )}
            </button>
          </div>

          {/* Credit Card mockup visualizer (Right Column) */}
          <div className="md:col-span-5 flex flex-col justify-between">
            {/* Card mockup */}
            {method === 'Card' ? (
              <div className="w-full aspect-[1.586/1] bg-gradient-to-br from-[#1E1B2E] via-[#2E2A40] to-[#FF3D6E]/30 border border-white/[0.08] rounded-2xl p-6 shadow-2xl relative flex flex-col justify-between overflow-hidden animate-scale-in">
                {/* Visual glow overlay */}
                <div className="absolute right-[-10%] top-[-10%] w-32 h-32 bg-spot/25 rounded-full blur-3xl" />
                <div className="absolute left-[-5%] bottom-[-5%] w-24 h-24 bg-spot2/10 rounded-full blur-2xl" />

                <div className="flex items-start justify-between z-10">
                  <div className="w-10 h-7 bg-white/10 rounded-md border border-white/20 relative overflow-hidden flex items-center justify-center">
                    <div className="w-4 h-5 border border-white/20 rounded-sm absolute left-1"></div>
                    <div className="w-4 h-5 border border-white/20 rounded-sm absolute right-1"></div>
                  </div>
                  <span className="font-display text-xl text-paper tracking-widest opacity-80">LIVEWIRE</span>
                </div>

                <div className="z-10 mt-6">
                  <p className="text-haze/40 text-[9px] font-mono uppercase tracking-widest">Card Number</p>
                  <p className="text-xl sm:text-2xl font-mono tracking-widest text-paper mt-0.5">
                    {formatCardNumDisplay(cardNumber)}
                  </p>
                </div>

                <div className="flex justify-between items-end z-10 mt-4">
                  <div>
                    <p className="text-haze/40 text-[8px] font-mono uppercase tracking-widest">Expiry</p>
                    <p className="text-xs font-mono text-paper mt-0.5">{cardExpiry || 'MM/YY'}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-haze/40 text-[8px] font-mono uppercase tracking-widest">CVV</p>
                    <p className="text-xs font-mono text-paper mt-0.5">{cardCvv ? '•••' : '123'}</p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="w-full border border-white/[0.04] bg-stage2/10 rounded-2xl p-6 flex flex-col gap-4 text-left animate-scale-in">
                <span className="text-3xl">🛒</span>
                <p className="font-display text-xl text-paper uppercase">Order Summary</p>
                <div className="text-xs space-y-1.5 font-mono text-haze">
                  <div className="flex justify-between"><span>EVENT</span><span className="text-paper truncate max-w-[150px]">{event.artist_name}</span></div>
                  <div className="flex justify-between"><span>SEATS</span><span className="text-paper">{seats} × {selected.category}</span></div>
                  <div className="flex justify-between"><span>CITY</span><span className="text-paper">{event.city}</span></div>
                </div>
              </div>
            )}

            {/* Receipt Summary details */}
            <div className="bg-stage border border-white/[0.04] p-5 rounded-2xl mt-6">
              <p className="text-xs font-mono text-haze uppercase tracking-wider mb-3">Order Receipt</p>
              <div className="space-y-2 text-sm text-haze">
                <div className="flex justify-between"><span>Category</span><span>{selected.category}</span></div>
                <div className="flex justify-between"><span>Price per seat</span><span>₹{selected.price_inr}</span></div>
                <div className="flex justify-between"><span>Quantity</span><span>{seats}</span></div>
                <div className="flex justify-between border-t border-white/[0.04] pt-3 mt-3">
                  <span className="font-display text-lg text-paper uppercase tracking-wider">Payable Total</span>
                  <span className="font-display text-xl text-spot2">₹{total}</span>
                </div>
              </div>
            </div>
          </div>

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
                  />
                </div>

                <div className="flex items-end justify-between border-t border-white/[0.04] pt-4">
                  <div>
                    <span className="text-[10px] font-mono text-haze uppercase block">Total Due</span>
                    <span className="font-display text-3xl text-spot2">₹{selected.price_inr * seats}</span>
                  </div>
                  
                  <button onClick={goToPayment} className="btn-spot text-sm">
                    Book Tickets
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

      </div>
    </div>
  )
}
