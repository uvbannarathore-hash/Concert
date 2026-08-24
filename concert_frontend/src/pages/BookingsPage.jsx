import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { Link } from 'react-router-dom'

const statusStyles = {
  Confirmed: 'text-go border-go/20 bg-go/5',
  Cancelled: 'text-haze/40 border-edge bg-stage2/20 line-through',
  Pending: 'text-spot2 border-spot2/20 bg-spot2/5',
}

export default function BookingsPage() {
  const [bookings, setBookings] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [cancellingId, setCancellingId] = useState('')

  function load() {
    setLoading(true)
    api
      .myBookings()
      .then((data) => setBookings(data.bookings || []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  async function handleCancel(bookingId) {
    if (!window.confirm("Are you sure you want to cancel this booking? This action is irreversible.")) return
    setCancellingId(bookingId)
    try {
      await api.cancelBooking(bookingId)
      load()
    } catch (err) {
      setError(err.message)
    } finally {
      setCancellingId('')
    }
  }

  // Format date nicely (e.g. "Dec 20, 2026")
  const formatDate = (dateStr) => {
    try {
      const date = new Date(dateStr)
      if (isNaN(date.getTime())) return dateStr
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    } catch {
      return dateStr
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-12 animate-fade-in-up">
      <div className="mb-10">
        <p className="eyebrow mb-1">Receipts & passes</p>
        <h1 className="font-display text-5xl tracking-wide uppercase text-paper">MY BOOKINGS</h1>
        <p className="text-xs text-haze mt-1">Manage your active entry passes and purchase history</p>
      </div>

      {loading && (
        <div className="space-y-4 animate-pulse">
          {[1, 2].map((n) => (
            <div key={n} className="bg-stage2/20 border border-white/[0.04] rounded-2xl h-44 w-full"></div>
          ))}
        </div>
      )}

      {error && (
        <div className="border border-spot/20 bg-spot/5 text-spot text-xs font-mono rounded-xl p-4 mb-6">
          ⚠️ Connection failure: {error}
        </div>
      )}

      {!loading && bookings.length === 0 && (
        <div className="text-center py-20 border border-dashed border-white/[0.06] rounded-2xl bg-stage2/5 max-w-xl mx-auto">
          <span className="text-4xl">🎟️</span>
          <p className="font-display text-2xl mb-2 text-paper mt-3 uppercase tracking-wide">No active passes</p>
          <p className="text-sm text-haze max-w-xs mx-auto">You haven't booked any shows yet. Explore genres and secure your entry today.</p>
          <Link to="/" className="btn-spot text-xs mt-6 inline-block">Browse Shows</Link>
        </div>
      )}

      <div className="space-y-6">
        {bookings.map((b) => {
          // Joined events detail is returned from backend as b.events
          const eventDetails = b.events || {}
          const isConfirmed = b.status === 'Confirmed'
          
          return (
            <div
              key={b.booking_id}
              className="bg-stage/30 border border-white/[0.04] rounded-2xl shadow-xl overflow-hidden flex flex-col md:flex-row animate-scale-in relative"
            >
              
              {/* Event poster thumbnail (Left Column) */}
              <div className="md:w-1/4 h-36 md:h-auto bg-void relative overflow-hidden border-b md:border-b-0 md:border-r border-white/[0.04]">
                {eventDetails.image_url ? (
                  <img
                    src={eventDetails.image_url}
                    alt={eventDetails.artist_name || 'Event'}
                    className="absolute inset-0 w-full h-full object-cover object-center"
                  />
                ) : (
                  <div className="absolute inset-0 bg-gradient-to-br from-stage2/40 to-void flex items-center justify-center">
                    <span className="font-display text-xl text-edge">PASS</span>
                  </div>
                )}
                <div className="absolute inset-0 bg-gradient-to-t from-void/80 to-transparent md:hidden" />
              </div>

              {/* Booking Info and details (Middle Column) */}
              <div className="flex-1 p-6 flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-mono text-spot uppercase tracking-wider bg-spot/5 border border-spot/10 px-2 py-0.5 rounded">
                      {eventDetails.event_type || 'Show'}
                    </span>
                    <span className="text-[10px] font-mono text-haze/60 uppercase">
                      ID: {b.booking_id}
                    </span>
                  </div>

                  <h3 className="font-display text-2xl tracking-wide text-paper uppercase leading-tight mt-2.5">
                    {eventDetails.artist_name || `Event ID: ${b.event_id}`}
                  </h3>
                  
                  <p className="text-xs text-haze/80 font-semibold mt-1">
                    📍 {eventDetails.venue_name || 'Venue'}, {eventDetails.city || 'City'}
                  </p>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-5 text-left font-mono text-[11px] text-haze">
                    <div>
                      <span className="text-[9px] text-haze/40 block uppercase">DATE</span>
                      <span className="text-paper font-semibold">{eventDetails.event_date ? formatDate(eventDetails.event_date) : '-'}</span>
                    </div>
                    <div>
                      <span className="text-[9px] text-haze/40 block uppercase">TIME</span>
                      <span className="text-paper font-semibold">{eventDetails.event_time || '-'}</span>
                    </div>
                    <div>
                      <span className="text-[9px] text-haze/40 block uppercase">CATEGORY</span>
                      <span className="text-paper font-semibold uppercase">{b.category}</span>
                    </div>
                    <div>
                      <span className="text-[9px] text-haze/40 block uppercase">SEATS</span>
                      <span className="text-paper font-semibold">{b.seats_booked}</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Status and Actions widget (Right Column / Stub Cutout) */}
              <div className="p-6 border-t md:border-t-0 md:border-l-2 md:border-dashed border-white/[0.04] bg-stage2/10 md:w-52 flex md:flex-col justify-between items-center md:items-stretch relative">
                
                {/* Physical Ticket Notch Cutouts on left border of this column */}
                <div className="hidden md:block absolute w-4 h-4 rounded-full bg-void -left-2 top-[-8px] border-b border-white/[0.04]"></div>
                <div className="hidden md:block absolute w-4 h-4 rounded-full bg-void -left-2 bottom-[-8px] border-t border-white/[0.04]"></div>

                <div className="text-center md:text-left">
                  <span className="text-[9px] font-mono text-haze/40 block uppercase mb-1 hidden md:block">Entry Status</span>
                  <span className={`text-[11px] font-mono uppercase px-2.5 py-1 rounded-md border ${statusStyles[b.status] || ''} inline-block`}>
                    {b.status}
                  </span>
                </div>

                <div className="text-right md:text-left flex md:flex-col md:gap-3 items-center md:items-stretch justify-end">
                  {isConfirmed && (
                    <button
                      onClick={() => handleCancel(b.booking_id)}
                      disabled={cancellingId === b.booking_id}
                      className="text-xs text-spot hover:text-[#ff5c84] underline underline-offset-4 disabled:opacity-40 font-semibold"
                    >
                      {cancellingId === b.booking_id ? 'Cancelling Pass…' : 'Cancel Ticket'}
                    </button>
                  )}
                  
                  {/* barcode on desktop view */}
                  <div className="hidden md:block w-full bg-white/5 border border-white/[0.02] p-2 rounded-lg flex flex-col items-center mt-3">
                    <div className="h-6 w-full flex justify-between overflow-hidden opacity-40 mix-blend-screen px-2">
                      {Array.from({ length: 22 }).map((_, i) => (
                        <div 
                          key={i} 
                          className="bg-paper" 
                          style={{ 
                            width: `${(i % 3 === 0 ? 2 : i % 2 === 0 ? 0.5 : 1)}px`, 
                            opacity: i % 5 === 0 ? 0.3 : 1 
                          }} 
                        />
                      ))}
                    </div>
                  </div>
                </div>

              </div>

            </div>
          )
        })}
      </div>
    </div>
  )
}
