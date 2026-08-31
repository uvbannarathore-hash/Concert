import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { QRCodeSVG } from 'qrcode.react'
import { Link } from 'react-router-dom'
import { getPublicPassUrl } from '../lib/api'

export default function DigitalPassModal({ isOpen, onClose, booking }) {
  const [copied, setCopied] = useState(false)
  const [showCalendarMenu, setShowCalendarMenu] = useState(false)

  // Handle escape key to close
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape') onClose()
    }
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown)
      document.body.style.overflow = 'hidden'
    }
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = 'auto'
    }
  }, [isOpen, onClose])

  if (!isOpen || !booking) return null

  const eventDetails = booking.events || booking.event || {}
  const passUrl = getPublicPassUrl(booking.booking_id)

  function handleCopyLink() {
    navigator.clipboard.writeText(passUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2500)
  }

  function handleAddToGoogleCalendar() {
    const eventDate = (eventDetails.event_date || '2026-09-15').replace(/-/g, '')
    const eventTime = (eventDetails.event_time || '19:00').replace(/:/g, '') + '00'
    const startIso = `${eventDate}T${eventTime}`
    const endIso = `${eventDate}T230000`

    const title = encodeURIComponent(`${eventDetails.artist_name || 'Live Concert'} - ${booking.category} Entry Pass`)
    const details = encodeURIComponent(`LiveWire Verified Admission Pass\nBooking ID: ${booking.booking_id}\nCategory: ${booking.category}\nSeats: ${booking.seats_booked}\nPass: ${passUrl}`)
    const location = encodeURIComponent(`${eventDetails.venue_name || 'Venue'}, ${eventDetails.city || 'City'}`)

    const gcalUrl = `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${title}&dates=${startIso}/${endIso}&details=${details}&location=${location}`
    window.open(gcalUrl, '_blank')
    setShowCalendarMenu(false)
  }

  function handleDownloadICS() {
    const eventDate = eventDetails.event_date || '2026-09-15'
    const eventTime = eventDetails.event_time || '19:00'
    const dateFormatted = eventDate.replace(/-/g, '')
    const timeFormatted = eventTime.replace(/:/g, '') + '00'

    const icsContent = [
      'BEGIN:VCALENDAR',
      'VERSION:2.0',
      'PRODID:-//LiveWire Concert Booking//Digital Pass//EN',
      'BEGIN:VEVENT',
      `UID:${booking.booking_id}@livewire.events`,
      `DTSTAMP:${new Date().toISOString().replace(/[-:]/g, '').split('.')[0]}Z`,
      `DTSTART:${dateFormatted}T${timeFormatted}`,
      `SUMMARY:${eventDetails.artist_name || 'Live Concert'} - ${booking.category} Entry`,
      `DESCRIPTION:LiveWire Verified Entry Pass. Booking ID: ${booking.booking_id}. Seats: ${booking.seats_booked}. Verification: ${passUrl}`,
      `LOCATION:${eventDetails.venue_name || 'Venue'}, ${eventDetails.city || 'City'}`,
      'STATUS:CONFIRMED',
      'END:VEVENT',
      'END:VCALENDAR',
    ].join('\r\n')

    const blob = new Blob([icsContent], { type: 'text/calendar;charset=utf-8' })
    const link = document.createElement('a')
    link.href = window.URL.createObjectURL(blob)
    link.setAttribute('download', `ticket-${booking.booking_id}.ics`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    setShowCalendarMenu(false)
  }

  function handlePrint() {
    window.print()
  }

  const modalContent = (
    <div className="fixed inset-0 z-[99999] flex items-center justify-center p-4 sm:p-6 overflow-y-auto">
      
      {/* Dimmed backdrop */}
      <div 
        className="fixed inset-0 bg-black/85 backdrop-blur-md transition-opacity duration-300"
        onClick={onClose}
      />

      {/* Pass Modal Card */}
      <div 
        className="relative z-10 w-full max-w-md bg-[#0D0C13] border border-white/[0.12] rounded-3xl shadow-[0_25px_70px_rgba(0,0,0,0.95)] overflow-hidden my-auto animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        
        {/* Hologram / Security Header Banner */}
        <div className="bg-gradient-to-r from-spot/25 via-spot2/25 to-go/25 border-b border-white/[0.08] px-5 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-go opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-go"></span>
            </span>
            <span className="text-[10px] font-mono tracking-widest text-paper uppercase font-bold">
              VERIFIED ENTRY PASS · {booking.status || 'CONFIRMED'}
            </span>
          </div>
          <button 
            onClick={onClose}
            className="text-haze hover:text-paper text-sm w-7 h-7 rounded-full bg-white/[0.05] hover:bg-white/10 flex items-center justify-center transition"
            aria-label="Close modal"
          >
            ✕
          </button>
        </div>

        {/* Card Body */}
        <div className="p-6 space-y-5">
          
          {/* Event Header & Thumbnail */}
          <div className="flex gap-4 items-center">
            {eventDetails.image_url ? (
              <img 
                src={eventDetails.image_url} 
                alt={eventDetails.artist_name}
                className="w-16 h-16 rounded-2xl object-cover border border-white/[0.08] shadow-md flex-shrink-0" 
              />
            ) : (
              <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-spot to-spot2 flex items-center justify-center text-void font-display text-xl font-bold flex-shrink-0">
                LW
              </div>
            )}
            <div className="min-w-0 flex-1">
              <span className="text-[9px] font-mono uppercase px-2 py-0.5 rounded bg-spot/10 border border-spot/20 text-spot font-semibold">
                {eventDetails.event_type || 'Concert'}
              </span>
              <h3 className="font-display text-2xl tracking-wide uppercase text-paper truncate mt-1">
                {eventDetails.artist_name || 'Live Event'}
              </h3>
              <p className="text-xs text-haze truncate">
                📍 {eventDetails.venue_name || 'Venue'}, {eventDetails.city || 'City'}
              </p>
            </div>
          </div>

          {/* Schedule Grid */}
          <div className="grid grid-cols-3 gap-2 bg-white/[0.03] border border-white/[0.06] p-3 rounded-2xl text-center font-mono">
            <div>
              <span className="text-[9px] text-haze/50 block uppercase">DATE</span>
              <span className="text-xs font-semibold text-paper block mt-0.5 truncate">{eventDetails.event_date || 'TBA'}</span>
            </div>
            <div className="border-x border-white/[0.04]">
              <span className="text-[9px] text-haze/50 block uppercase">DOORS</span>
              <span className="text-xs font-semibold text-paper block mt-0.5 truncate">{eventDetails.event_time || '19:00'}</span>
            </div>
            <div>
              <span className="text-[9px] text-haze/50 block uppercase">TIER</span>
              <span className="text-xs font-semibold text-spot2 uppercase block mt-0.5 truncate">{booking.category}</span>
            </div>
          </div>

          {/* Scannable High-Tech QR Code Box */}
          <div className="relative bg-white/[0.03] border border-white/[0.08] rounded-2xl p-5 flex flex-col items-center justify-center gap-3 group">
            {/* 4 Corner Scan Brackets */}
            <div className="absolute top-2.5 left-2.5 w-3.5 h-3.5 border-t-2 border-l-2 border-spot rounded-tl-sm"></div>
            <div className="absolute top-2.5 right-2.5 w-3.5 h-3.5 border-t-2 border-r-2 border-spot rounded-tr-sm"></div>
            <div className="absolute bottom-2.5 left-2.5 w-3.5 h-3.5 border-b-2 border-l-2 border-spot rounded-bl-sm"></div>
            <div className="absolute bottom-2.5 right-2.5 w-3.5 h-3.5 border-b-2 border-r-2 border-spot rounded-br-sm"></div>

            {/* QR Code Graphic with White Canvas container for universal phone camera contrast */}
            <div className="p-3 bg-white rounded-xl shadow-xl flex items-center justify-center">
              <QRCodeSVG
                value={passUrl}
                size={160}
                level="H"
                includeMargin={false}
                fgColor="#0B0A10"
                bgColor="#FFFFFF"
              />
            </div>

            <div className="text-center space-y-0.5">
              <span className="font-mono text-xs text-paper font-bold tracking-wider uppercase block">
                {booking.booking_id}
              </span>
              <span className="text-[10px] text-haze font-mono block">
                Scan with any smartphone camera for entry validation
              </span>
            </div>
          </div>

          {/* Seat & Admission details */}
          <div className="flex items-center justify-between text-xs font-mono px-1">
            <span className="text-haze">ADMISSION SEATS:</span>
            <span className="font-bold text-paper text-sm">
              <span className="text-spot2 font-extrabold text-base">{booking.seats_booked}</span> {booking.seats_booked > 1 ? 'PERSONS' : 'PERSON'}
            </span>
          </div>

          {/* Actions & Utilities */}
          <div className="relative pt-2 border-t border-white/[0.06]">
            
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

            <div className="grid grid-cols-3 gap-2">
              <button
                onClick={() => setShowCalendarMenu(!showCalendarMenu)}
                className={`btn-ghost !py-2 !px-2 text-[10px] font-mono uppercase flex flex-col items-center justify-center gap-1 hover:border-spot2/30 ${showCalendarMenu ? 'border-spot2 text-white' : ''}`}
                title="Add to Google Calendar or download .ics"
              >
                <span>📅</span>
                <span>Calendar</span>
              </button>
              <button
                onClick={handlePrint}
                className="btn-ghost !py-2 !px-2 text-[10px] font-mono uppercase flex flex-col items-center justify-center gap-1 hover:border-spot/30"
                title="Print or save PDF pass"
              >
                <span>🖨️</span>
                <span>Print Pass</span>
              </button>
              <button
                onClick={handleCopyLink}
                className="btn-ghost !py-2 !px-2 text-[10px] font-mono uppercase flex flex-col items-center justify-center gap-1 hover:border-go/30"
                title="Copy public verification link"
              >
                <span>{copied ? '✓' : '🔗'}</span>
                <span>{copied ? 'Copied!' : 'Share Pass'}</span>
              </button>
            </div>
          </div>

          {/* Direct Link to Full Web Pass */}
          <Link
            to={`/ticket/${booking.booking_id}`}
            onClick={onClose}
            className="block text-center text-xs font-mono text-spot hover:underline tracking-wider uppercase pt-1"
          >
            Open Dedicated Verification Page →
          </Link>

        </div>
      </div>
    </div>
  )

  return createPortal(modalContent, document.body)
}
