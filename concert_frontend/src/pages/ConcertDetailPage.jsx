import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import { api, getPublicPassUrl } from '../lib/api'
import DigitalPassModal from '../components/DigitalPassModal'

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

  // --- Real admin check (matches NavBar/ChatWidget/VoiceWidget) ---
  // The old check here read localStorage keys ('user', 'admin',
  // 'admin_token', 'adminToken') and api.getUser?.() - none of which
  // are ever actually set by api.js's login/setSession (only
  // access_token/user_id/email are stored), so it was always false
  // regardless of real admin status. That let an admin's own account
  // sail through the customer booking UI with no warning, only to be
  // rejected server-side (403) once they hit Pay - confusing, and it
  // also meant the seat map/price never accounted for admin-only
  // restrictions client-side. isAdmin now starts as null ("not
  // checked yet") so the Pay button/seat map stay disabled until we
  // have a real answer, instead of flashing "allowed" first.
  const [isAdmin, setIsAdmin] = useState(null)

  useEffect(() => {
    if (!api.isLoggedIn()) {
      setIsAdmin(false)
      return
    }
    api.myProfile().then((p) => setIsAdmin(!!p?.is_admin)).catch(() => setIsAdmin(false))
  }, [])

  const [event, setEvent] = useState(null)
  const [tickets, setTickets] = useState([])
  const [selected, setSelected] = useState(null)
  const [seats, setSeats] = useState(1)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('') // '', 'paying', 'done'
  const [confirmedId, setConfirmedId] = useState('')
  const [showPassModal, setShowPassModal] = useState(false)
  const [paymentId, setPaymentId] = useState('')

  // --- Seat map (interactive picker) state — only used for events where
  // an admin has built a seat layout (see AdminPage's Seat Layout tab).
  // Events with no rows defined fall back to the plain quantity picker
  // below, completely unchanged from before this feature existed.
  const [seatMap, setSeatMap] = useState(null)     // { seats: [...], has_seat_map }
  const [selectedSeatIds, setSelectedSeatIds] = useState([])
  const [selectedSeatCategory, setSelectedSeatCategory] = useState(null)

  useEffect(() => {
    api
      .getConcert(eventId)
      .then((data) => {
        setEvent(data.event)
        setTickets(data.ticket_categories || [])
      })
      .catch((err) => setError(err.message))

    api
      .getSeatMap(eventId)
      .then((data) => setSeatMap(data))
      .catch(() => setSeatMap({ seats: [], has_seat_map: false }))
  }, [eventId])

  const hasSeatMap = seatMap?.has_seat_map === true

  function refreshSeatMap() {
    api.getSeatMap(eventId).then((data) => setSeatMap(data)).catch(() => {})
  }

  function toggleSeat(seat) {
    if (seat.status !== 'Available') return

    const already = selectedSeatIds.includes(seat.id)

    if (!already && selectedSeatCategory && seat.category !== selectedSeatCategory) {
      setError(`You can only select seats from one category at a time (currently: ${selectedSeatCategory}). Deselect those first to switch categories.`)
      return
    }

    if (!already && selectedSeatIds.length >= 20) {
      setError('You can select a maximum of 20 seats per booking.')
      return
    }

    setError('')

    setSelectedSeatIds((ids) => {
      if (already) return ids.filter((id) => id !== seat.id)
      return [...ids, seat.id]
    })

    if (already) {
      if (selectedSeatIds.length === 1) setSelectedSeatCategory(null)
    } else {
      setSelectedSeatCategory(seat.category)
    }
  }

  // Derived from selectedSeatIds + the seat map data, rather than kept as
  // its own state - see the note in toggleSeat above for why.
  const selectedSeatLabels = selectedSeatIds
    .map((id) => {
      const s = seatMap?.seats?.find((s) => s.id === id)
      return s ? { id, label: `${s.seat_row}${s.seat_number}` } : null
    })
    .filter(Boolean)

  // Admins type the category name separately in two different forms (the
  // Pricing tab, and the Seat Layout Builder's free-text "Category"
  // field) - a mismatch in case/spacing between them (e.g. "Gold" vs
  // "GOLD") means the exact-match lookup below would silently find no
  // price and show ₹0. Match case/whitespace-insensitively so a seat
  // row's category still finds its price even if it wasn't typed
  // identically everywhere.
  function findTicketFor(category) {
    if (!category) return undefined
    const needle = category.trim().toLowerCase()
    return tickets.find((t) => (t.category || '').trim().toLowerCase() === needle)
  }

  const seatCategoryPrice = hasSeatMap && selectedSeatCategory
    ? findTicketFor(selectedSeatCategory)?.price_inr || 0
    : 0

  async function handlePay() {
    if (!api.isLoggedIn()) {
      navigate('/login')
      return
    }
    if (isAdmin !== false) {
      // Covers both isAdmin === true (real admin) and isAdmin === null
      // (profile check hasn't resolved yet) - never let a booking
      // through until we've positively confirmed the user isn't an
      // admin, matching what the server enforces anyway.
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
      if (hasSeatMap) {
        await api.lockSeats(eventId, selectedSeatIds)
        order = await api.createOrderSeats(eventId, selectedSeatIds)
      } else {
        order = await api.createOrder(eventId, selected.category, seats)
      }
    } catch (err) {
      setError(err.message)
      setStatus('')
      if (hasSeatMap) {
        // Someone likely grabbed one of these seats first — refresh so the
        // user sees current availability instead of retrying blindly.
        refreshSeatMap()
        setSelectedSeatIds([])
        setSelectedSeatCategory(null)
      }
      return
    }

    const bookingCategory = hasSeatMap ? selectedSeatCategory : selected.category
    const bookingSeatCount = hasSeatMap ? selectedSeatIds.length : seats

    const rzp = new window.Razorpay({
      key: order.razorpay_key_id,
      amount: order.amount,
      currency: order.currency,
      name: event.artist_name,
      description: `${bookingSeatCount} × ${bookingCategory} — ${event.venue_name}`,
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
            // Cancelling the booking also releases the specific seats back
            // to Available via trg_restore_specific_seats, same trigger
            // pattern the plain category flow already relied on.
            await api.cancelBooking(order.booking_id)
          } catch (e) {
            // best-effort cleanup; ignore
          }
          if (hasSeatMap) refreshSeatMap()
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

  const total = hasSeatMap ? seatCategoryPrice * selectedSeatIds.length : (selected ? selected.price_inr * seats : 0)
  const canPay = hasSeatMap ? selectedSeatIds.length > 0 : Boolean(selected)
  const bookedCategory = hasSeatMap ? selectedSeatCategory : selected?.category
  const bookedSeatCount = hasSeatMap ? selectedSeatIds.length : seats

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
              <div className="flex justify-between"><span>CATEGORY</span><span className="text-paper font-semibold">{bookedCategory}</span></div>
              {hasSeatMap && selectedSeatLabels.length > 0 && (
                <div className="flex justify-between"><span>SEATS</span><span className="text-paper font-semibold">{selectedSeatLabels.map((s) => s.label).join(', ')}</span></div>
              )}
              <div className="flex justify-between"><span>TOTAL SEATS</span><span className="text-paper font-semibold">{bookedSeatCount}</span></div>
              <div className="flex justify-between"><span>BOOKING ID</span><span className="text-paper font-semibold">{confirmedId}</span></div>
              <div className="flex justify-between"><span>PAYMENT STATUS</span><span className="text-go font-semibold">SUCCESS</span></div>
            </div>

            {/* Scannable Gate Pass QR Code Box */}
            <div className="w-full bg-white/[0.03] border border-white/[0.06] p-5 rounded-2xl flex flex-col items-center gap-3 shadow-inner">
              <div className="p-3 bg-white rounded-xl shadow-md">
                <QRCodeSVG
                  value={getPublicPassUrl(confirmedId)}
                  size={140}
                  level="H"
                  fgColor="#0B0A10"
                  bgColor="#FFFFFF"
                />
              </div>
              <div className="text-center space-y-1">
                <span className="text-xs font-mono font-bold tracking-widest text-paper uppercase block">{confirmedId}</span>
                <span className="text-[10px] text-haze font-mono block">Scan with camera for turnstile entry verification</span>
              </div>
              <button
                onClick={() => setShowPassModal(true)}
                className="text-xs font-mono text-spot hover:text-white uppercase tracking-wider font-bold transition flex items-center gap-1.5 mt-1"
              >
                <span>Open Digital Pass Modal</span>
                <span>↗</span>
              </button>
            </div>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row gap-3 mt-8">
          <Link to={`/ticket/${confirmedId}`} className="btn-spot flex-1 text-sm text-center">
            View Official Pass Page →
          </Link>
          <button onClick={() => navigate('/bookings')} className="btn-ghost flex-1 text-sm">
            My Bookings List
          </button>
        </div>
        {/* Digital Pass Modal */}
        <DigitalPassModal
          isOpen={showPassModal}
          onClose={() => setShowPassModal(false)}
          booking={{
            booking_id: confirmedId,
            category: bookedCategory || 'General',
            seats_booked: bookedSeatCount,
            status: 'Confirmed',
            event: event,
          }}
        />
      </div>
    )
  }

  // Group seat map rows by category then by row letter, for rendering.
  const seatsByCategory = {}
  if (hasSeatMap) {
    for (const s of seatMap.seats) {
      if (!seatsByCategory[s.category]) seatsByCategory[s.category] = {}
      if (!seatsByCategory[s.category][s.seat_row]) seatsByCategory[s.category][s.seat_row] = []
      seatsByCategory[s.category][s.seat_row].push(s)
    }
  }

  function seatButtonClasses(seat) {
    const isSelected = selectedSeatIds.includes(seat.id)
    if (isSelected)
      return 'border-green-400 bg-green-400/25 text-green-300 ring-1 ring-green-400/50 scale-105'
    if (seat.status === 'Booked')
      return 'border-white/10 bg-white/[0.04] text-white/20 cursor-not-allowed'
    if (seat.status === 'Locked')
      return 'border-amber-500/40 bg-amber-500/10 text-amber-400/50 cursor-not-allowed'
    return 'border-white/30 bg-white/[0.04] text-white/70 hover:border-green-400/60 hover:bg-green-400/10 hover:text-green-300 cursor-pointer'
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

          {/* --- Interactive Seat Map (only for events with a defined layout) --- */}
          {hasSeatMap && (
            <div className="border-t border-white/[0.04] pt-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-display text-lg tracking-wider text-paper uppercase">Select Your Seats</h3>
                <button onClick={refreshSeatMap} className="text-[10px] font-mono text-haze hover:text-paper uppercase">🔄 Refresh</button>
              </div>

              <div className="space-y-6">
                {Object.entries(seatsByCategory).map(([category, rows]) => {
                  const price = findTicketFor(category)?.price_inr
                  return (
                    <div key={category}>
                      <p className="text-xs font-mono uppercase tracking-wider text-spot2 mb-2">
                        ₹{price} {category.toUpperCase()} ROWS
                      </p>
                      <div className="space-y-2">
                        {Object.entries(rows).sort(([a], [b]) => a.localeCompare(b)).map(([row, rowSeats]) => (
                          <div key={row} className="flex items-center gap-3 min-w-0">
                            <span className="text-xs font-mono font-bold text-amber-400 w-5 shrink-0 text-right select-none">{row}</span>
                            <div className="flex flex-wrap gap-1.5">
                              {rowSeats.sort((a, b) => a.seat_number - b.seat_number).map((seat) => {
                                const isBooked = seat.status === 'Booked'
                                return (
                                  <button
                                    key={seat.id}
                                    type="button"
                                    onClick={() => toggleSeat(seat)}
                                    disabled={seat.status !== 'Available' && !selectedSeatIds.includes(seat.id)}
                                    title={isBooked ? 'Sold' : seat.status}
                                    className={`relative w-7 h-7 text-[9px] font-mono rounded border flex items-center justify-center transition-all duration-150 ${seatButtonClasses(seat)}`}
                                  >
                                    {isBooked ? (
                                      <svg viewBox="0 0 10 10" className="w-3 h-3 opacity-40" fill="none" stroke="currentColor" strokeWidth="2">
                                        <line x1="2" y1="2" x2="8" y2="8" />
                                        <line x1="8" y1="2" x2="2" y2="8" />
                                      </svg>
                                    ) : (
                                      seat.seat_number
                                    )}
                                  </button>
                                )
                              })}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )
                })}
              </div>

              <div className="flex flex-wrap gap-5 mt-6 pt-4 border-t border-white/[0.06] text-[11px] font-mono">
                <span className="flex items-center gap-2 text-white/60">
                  <span className="w-5 h-5 rounded border border-white/30 bg-white/[0.04] flex items-center justify-center text-[8px] text-white/60">8</span>
                  Available
                </span>
                <span className="flex items-center gap-2 text-white/60">
                  <span className="w-5 h-5 rounded border border-white/10 bg-white/[0.04] flex items-center justify-center">
                    <svg viewBox="0 0 10 10" className="w-2.5 h-2.5 opacity-40" fill="none" stroke="white" strokeWidth="2">
                      <line x1="2" y1="2" x2="8" y2="8" />
                      <line x1="8" y1="2" x2="2" y2="8" />
                    </svg>
                  </span>
                  Sold
                </span>
                <span className="flex items-center gap-2 text-green-300">
                  <span className="w-5 h-5 rounded border border-green-400 bg-green-400/25 ring-1 ring-green-400/50 flex items-center justify-center text-[8px] text-green-300">8</span>
                  Selected
                </span>
                <span className="flex items-center gap-2 text-amber-400/70">
                  <span className="w-5 h-5 rounded border border-amber-500/40 bg-amber-500/10 flex items-center justify-center text-[8px] text-amber-400/50">8</span>
                  Locked
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Ticket categories select (or seat-map summary) */}
        <div className="md:col-span-5 space-y-6">
          <div className="bg-stage/20 border border-white/[0.04] p-6 rounded-2xl">
            {hasSeatMap ? (
              <>
                <h2 className="font-display text-2xl tracking-wide text-paper uppercase mb-4">YOUR SELECTION</h2>
                {selectedSeatIds.length === 0 ? (
                  <p className="text-xs text-haze font-mono">Tap seats on the seat map to select them.</p>
                ) : (
                  <div className="space-y-3">
                    <p className="text-xs font-mono text-haze">
                      {selectedSeatCategory} · {selectedSeatLabels.map((s) => s.label).join(', ')}
                    </p>
                  </div>
                )}
              </>
            ) : (
              <>
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
                  </div>
                )}
              </>
            )}

            {canPay && (
              <div className="border-t border-white/[0.04] pt-4 mt-6 space-y-4">
                <div className="flex items-end justify-between">
                  <div>
                    <span className="text-[10px] font-mono text-haze uppercase block">Total Due</span>
                    <span className="font-display text-3xl text-spot2">₹{total}</span>
                  </div>

                  {isAdmin !== false ? (
                    <div className="bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-mono py-2.5 px-4 rounded-xl max-w-[200px]">
                      {isAdmin === null ? 'Checking account…' : 'Admins cannot book tickets'}
                    </div>
                  ) : (
                    <button onClick={handlePay} disabled={status === 'paying'} className="btn-spot text-sm">
                      {status === 'paying' ? 'Opening Payment…' : `Pay ₹${total}`}
                    </button>
                  )}
                </div>
              </div>
            )}

            {error && (
              <p className="text-spot text-xs font-mono mt-3 text-right">
                ❌ {error}
              </p>
            )}
          </div>
        </div>

      </div>
    </div>
  )
}