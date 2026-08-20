import { useEffect, useState } from 'react'
import { api } from '../lib/api'

const statusStyles = {
  Confirmed: 'text-go border-go/40 bg-go/10',
  Cancelled: 'text-haze border-edge bg-stage2 line-through',
  Pending: 'text-spot2 border-spot2/40 bg-spot2/10',
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

  return (
    <div className="max-w-3xl mx-auto px-6 py-14">
      <p className="eyebrow mb-3">Your history</p>
      <h1 className="font-display text-5xl tracking-wide mb-10">MY BOOKINGS</h1>

      {loading && <p className="text-haze">Loading…</p>}
      {error && <p className="text-spot mb-4">{error}</p>}

      {!loading && bookings.length === 0 && (
        <div className="text-center py-20 border border-dashed border-edge rounded-2xl">
          <p className="font-display text-2xl mb-2">NO TICKETS YET</p>
          <p className="text-haze">Once you book a show, it'll show up here.</p>
        </div>
      )}

      <div className="space-y-3">
        {bookings.map((b) => (
          <div
            key={b.booking_id}
            className="bg-stage border border-edge rounded-2xl p-5 flex items-center justify-between flex-wrap gap-3"
          >
            <div>
              <p className="font-display text-xl tracking-wide">{b.event_id} — {b.category}</p>
              <p className="text-sm text-haze font-mono">
                {b.seats_booked} seats · {b.booking_date} · {b.booking_id}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <span className={`text-xs font-mono uppercase px-3 py-1 rounded-full border ${statusStyles[b.status] || ''}`}>
                {b.status}
              </span>
              {b.status === 'Confirmed' && (
                <button
                  onClick={() => handleCancel(b.booking_id)}
                  disabled={cancellingId === b.booking_id}
                  className="text-sm text-spot hover:underline disabled:opacity-40"
                >
                  {cancellingId === b.booking_id ? 'Cancelling…' : 'Cancel'}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
