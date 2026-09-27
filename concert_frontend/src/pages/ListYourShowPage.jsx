import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { MapPin } from 'lucide-react'
import { extractYoutubeVideoId } from '../utils/youtube'

const EVENT_TYPES = ['Concert', 'Movie', 'Comedy Show', 'Music Show', 'Play', 'Sports']

const emptyCategory = { category: '', price: '', seats: '' }

const emptyForm = {
  artist_name: '',
  venue_name: '',
  city: '',
  event_date: '',
  event_time: '',
  event_type: 'Concert',
  description: '',
  organizer_contact_name: '',
  organizer_contact_phone: '',
  organizer_notes: '',
  trailer_url: '',
}

const statusStyles = {
  Pending: 'text-spot2 border-spot2/20 bg-spot2/5',
  Approved: 'text-go border-go/20 bg-go/5',
  Rejected: 'text-spot border-spot/20 bg-spot/5',
}

export default function ListYourShowPage() {
  const [profile, setProfile] = useState(null)
  const [form, setForm] = useState(emptyForm)
  const [categories, setCategories] = useState([{ ...emptyCategory }])
  const [imageFile, setImageFile] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [successMsg, setSuccessMsg] = useState('')

  const [showLocationPicker, setShowLocationPicker] = useState(false)
  const [venueLocation, setVenueLocation] = useState(null)
  const [locationQuery, setLocationQuery] = useState('')
  const [locationResults, setLocationResults] = useState([])
  const [locationSearching, setLocationSearching] = useState(false)

  const [submissions, setSubmissions] = useState([])
  const [loadingSubmissions, setLoadingSubmissions] = useState(true)
  const [payouts, setPayouts] = useState(null)

  // Payout Details form state
  const [payoutForm, setPayoutForm] = useState({ upi_id: '', bank_account: '', ifsc: '' })
  const [payoutSaving, setPayoutSaving] = useState(false)

  useEffect(() => {
    if (!showLocationPicker || locationQuery.trim().length < 3) {
      setLocationResults([])
      return
    }
    const timer = setTimeout(async () => {
      setLocationSearching(true)
      try {
        const res = await fetch(
          `https://nominatim.openstreetmap.org/search?format=json&addressdetails=1&limit=5&q=${encodeURIComponent(locationQuery)}`
        )
        const data = await res.json()
        setLocationResults(data || [])
      } catch (err) {
        console.warn('Venue search failed', err)
        setLocationResults([])
      } finally {
        setLocationSearching(false)
      }
    }, 500)
    return () => clearTimeout(timer)
  }, [locationQuery, showLocationPicker])

  function selectLocationResult(place) {
    setVenueLocation({
      name: place.display_name.split(',')[0],
      address: place.display_name,
      latitude: parseFloat(place.lat),
      longitude: parseFloat(place.lon),
    })
    setShowLocationPicker(false)
    setLocationQuery('')
    setLocationResults([])
  }

  function loadInitialData() {
    setLoadingSubmissions(true)
    api.myProfile().then(data => {
      setProfile(data)
      setPayoutForm({
        upi_id: data.payout_upi_id || '',
        bank_account: data.payout_bank_account || '',
        ifsc: data.payout_ifsc || ''
      })
    }).catch(console.error)
    
    api.myShowSubmissions()
      .then((data) => setSubmissions(data.submissions || []))
      .catch(() => {})
      .finally(() => setLoadingSubmissions(false))
      
    api.getPendingPayouts()
      .then(setPayouts)
      .catch(console.error)
  }

  useEffect(loadInitialData, [])

  function updateField(key, value) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  function updateCategory(index, key, value) {
    setCategories((cats) => cats.map((c, i) => (i === index ? { ...c, [key]: value } : c)))
  }

  function addCategory() {
    setCategories((cats) => [...cats, { ...emptyCategory }])
  }

  function removeCategory(index) {
    setCategories((cats) => cats.filter((_, i) => i !== index))
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSuccessMsg('')

    const cleanCategories = categories
      .filter((c) => c.category.trim())
      .map((c) => ({
        category: c.category.trim(),
        price: parseFloat(c.price) || 0,
        seats: parseInt(c.seats, 10) || 0,
      }))

    if (cleanCategories.length === 0) {
      setError('Add at least one ticket category with a name.')
      return
    }
    
    if (form.trailer_url && form.trailer_url.trim() !== '') {
      const extractedId = extractYoutubeVideoId(form.trailer_url);
      if (!extractedId) {
        setError('Invalid YouTube Trailer URL. Please provide a valid youtube.com or youtu.be link.')
        return
      }
    }

    if (form.event_date) {
      const year = parseInt(form.event_date.split('-')[0], 10)
      const currentYear = new Date().getFullYear()
      if (year < currentYear || year > currentYear + 3) {
        setError(`Event year must be between ${currentYear} and ${currentYear + 3}.`)
        return
      }
    }

    setSubmitting(true)
    try {
      await api.submitShow(
        {
          ...form,
          categories: cleanCategories,
          latitude: venueLocation?.latitude ?? null,
          longitude: venueLocation?.longitude ?? null,
        },
        imageFile
      )
      setSuccessMsg('Your show was submitted for review. We’ll notify you once an admin approves it.')
      setForm(emptyForm)
      setCategories([{ ...emptyCategory }])
      setImageFile(null)
      setVenueLocation(null)
      loadInitialData()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleSavePayoutDetails(e) {
    e.preventDefault()
    setPayoutSaving(true)
    try {
      await api.updatePayoutDetails(payoutForm)
      alert("Payout details saved.")
      loadInitialData()
    } catch (err) {
      alert(err.message || "Failed to save payout details.")
    } finally {
      setPayoutSaving(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-12 animate-fade-in-up">
      <div className="mb-10">
        <p className="eyebrow mb-1">Bring your show to LiveWire</p>
        <h1 className="font-display text-5xl tracking-wide uppercase text-paper">LIST YOUR SHOW</h1>
        <p className="text-xs text-haze mt-1">
          Submit your event for review — once approved by our team, it goes live for booking.
        </p>
      </div>

      {error && (
        <div className="border border-spot/20 bg-spot/5 text-spot text-xs font-mono rounded-xl p-4 mb-6">
          ⚠️ {error}
        </div>
      )}
      {successMsg && (
        <div className="border border-go/20 bg-go/5 text-go text-xs font-mono rounded-xl p-4 mb-6">
          ✅ {successMsg}
        </div>
      )}

      {/* Organizer Dashboard Section */}
      {profile?.is_organizer ? (
        <div className="mb-12 space-y-8">
          {/* Plan Section */}
          <div className="bg-stage/20 border border-white/[0.04] rounded-2xl p-6">
            <h2 className="font-display text-2xl uppercase tracking-wide text-paper mb-4">Your Organizer Plan</h2>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
              <div>
                <p className="text-sm text-paper font-semibold capitalize">Current Tier: {profile.plan_tier || 'Starter'}</p>
                {profile.plan_expiry_date && new Date(profile.plan_expiry_date) > new Date() && (
                  <p className="text-xs text-haze mt-1">Expires on {new Date(profile.plan_expiry_date).toLocaleDateString()}</p>
                )}
              </div>
              <div className="flex gap-2">
                <Link to="/pricing" className="btn-paper text-xs px-4 py-2 bg-white/10 hover:bg-white/20">
                  Manage Plan / Upgrade
                </Link>
              </div>
            </div>
          </div>

          {/* Payout Details Section */}
          <div className="bg-stage/20 border border-white/[0.04] rounded-2xl p-6">
            <h2 className="font-display text-2xl uppercase tracking-wide text-paper mb-4">Payout Details</h2>
            {payouts?.payout_destination_missing && (
              <div className="mb-4 text-xs font-mono text-spot bg-spot/5 border border-spot/20 p-3 rounded-lg">
                ⚠️ You have pending payouts, but no payout destination is set. Please add a UPI ID or Bank Details below to receive your balance.
              </div>
            )}
            <form onSubmit={handleSavePayoutDetails} className="space-y-4 max-w-md">
              <div>
                <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">UPI ID (Preferred)</label>
                <input
                  value={payoutForm.upi_id}
                  onChange={(e) => setPayoutForm(f => ({ ...f, upi_id: e.target.value }))}
                  placeholder="e.g. name@bank"
                  className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper focus:outline-none focus:border-spot/40"
                />
              </div>
              <p className="text-xs text-haze font-mono text-center">— OR —</p>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">Bank Account</label>
                  <input
                    value={payoutForm.bank_account}
                    onChange={(e) => setPayoutForm(f => ({ ...f, bank_account: e.target.value }))}
                    className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper focus:outline-none focus:border-spot/40"
                  />
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">IFSC Code</label>
                  <input
                    value={payoutForm.ifsc}
                    onChange={(e) => setPayoutForm(f => ({ ...f, ifsc: e.target.value }))}
                    className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper focus:outline-none focus:border-spot/40"
                  />
                </div>
              </div>
              <button type="submit" disabled={payoutSaving} className="btn-spot text-xs mt-2">
                {payoutSaving ? 'Saving...' : 'Save Payout Details'}
              </button>
            </form>
          </div>

          {/* Payout Balance */}
          {payouts && (
            <div>
              <h2 className="font-display text-2xl uppercase tracking-wide text-paper mb-4">Payout Balance</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-stage/20 border border-white/[0.04] rounded-xl p-4 flex flex-col justify-center">
                  <p className="text-xs text-haze uppercase tracking-widest mb-1">Pending Payouts</p>
                  <p className="text-2xl text-paper font-semibold">₹{(payouts.total_pending_payout || 0).toLocaleString()}</p>
                </div>
                <div className="bg-stage/20 border border-white/[0.04] rounded-xl p-4 flex flex-col justify-center">
                  <p className="text-xs text-haze uppercase tracking-widest mb-1">Clawbacks</p>
                  <p className="text-2xl text-spot font-semibold">₹{(Math.abs(payouts.total_clawbacks) || 0).toLocaleString()}</p>
                </div>
                <div className="bg-stage/20 border border-white/[0.04] rounded-xl p-4 flex flex-col justify-center border-l-4 border-l-go/50">
                  <p className="text-xs text-haze uppercase tracking-widest mb-1">Net Payable</p>
                  <p className="text-2xl text-go font-semibold">₹{(payouts.net_payable || 0).toLocaleString()}</p>
                </div>
              </div>
            </div>
          )}
        </div>
      ) : (
        profile && (
          <div className="mb-12 bg-spot/5 border border-spot/20 rounded-2xl p-6 text-center">
            <h2 className="font-display text-xl uppercase tracking-wide text-spot mb-2">Submit Your First Event to Become an Organizer</h2>
            <p className="text-xs text-haze max-w-lg mx-auto">
              You are currently a standard user. Once you submit a show and it is approved by an admin, you will unlock the Organizer Dashboard where you can manage payouts, plans, and more.
            </p>
          </div>
        )
      )}

      <form onSubmit={handleSubmit} className="bg-stage/30 border border-white/[0.04] rounded-2xl p-6 space-y-6 mb-12">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">Artist / Event Title</label>
            <input
              required
              value={form.artist_name}
              onChange={(e) => updateField('artist_name', e.target.value)}
              className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper focus:outline-none focus:border-spot/40"
              placeholder="e.g. Arijit Singh"
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">Event Type</label>
            <select
              value={form.event_type}
              onChange={(e) => updateField('event_type', e.target.value)}
              className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper focus:outline-none focus:border-spot/40"
            >
              {EVENT_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">Venue Name</label>
            <input
              required
              value={form.venue_name}
              onChange={(e) => updateField('venue_name', e.target.value)}
              className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper focus:outline-none focus:border-spot/40"
              placeholder="e.g. DY Patil Stadium"
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">City</label>
            <input
              required
              value={form.city}
              onChange={(e) => updateField('city', e.target.value)}
              className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper focus:outline-none focus:border-spot/40"
              placeholder="e.g. Mumbai"
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">Event Date</label>
            <input
              required
              type="date"
              value={form.event_date}
              onChange={(e) => updateField('event_date', e.target.value)}
              className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper focus:outline-none focus:border-spot/40"
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">Event Time</label>
            <input
              required
              type="time"
              value={form.event_time}
              onChange={(e) => updateField('event_time', e.target.value)}
              className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper focus:outline-none focus:border-spot/40"
            />
          </div>
        </div>

        <div>
          <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">Description (Optional)</label>
          <textarea
            value={form.description}
            onChange={(e) => updateField('description', e.target.value)}
            className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper focus:outline-none focus:border-spot/40"
            rows="3"
            placeholder="Tell us about the event, what to expect, etc."
          />
        </div>

        <div>
          <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">Poster Image (optional)</label>
          <input
            type="file"
            accept="image/*"
            onChange={(e) => setImageFile(e.target.files?.[0] || null)}
            className="text-xs text-haze file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-spot/10 file:text-spot file:text-xs"
          />
        </div>

        <div>
          <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">YouTube Trailer URL (optional)</label>
          <input
            type="url"
            value={form.trailer_url}
            onChange={(e) => updateField('trailer_url', e.target.value)}
            className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper focus:outline-none focus:border-spot/40"
            placeholder="e.g. https://youtube.com/watch?v=..."
          />
        </div>

        <div>
          <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">Venue Location (optional)</label>
          <div className="flex flex-wrap gap-2 items-center">
            <button
              type="button"
              onClick={() => setShowLocationPicker((s) => !s)}
              className="text-xs font-mono px-3 py-1.5 rounded-lg border border-white/[0.06] text-haze hover:text-paper hover:border-spot/30 transition flex items-center gap-1.5"
            >
              <MapPin className="w-3.5 h-3.5 text-spot" /> {venueLocation ? 'Change pin' : 'Search & pin venue'}
            </button>
            {venueLocation && (
              <span className="flex items-center gap-1.5 text-[10px] font-mono text-spot2 bg-spot2/5 border border-spot2/15 px-2.5 py-1 rounded-md">
                {venueLocation.name}
                <button type="button" onClick={() => setVenueLocation(null)} className="text-[9px] hover:text-white font-bold">✕</button>
              </span>
            )}
          </div>

          {showLocationPicker && (
            <div className="mt-2 relative animate-scale-in">
              <input
                value={locationQuery}
                onChange={(e) => setLocationQuery(e.target.value)}
                placeholder="Search venue (e.g. DY Patil Stadium Mumbai)..."
                autoFocus
                className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-xs font-mono text-paper focus:outline-none focus:border-spot/40"
              />
              {locationSearching && (
                <p className="text-[10px] font-mono text-haze mt-1 px-2">Searching…</p>
              )}
              {locationResults.length > 0 && (
                <div className="absolute z-30 w-full mt-1 bg-stage border border-white/[0.06] rounded-xl overflow-hidden shadow-2xl">
                  {locationResults.map((place, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => selectLocationResult(place)}
                      className="block w-full text-left px-4 py-2 text-xs text-paper hover:bg-spot hover:text-void transition duration-150 truncate border-b border-white/[0.02]"
                    >
                      {place.display_name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-[10px] uppercase tracking-wider text-haze/60">Ticket Categories</label>
            <button type="button" onClick={addCategory} className="text-[10px] text-spot hover:text-[#ff5c84] font-mono uppercase">
              + Add Category
            </button>
          </div>
          <div className="space-y-2">
            {categories.map((cat, i) => (
              <div key={i} className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2 items-center">
                <input
                  value={cat.category}
                  onChange={(e) => updateCategory(i, 'category', e.target.value)}
                  placeholder="Category (e.g. VIP)"
                  className="bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper focus:outline-none focus:border-spot/40"
                />
                <input
                  type="number"
                  min="0"
                  value={cat.price}
                  onChange={(e) => updateCategory(i, 'price', e.target.value)}
                  placeholder="Price (₹)"
                  className="bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper focus:outline-none focus:border-spot/40"
                />
                <input
                  type="number"
                  min="0"
                  value={cat.seats}
                  onChange={(e) => updateCategory(i, 'seats', e.target.value)}
                  placeholder="Seats"
                  className="bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper focus:outline-none focus:border-spot/40"
                />
                {categories.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeCategory(i)}
                    className="text-haze/40 hover:text-spot text-xs px-2"
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-white/[0.04]">
          <div>
            <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">Your Name</label>
            <input
              value={form.organizer_contact_name}
              onChange={(e) => updateField('organizer_contact_name', e.target.value)}
              className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper focus:outline-none focus:border-spot/40"
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">Contact Phone</label>
            <input
              value={form.organizer_contact_phone}
              onChange={(e) => updateField('organizer_contact_phone', e.target.value)}
              className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper focus:outline-none focus:border-spot/40"
            />
          </div>
          <div className="sm:col-span-2">
            <label className="text-[10px] uppercase tracking-wider text-haze/60 block mb-1">Notes for Admin (optional)</label>
            <textarea
              value={form.organizer_notes}
              onChange={(e) => updateField('organizer_notes', e.target.value)}
              rows={3}
              className="w-full bg-void border border-white/[0.06] rounded-lg px-3 py-2 text-sm text-paper focus:outline-none focus:border-spot/40"
              placeholder="Anything the admin should know before approving this event."
            />
          </div>
        </div>

        <button type="submit" disabled={submitting} className="btn-spot text-xs disabled:opacity-40">
          {submitting ? 'Submitting…' : 'Submit for Review'}
        </button>
      </form>

      <div>
        <h2 className="font-display text-2xl uppercase tracking-wide text-paper mb-4">Your Submissions</h2>
        {loadingSubmissions && <p className="text-xs text-haze">Loading…</p>}
        {!loadingSubmissions && submissions.length === 0 && (
          <p className="text-xs text-haze">You haven't submitted any shows yet.</p>
        )}
        <div className="space-y-3">
          {submissions.map((s) => (
            <div key={s.id} className="bg-stage/20 border border-white/[0.04] rounded-xl p-4 flex items-center justify-between">
              <div>
                <p className="text-sm text-paper font-semibold">{s.artist_name}</p>
                <p className="text-xs text-haze">{s.venue_name}, {s.city} — {s.event_date}</p>
                {s.status === 'Rejected' && s.rejection_reason && (
                  <p className="text-[11px] text-spot mt-1">Reason: {s.rejection_reason}</p>
                )}
              </div>
              <span className={`text-[10px] font-mono uppercase px-2.5 py-1 rounded-md border ${statusStyles[s.status] || ''}`}>
                {s.status}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
