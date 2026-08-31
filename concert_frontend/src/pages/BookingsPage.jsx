import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import { api, getPublicPassUrl } from '../lib/api'
import DigitalPassModal from '../components/DigitalPassModal'

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
  const [selectedPass, setSelectedPass] = useState(null)

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
    <div className="max-w-6xl mx-auto px-6 py-12 animate-fade-in-up">
      
      {/* Header section */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-8 border-b border-white/[0.04] pb-6">
        <div>
          <p className="eyebrow mb-1">Your personal box office</p>
          <h1 className="font-display text-5xl tracking-wide uppercase text-paper">MY BOOKINGS</h1>
        </div>
        <Link to="/" className="btn-ghost text-xs uppercase tracking-wider font-mono px-4 py-2 self-start sm:self-auto">
          Explore More Shows →
        </Link>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="space-y-3 text-center">
            <div className="w-8 h-8 border-4 border-spot border-t-transparent rounded-full animate-spin mx-auto"></div>
            <p className="text-xs font-mono text-haze">Retrieving your passes...</p>
          </div>
        </div>
      )}

      {error && (
        <div className="border border-spot/20 bg-spot/5 text-spot text-xs font-mono rounded-xl p-4 mb-6">
          {error}
        </div>
      )}

      {!loading && !error && bookings.length === 0 && (
        <div className="glass-card rounded-2xl p-12 text-center max-w-md mx-auto my-12 space-y-4">
          <span className="text-4xl block">🎟️</span>
          <h2 className="font-display text-2xl text-paper uppercase">No Active Bookings</h2>
          <p className="text-xs text-haze leading-relaxed">
            You haven't reserved tickets for any upcoming live concerts yet. Explore the lineup and reserve your spot!
          </p>
          <Link to="/" className="btn-spot inline-block text-xs font-bold uppercase tracking-wider !px-6 !py-2.5 mt-2">
            Browse Live Shows
          </Link>
        </div>
      )}

      {/* Bookings Card List - Physical Ticket Look */}
      <div className="space-y-6">
        {bookings.map((b) => {
          const eventDetails = b.events || {}
          const isConfirmed = b.status === 'Confirmed'
          const passUrl = getPublicPassUrl(b.booking_id)

          return (
            <div
              key={b.booking_id}
              className="glass-card bg-stage/15 border border-white/[0.04] rounded-2xl overflow-hidden hover:border-white/[0.08] transition-all duration-300 flex flex-col md:flex-row relative group shadow-xl"
            >
              
              {/* Event Image Banner (Left Column) */}
              <div className="md:w-64 h-48 md:h-auto relative flex-shrink-0 overflow-hidden bg-void">
                {eventDetails.image_url ? (
                  <img
                    src={eventDetails.image_url}
                    alt={eventDetails.artist_name || 'Event'}
                    className="absolute inset-0 w-full h-full object-cover object-center group-hover:scale-105 transition-transform duration-500"
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

                {/* Mobile View Pass Button */}
                <div className="mt-4 pt-3 border-t border-white/[0.04] md:hidden flex justify-between items-center">
                  <button
                    onClick={() => setSelectedPass(b)}
                    className="text-xs font-mono text-spot font-bold uppercase tracking-wider flex items-center gap-1.5"
                  >
                    <span>📱 View Digital Pass</span>
                    <span>↗</span>
                  </button>
                  {isConfirmed && (
                    <button
                      onClick={() => handleCancel(b.booking_id)}
                      disabled={cancellingId === b.booking_id}
                      className="text-xs text-haze hover:text-spot underline disabled:opacity-40"
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </div>

              {/* Status and QR Code widget (Right Column / Stub Cutout) */}
              <div className="p-6 border-t md:border-t-0 md:border-l-2 md:border-dashed border-white/[0.04] bg-stage2/10 md:w-56 flex md:flex-col justify-between items-center md:items-stretch relative flex-shrink-0">
                
                {/* Physical Ticket Notch Cutouts on left border of this column */}
                <div className="hidden md:block absolute w-4 h-4 rounded-full bg-void -left-2 top-[-8px] border-b border-white/[0.04]"></div>
                <div className="hidden md:block absolute w-4 h-4 rounded-full bg-void -left-2 bottom-[-8px] border-t border-white/[0.04]"></div>

                <div className="text-center md:text-left">
                  <span className="text-[9px] font-mono text-haze/40 block uppercase mb-1 hidden md:block">Entry Status</span>
                  <span className={`text-[11px] font-mono uppercase px-2.5 py-1 rounded-md border ${statusStyles[b.status] || ''} inline-block`}>
                    {b.status}
                  </span>
                </div>

                <div className="hidden md:flex flex-col items-center gap-2 mt-3">
                  
                  {/* Scannable SVG QR Code Card */}
                  <div 
                    onClick={() => setSelectedPass(b)}
                    className="w-full bg-white/[0.03] border border-white/[0.06] hover:border-spot/40 p-2.5 rounded-xl flex flex-col items-center gap-1.5 transition-all duration-200 cursor-pointer shadow-inner group/qr"
                    title="Click to expand Digital Pass"
                  >
                    <div className="p-1.5 bg-white rounded-lg shadow-md group-hover/qr:scale-105 transition-transform duration-200">
                      <QRCodeSVG
                        value={passUrl}
                        size={76}
                        level="M"
                        fgColor="#0B0A10"
                        bgColor="#FFFFFF"
                      />
                    </div>
                    <span className="text-[9px] font-mono text-spot group-hover/qr:text-white uppercase tracking-wider font-bold transition flex items-center gap-1">
                      <span>View Pass</span>
                      <span>↗</span>
                    </span>
                  </div>

                  {isConfirmed && (
                    <button
                      onClick={() => handleCancel(b.booking_id)}
                      disabled={cancellingId === b.booking_id}
                      className="text-[11px] text-haze/60 hover:text-spot underline underline-offset-4 disabled:opacity-40 font-mono transition"
                    >
                      {cancellingId === b.booking_id ? 'Cancelling…' : 'Cancel Ticket'}
                    </button>
                  )}
                </div>

              </div>

            </div>
          )
        })}
      </div>

      {/* Interactive Digital Ticket Pass Modal */}
      <DigitalPassModal
        isOpen={!!selectedPass}
        onClose={() => setSelectedPass(null)}
        booking={selectedPass}
      />

    </div>
  )
}
