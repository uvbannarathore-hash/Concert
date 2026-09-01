import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import { api, getPublicPassUrl } from '../lib/api'
import { supabase } from '../lib/supabaseClient'

export default function TicketPassPage() {
  const { bookingId } = useParams()
  const [ticket, setTicket] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const [showCalendarMenu, setShowCalendarMenu] = useState(false)

  useEffect(() => {
    setLoading(true)
    setError('')

    // 1. Try backend API endpoint first
    api.getTicketPass(bookingId)
      .then((data) => {
        if (data?.ticket) {
          setTicket(data.ticket)
          setLoading(false)
        } else {
          throw new Error('Not found')
        }
      })
      .catch(async () => {
        // 2. Direct Supabase fallback: ensures mobile phones scanning QR codes in local dev or deployed cross-networks always load successfully
        try {
          const { data, error: sbErr } = await supabase
            .from('bookings')
            .select('booking_id, event_id, category, seats_booked, status, created_at, events(*)')
            .eq('booking_id', bookingId)
            .maybeSingle()

          if (sbErr || !data) {
            setError('Ticket pass not found or invalid QR code.')
          } else {
            setTicket(data)
          }
        } catch (e) {
          setError('Unable to authenticate digital ticket pass.')
        } finally {
          setLoading(false)
        }
      })
  }, [bookingId])

  const eventDetails = ticket?.events || {}
  const userDetails = ticket?.users || {}
  const passUrl = getPublicPassUrl(bookingId)

  function handleCopyLink() {
    navigator.clipboard.writeText(passUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2500)
  }

  function handlePrint() {
    window.print()
  }

  function handleAddToGoogleCalendar() {
    if (!ticket) return
    const eventDate = (eventDetails.event_date || '2026-09-15').replace(/-/g, '')
    const eventTime = (eventDetails.event_time || '19:00').replace(/:/g, '') + '00'
    const startIso = `${eventDate}T${eventTime}`
    const endIso = `${eventDate}T230000`

    const title = encodeURIComponent(`${eventDetails.artist_name || 'Live Concert'} - ${ticket.category} Entry Pass`)
    const details = encodeURIComponent(`LiveWire Verified Admission Pass\nBooking ID: ${ticket.booking_id}\nCategory: ${ticket.category}\nSeats: ${ticket.seats_booked}\nPass: ${passUrl}`)
    const location = encodeURIComponent(`${eventDetails.venue_name || 'Venue'}, ${eventDetails.city || 'City'}`)

    const gcalUrl = `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${title}&dates=${startIso}/${endIso}&details=${details}&location=${location}`
    window.open(gcalUrl, '_blank')
    setShowCalendarMenu(false)
  }

  function handleDownloadICS() {
    if (!ticket) return
    const eventDate = eventDetails.event_date || '2026-09-15'
    const eventTime = eventDetails.event_time || '19:00'
    const dateFormatted = eventDate.replace(/-/g, '')
    const timeFormatted = eventTime.replace(/:/g, '') + '00'

    const icsContent = [
      'BEGIN:VCALENDAR',
      'VERSION:2.0',
      'PRODID:-//LiveWire Concert Booking//Digital Pass//EN',
      'BEGIN:VEVENT',
      `UID:${ticket.booking_id}@livewire.events`,
      `DTSTAMP:${new Date().toISOString().replace(/[-:]/g, '').split('.')[0]}Z`,
      `DTSTART:${dateFormatted}T${timeFormatted}`,
      `SUMMARY:${eventDetails.artist_name || 'Live Concert'} - ${ticket.category} Entry`,
      `DESCRIPTION:LiveWire Verified Digital Pass. ID: ${ticket.booking_id}. Seats: ${ticket.seats_booked}. Verification: ${passUrl}`,
      `LOCATION:${eventDetails.venue_name || 'Venue'}, ${eventDetails.city || 'City'}`,
      'STATUS:CONFIRMED',
      'END:VEVENT',
      'END:VCALENDAR',
    ].join('\r\n')

    const blob = new Blob([icsContent], { type: 'text/calendar;charset=utf-8' })
    const link = document.createElement('a')
    link.href = window.URL.createObjectURL(blob)
    link.setAttribute('download', `ticket-${ticket.booking_id}.ics`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    setShowCalendarMenu(false)
  }

  if (loading) {
    return (
      <div className="min-h-[80vh] flex flex-col items-center justify-center p-6">
        <div className="w-12 h-12 border-4 border-spot border-t-transparent rounded-full animate-spin mb-4" />
        <p className="font-mono text-sm text-haze uppercase tracking-widest">Verifying Digital Ticket Pass…</p>
      </div>
    )
  }

  if (error || !ticket) {
    return (
      <div className="max-w-md mx-auto my-16 p-8 glass-card bg-stage/40 rounded-3xl border border-spot/30 text-center space-y-4">
        <div className="w-16 h-16 rounded-full bg-spot/10 border border-spot/30 text-spot font-bold text-2xl flex items-center justify-center mx-auto">
          ✕
        </div>
        <h2 className="font-display text-2xl text-paper uppercase tracking-wider">Invalid Ticket Pass</h2>
        <p className="text-xs text-haze leading-relaxed font-mono">
          {error || 'This booking pass could not be authenticated. Please verify the booking ID or contact support.'}
        </p>
        <Link to="/" className="inline-block btn-spot !py-2 !px-6 text-xs font-bold uppercase mt-2">
          Back to Shows
        </Link>
      </div>
    )
  }

  const isConfirmed = ticket.status === 'Confirmed'

  return (
    <div className="max-w-xl mx-auto px-4 py-8 sm:py-12 animate-fade-in-up">
      
      {/* Top Header branding */}
      <div className="text-center mb-6 space-y-1">
        <p className="eyebrow text-spot font-mono tracking-widest">LIVEWIRE VERIFIED PASS</p>
        <h1 className="font-display text-4xl sm:text-5xl uppercase text-paper tracking-wide">
          OFFICIAL GATE PASS
        </h1>
        <p className="text-xs text-haze font-mono">
          Authenticated Digital Admission Ticket · Gate Entry Ready
        </p>
      </div>

      {/* Main Physical-Style Pass Container */}
      <div className="relative bg-[#0E0D15] border border-white/[0.08] rounded-3xl shadow-[0_25px_80px_rgba(0,0,0,0.85)] overflow-hidden">
        
        {/* Security Holographic Header Stripe */}
        <div className={`px-6 py-3 border-b border-white/[0.06] flex items-center justify-between ${
          isConfirmed 
            ? 'bg-gradient-to-r from-go/20 via-spot/20 to-spot2/20' 
            : 'bg-gradient-to-r from-spot/20 via-amber-500/20 to-spot/20'
        }`}>
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${isConfirmed ? 'bg-go' : 'bg-amber-400'}`}></span>
              <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${isConfirmed ? 'bg-go' : 'bg-amber-400'}`}></span>
            </span>
            <span className="font-mono text-[11px] font-bold tracking-widest uppercase text-paper">
              {isConfirmed ? 'VALID PASS · ENTRY APPROVED' : `STATUS: ${ticket.status}`}
            </span>
          </div>
          <span className="text-[10px] font-mono text-haze bg-white/[0.04] px-2 py-0.5 rounded border border-white/[0.04]">
            ID: {ticket.booking_id}
          </span>
        </div>

        {/* Hero Event Image / Banner */}
        <div className="relative h-52 sm:h-64 w-full overflow-hidden bg-void">
          {eventDetails.image_url ? (
            <img
              src={eventDetails.image_url}
              alt={eventDetails.artist_name || 'Event Banner'}
              className="w-full h-full object-cover object-center scale-105 hover:scale-100 transition-transform duration-700"
            />
          ) : (
            <div className="w-full h-full bg-gradient-to-tr from-stage via-stage2 to-void flex items-center justify-center">
              <span className="font-display text-4xl text-edge">LIVEWIRE PASS</span>
            </div>
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-[#0E0D15] via-[#0E0D15]/40 to-transparent" />
          
          {/* Tag Badges over hero */}
          <div className="absolute bottom-4 left-6 right-6 flex justify-between items-end">
            <div>
              <span className="text-[10px] font-mono uppercase px-2.5 py-1 rounded bg-spot text-void font-bold shadow-md">
                {eventDetails.event_type || 'Concert'}
              </span>
              <h2 className="font-display text-3xl sm:text-4xl tracking-wide uppercase text-paper mt-2 leading-none">
                {eventDetails.artist_name || 'Featured Event'}
              </h2>
            </div>
          </div>
        </div>

        {/* Event Schedule & Location */}
        <div className="p-6 space-y-6">
          
          <div className="flex items-center gap-2 text-xs text-haze/90 font-medium">
            <span>📍</span>
            <span className="text-paper font-semibold">{eventDetails.venue_name || 'Venue Name'}</span>
            <span>·</span>
            <span>{eventDetails.city || 'City'}</span>
          </div>

          {/* Schedule Matrix */}
          <div className="grid grid-cols-3 gap-3 bg-white/[0.02] border border-white/[0.04] p-4 rounded-2xl text-center font-mono">
            <div>
              <span className="text-[9px] text-haze/50 block uppercase">EVENT DATE</span>
              <span className="text-sm font-bold text-paper block mt-1">{eventDetails.event_date || 'TBA'}</span>
            </div>
            <div className="border-x border-white/[0.04]">
              <span className="text-[9px] text-haze/50 block uppercase">DOORS OPEN</span>
              <span className="text-sm font-bold text-paper block mt-1">{eventDetails.event_time || '19:00'}</span>
            </div>
            <div>
              <span className="text-[9px] text-haze/50 block uppercase">CATEGORY</span>
              <span className="text-sm font-bold text-spot2 uppercase block mt-1">{ticket.category}</span>
            </div>
          </div>

          {/* Scannable Gate Pass QR Code Box */}
          <div className="relative bg-white/[0.03] border border-white/[0.08] rounded-3xl p-6 flex flex-col items-center justify-center gap-4">
            
            {/* 4 Corner Scan Brackets */}
            <div className="absolute top-3 left-3 w-4 h-4 border-t-2 border-l-2 border-spot rounded-tl-sm"></div>
            <div className="absolute top-3 right-3 w-4 h-4 border-t-2 border-r-2 border-spot rounded-tr-sm"></div>
            <div className="absolute bottom-3 left-3 w-4 h-4 border-b-2 border-l-2 border-spot rounded-bl-sm"></div>
            <div className="absolute bottom-3 right-3 w-4 h-4 border-b-2 border-r-2 border-spot rounded-br-sm"></div>

            {/* High-Contrast Crisp QR Canvas */}
            <div className="p-4 bg-white rounded-2xl shadow-2xl flex items-center justify-center">
              <QRCodeSVG
                value={passUrl}
                size={200}
                level="H"
                includeMargin={false}
                fgColor="#0B0A10"
                bgColor="#FFFFFF"
              />
            </div>

            <div className="text-center space-y-1">
              <span className="font-mono text-sm text-paper font-bold tracking-widest uppercase block">
                {ticket.booking_id}
              </span>
              <p className="text-xs text-haze font-mono max-w-xs">
                Present this QR code to the venue turnstile or gate scanner for entry admission.
              </p>
            </div>
          </div>

          {/* Attendee Metadata */}
          <div className="divide-y divide-white/[0.04] text-xs font-mono">
            <div className="py-2.5 flex justify-between">
              <span className="text-haze">TICKET HOLDER:</span>
              <span className="text-paper font-semibold">{userDetails.name || 'Registered Guest'}</span>
            </div>
            <div className="py-2.5 flex justify-between">
              <span className="text-haze">TOTAL SEATS:</span>
              <span className="text-spot2 font-bold">{ticket.seats_booked} ADMIT(S)</span>
            </div>
            <div className="py-2.5 flex justify-between">
              <span className="text-haze">ISSUED AT:</span>
              <span className="text-paper font-semibold">{new Date(ticket.created_at).toLocaleDateString()}</span>
            </div>
          </div>

          {/* Quick Utility Actions */}
          <div className="relative pt-2">
            
            {showCalendarMenu && (
              <div className="absolute bottom-16 left-0 w-48 bg-stage border border-white/10 rounded-xl p-2 shadow-2xl space-y-1 z-20 animate-scale-in">
                <button
                  onClick={handleAddToGoogleCalendar}
                  className="w-full text-left px-3 py-2 text-xs font-mono text-paper hover:text-white hover:bg-white/[0.08] rounded-lg transition flex items-center gap-2"
                >
                  <span>📅</span> Google Calendar
                </button>
                <button
                  onClick={handleDownloadICS}
                  className="w-full text-left px-3 py-2 text-xs font-mono text-paper hover:text-white hover:bg-white/[0.08] rounded-lg transition flex items-center gap-2"
                >
                  <span>🍏</span> Apple / Outlook (.ics)
                </button>
              </div>
            )}

            <div className="grid grid-cols-3 gap-3">
              <button
                onClick={() => setShowCalendarMenu(!showCalendarMenu)}
                className={`btn-ghost !py-2.5 !px-3 text-xs font-mono uppercase flex flex-col items-center justify-center gap-1 hover:border-spot2/30 ${showCalendarMenu ? 'border-spot2 text-white' : ''}`}
                title="Add to Google Calendar or download .ics"
              >
                <span>📅</span>
                <span>Calendar</span>
              </button>
              <button
                onClick={handlePrint}
                className="btn-ghost !py-2.5 !px-3 text-xs font-mono uppercase flex flex-col items-center justify-center gap-1 hover:border-spot/30"
                title="Print or save PDF pass"
              >
                <span>🖨️</span>
                <span>Print Pass</span>
              </button>
              <button
                onClick={handleCopyLink}
                className="btn-ghost !py-2.5 !px-3 text-xs font-mono uppercase flex flex-col items-center justify-center gap-1 hover:border-go/30"
                title="Copy public verification link"
              >
                <span>{copied ? '✓' : '🔗'}</span>
                <span>{copied ? 'Copied' : 'Share Link'}</span>
              </button>
            </div>
          </div>

        </div>

      </div>

      <div className="text-center mt-6">
        <Link to="/bookings" className="text-xs font-mono text-haze hover:text-paper uppercase tracking-wider underline">
          ← Back to My Bookings
        </Link>
      </div>

    </div>
  )
}