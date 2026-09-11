import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import { api, getPublicPassUrl } from '../lib/api'
import DigitalPassModal from '../components/DigitalPassModal'
import ReviewModal from '../components/ReviewModal'

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
  const [refundingId, setRefundingId] = useState('')
  const [selectedPass, setSelectedPass] = useState(null)
  const [reviewingEvent, setReviewingEvent] = useState(null)
  const [razorpayKeyId, setRazorpayKeyId] = useState('')

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

  function load() {
    setLoading(true)
    api
      .myBookings()
      .then((data) => {
        setBookings(data.bookings || [])
        if (data.razorpay_key_id) setRazorpayKeyId(data.razorpay_key_id)
      })
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

  async function handleRefund(bookingId) {
    if (!window.confirm("Are you sure you want to refund this booking?")) return
    setRefundingId(bookingId)
    try {
      await api.initiateRefund(bookingId)
      alert("Refund initiated successfully")
      load()
    } catch (err) {
      alert("Refund failed: " + err.message)
    } finally {
      setRefundingId('')
    }
  }

  async function handleRetryPayment(booking) {
    let retryDetails;
    try {
      retryDetails = await api.getPaymentRetry(booking.booking_id)
    } catch (err) {
      alert("Could not fetch payment details: " + err.message)
      return
    }

    const scriptReady = await loadRazorpayScript()
    if (!scriptReady) {
      alert("Razorpay SDK failed to load. Check your connection.")
      return
    }

    const rzp = new window.Razorpay({
      key: razorpayKeyId,
      amount: retryDetails.amount,
      currency: retryDetails.currency,
      order_id: retryDetails.razorpay_order_id,
      name: "Concert Booking Retry",
      description: `Payment for ${booking.events?.artist_name || 'Event'}`,
      theme: { color: '#FF3D6E' },
      handler: async function (response) {
        try {
          await api.verifyPayment({
            booking_id: booking.booking_id,
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          })
          load()
        } catch (err) {
          alert('Payment verification failed: ' + err.message)
        }
      },
    })
    rzp.on('payment.failed', function (response) {
      alert(`Payment Failed: ${response.error.description}`)
    })
    rzp.open()
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

  const checkIsPastEvent = (dateStr, timeStr) => {
    try {
      const dt = new Date(`${dateStr} ${timeStr || '00:00'}`)
      if (isNaN(dt.getTime())) return false
      return dt < new Date()
    } catch {
      return false
    }
  }

  function printReceipt(b) {
    const eventDetails = b.events || {}
    const printWindow = window.open('', '_blank', 'width=800,height=600');
    if (!printWindow) {
      alert('Please allow popups to download the receipt.');
      return;
    }
    const html = `
      <!DOCTYPE html>
      <html>
        <head>
          <title>Receipt - ${b.booking_id}</title>
          <style>
            body { font-family: 'Courier New', Courier, monospace; padding: 40px; color: #111; max-width: 600px; margin: 0 auto; line-height: 1.5; }
            .header { text-align: center; border-bottom: 2px dashed #ccc; padding-bottom: 20px; margin-bottom: 20px; }
            .title { font-size: 28px; font-weight: bold; margin: 0; letter-spacing: 2px; }
            .subtitle { font-size: 14px; color: #555; text-transform: uppercase; margin-top: 5px; }
            .row { display: flex; justify-content: space-between; margin-bottom: 12px; font-size: 15px; }
            .label { font-weight: bold; color: #333; }
            .divider { border-bottom: 1px solid #eee; margin: 20px 0; }
            .footer { text-align: center; margin-top: 40px; font-size: 12px; color: #777; border-top: 2px dashed #ccc; padding-top: 20px; }
            @media print {
              body { padding: 0; margin: 20px auto; }
            }
          </style>
        </head>
        <body>
          <div class="header">
            <h1 class="title">LIVEWIRE</h1>
            <div class="subtitle">Official Booking Receipt</div>
          </div>
          
          <div class="row"><span class="label">Booking ID:</span> <span>${b.booking_id}</span></div>
          <div class="row"><span class="label">Event:</span> <span>${eventDetails.artist_name || 'LiveWire Show'}</span></div>
          <div class="row"><span class="label">Venue:</span> <span>${eventDetails.venue_name || '-'}, ${eventDetails.city || '-'}</span></div>
          <div class="row"><span class="label">Date:</span> <span>${eventDetails.event_date ? formatDate(eventDetails.event_date) : '-'}</span></div>
          <div class="row"><span class="label">Time:</span> <span>${eventDetails.event_time || '-'}</span></div>
          
          <div class="divider"></div>
          
          <div class="row"><span class="label">Category:</span> <span>${(b.category || 'General').toUpperCase()}</span></div>
          <div class="row"><span class="label">Seats:</span> <span>${b.seats_booked}</span></div>
          <div class="row"><span class="label">Booking Status:</span> <span>${(b.status || '').toUpperCase()}</span></div>
          <div class="row"><span class="label">Payment Status:</span> <span>${(b.payment_status || '').toUpperCase()}</span></div>
          
          <div class="footer">
            Generated on ${new Date().toLocaleString()}
          </div>
        </body>
      </html>
    `;
    printWindow.document.open();
    printWindow.document.write(html);
    printWindow.document.close();
    printWindow.focus();
    setTimeout(() => {
      printWindow.print();
    }, 250);
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
          ⚠️ Connection failure: {error}
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
          // Joined events detail is returned from backend as b.events
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
                    <div className="flex flex-col items-center gap-1 w-full text-center mt-2">
                      <button
                        onClick={() => printReceipt(b)}
                        className="text-[11px] text-haze hover:text-paper bg-white/[0.05] hover:bg-white/[0.1] rounded px-2 py-1 font-mono transition w-full"
                      >
                        Download Receipt
                      </button>
                      <button
                        onClick={() => handleCancel(b.booking_id)}
                        disabled={cancellingId === b.booking_id}
                        className="text-[11px] text-haze/60 hover:text-spot underline underline-offset-4 disabled:opacity-40 font-mono transition mt-1"
                      >
                        {cancellingId === b.booking_id ? 'Cancelling…' : 'Cancel Ticket'}
                      </button>
                    </div>
                  )}

                  {b.status === 'Cancelled' && !!b.razorpay_payment_id && b.payment_status !== 'Refunded' && (
                    <button
                      onClick={() => handleRefund(b.booking_id)}
                      disabled={refundingId === b.booking_id}
                      className="text-[11px] text-spot hover:text-white bg-spot/20 hover:bg-spot/40 rounded px-2 py-1 font-mono transition w-full mt-2"
                    >
                      {refundingId === b.booking_id ? 'Refunding…' : 'Initiate Refund'}
                    </button>
                  )}

                  {b.status === 'Pending' && (
                    <button
                      onClick={() => handleRetryPayment(b)}
                      className="text-[11px] text-go hover:text-white bg-go/20 hover:bg-go/40 rounded px-2 py-1 font-mono transition w-full mt-2"
                    >
                      Complete Payment
                    </button>
                  )}

                  {isConfirmed && b.payment_status === 'Paid' && checkIsPastEvent(eventDetails.event_date, eventDetails.event_time) && (
                    <button
                      onClick={() => setReviewingEvent(eventDetails)}
                      className="text-[11px] text-white hover:text-void bg-white/10 hover:bg-white rounded px-2 py-1 font-mono transition w-full mt-2 uppercase tracking-wider"
                    >
                      Leave a Review
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

      <ReviewModal
        isOpen={!!reviewingEvent}
        onClose={() => setReviewingEvent(null)}
        event={reviewingEvent}
        onSuccess={() => {
          alert('Review submitted successfully!')
          load()
        }}
      />
    </div>
  )
}
