import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { useNavigate } from 'react-router-dom'

export default function OrganizerDashboard() {
  const navigate = useNavigate()
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState('events')
  const [selectedEvent, setSelectedEvent] = useState(null)
  
  // Custom Tracking State
  const [gaId, setGaId] = useState('')
  const [pixelId, setPixelId] = useState('')
  const [trackingStatus, setTrackingStatus] = useState('')

  // Event Stats State
  const [eventStats, setEventStats] = useState(null)
  const [statsLoading, setStatsLoading] = useState(false)



  // Actually, let's fetch the full profile to get the accurate plan_tier
  const [profile, setProfile] = useState(null)
  const [payouts, setPayouts] = useState(null)
  const [payoutForm, setPayoutForm] = useState({ upi_id: '', bank_account: '', ifsc: '' })
  const [payoutSaving, setPayoutSaving] = useState(false)

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true)
        const profileData = await api.myProfile()
        setProfile(profileData)
        
        // Fetch all events by this organizer directly from the dedicated backend route
        const eventsData = await api.getOrganizerEvents()
        setEvents(eventsData.events)

        setPayoutForm({
          upi_id: profileData.payout_upi_id || '',
          bank_account: profileData.payout_bank_account || '',
          ifsc: profileData.payout_ifsc || ''
        })

        if (profileData.is_organizer) {
          const payoutData = await api.getPendingPayouts().catch(() => null)
          if (payoutData) setPayouts(payoutData)
        }
      } catch (err) {
        setError(err.message || 'Failed to load dashboard.')
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [])

  // Helper to determine effective plan in the UI (matches backend logic)
  const getEffectivePlan = () => {
    if (!profile) return 'starter'
    const tier = (profile.plan_tier || 'starter').toLowerCase()
    if (['pro', 'business'].includes(tier) && profile.plan_expiry_date) {
      if (new Date(profile.plan_expiry_date) >= new Date()) {
        return tier
      }
    }
    return 'starter'
  }

  const effectivePlan = getEffectivePlan()
  const isProOrAbove = ['pro', 'business'].includes(effectivePlan)
  const isBusiness = effectivePlan === 'business'

  const handleSavePayoutDetails = async (e) => {
    e.preventDefault()
    setPayoutSaving(true)
    try {
      await api.updateProfile({
        payout_upi_id: payoutForm.upi_id,
        payout_bank_account: payoutForm.bank_account,
        payout_ifsc: payoutForm.ifsc
      })
      if (payouts) {
        setPayouts(prev => ({ ...prev, payout_destination_missing: false }))
      }
      alert("Payout details saved.")
    } catch (err) {
      alert(err.message || "Failed to save payout details.")
    } finally {
      setPayoutSaving(false)
    }
  }

  const handleExportCsv = async (eventId) => {
    try {
      const csvText = await api.exportAttendeesCsv(eventId)
      const blob = new Blob([csvText], { type: 'text/csv;charset=utf-8;' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `attendees_${eventId}.csv`)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    } catch (err) {
      alert(`Export failed: ${err.message}`)
    }
  }

  const handleSaveTracking = async (e) => {
    e.preventDefault()
    setTrackingStatus('saving')
    try {
      await api.updateTrackingIds(selectedEvent.event_id, {
        ga_tracking_id: gaId || null,
        pixel_tracking_id: pixelId || null
      })
      setTrackingStatus('success')
      // Update local state
      setSelectedEvent({ ...selectedEvent, ga_tracking_id: gaId, pixel_tracking_id: pixelId })
    } catch (err) {
      alert(`Failed to save tracking: ${err.message}`)
      setTrackingStatus('')
    }
  }

  const renderEventDetails = () => {
    if (!selectedEvent) return null

    return (
      <div className="bg-void/50 border border-white/[0.08] p-6 rounded-xl space-y-8 animate-fade-in">
        <div>
          <h3 className="text-2xl font-display text-paper mb-2">{selectedEvent.title}</h3>
          <p className="text-haze">Date: {new Date(selectedEvent.event_date).toLocaleDateString()}</p>
        </div>

        {/* Inventory & Sales Section */}
        <div className="space-y-4">
          <h4 className="text-lg font-bold text-paper border-b border-white/[0.08] pb-2">Inventory & Sales</h4>
          {statsLoading ? (
            <p className="text-xs text-haze">Loading stats...</p>
          ) : eventStats ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-void border border-white/[0.04] p-4 rounded-xl">
                <p className="text-[10px] text-haze uppercase tracking-widest mb-1">Total Bookings</p>
                <p className="text-xl text-paper font-bold">{eventStats.total_confirmed_orders}</p>
              </div>
              <div className="bg-void border border-white/[0.04] p-4 rounded-xl">
                <p className="text-[10px] text-haze uppercase tracking-widest mb-1">Tickets Sold</p>
                <p className="text-xl text-go font-bold">{eventStats.total_tickets_sold} <span className="text-haze font-normal text-xs">/ {eventStats.total_capacity}</span></p>
              </div>
              <div className="bg-void border border-white/[0.04] p-4 rounded-xl">
                <p className="text-[10px] text-haze uppercase tracking-widest mb-1">Seats Remaining</p>
                <p className="text-xl text-paper font-bold">{eventStats.remaining_seats}</p>
              </div>
              <div className="bg-void border border-white/[0.04] p-4 rounded-xl">
                <p className="text-[10px] text-haze uppercase tracking-widest mb-1">Cancellations</p>
                <p className="text-xl text-spot font-bold">{eventStats.cancellations}</p>
              </div>
            </div>
          ) : (
            <p className="text-xs text-haze">Could not load stats.</p>
          )}
        </div>

        {/* CSV Export Section */}
        <div className="space-y-4">
          <h4 className="text-lg font-bold text-paper border-b border-white/[0.08] pb-2">Attendee Data</h4>
          
          {isProOrAbove ? (
            <button 
              onClick={() => handleExportCsv(selectedEvent.event_id)}
              className="bg-paper text-void px-6 py-2 rounded-xl text-sm font-bold hover:bg-white transition-colors"
            >
              ⬇️ Download Attendee CSV
            </button>
          ) : (
            <div className="relative">
              <button disabled className="bg-paper/30 text-void/50 px-6 py-2 rounded-xl text-sm font-bold cursor-not-allowed filter blur-[2px]">
                ⬇️ Download Attendee CSV
              </button>
              <div className="absolute inset-0 flex items-center p-4">
                <button 
                  onClick={() => navigate('/pricing')}
                  className="bg-spot text-white px-4 py-1 rounded-lg text-xs font-bold shadow-lg"
                >
                  ⭐ Upgrade to Pro to Export
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Tracking Section */}
        <div className="space-y-4">
          <h4 className="text-lg font-bold text-paper border-b border-white/[0.08] pb-2">Marketing & Tracking</h4>
          
          {isBusiness ? (
            <form onSubmit={handleSaveTracking} className="space-y-4 max-w-md">
              <div>
                <label className="block text-xs font-mono text-haze mb-1">Google Analytics 4 ID (G-XXXXXXXXXX)</label>
                <input 
                  type="text" 
                  value={gaId} 
                  onChange={(e) => setGaId(e.target.value)}
                  placeholder="G-..."
                  pattern="^G-[a-zA-Z0-9]{5,15}$"
                  className="w-full bg-void border border-white/[0.08] rounded-xl px-4 py-2 text-sm text-paper focus:border-spot/50 outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-mono text-haze mb-1">Meta Pixel ID</label>
                <input 
                  type="text" 
                  value={pixelId} 
                  onChange={(e) => setPixelId(e.target.value)}
                  placeholder="15 or 16 digits"
                  pattern="^\d{15,16}$"
                  className="w-full bg-void border border-white/[0.08] rounded-xl px-4 py-2 text-sm text-paper focus:border-spot/50 outline-none"
                />
              </div>
              <button 
                type="submit" 
                className="bg-paper text-void px-6 py-2 rounded-xl text-sm font-bold hover:bg-white transition-colors"
              >
                {trackingStatus === 'saving' ? 'Saving...' : trackingStatus === 'success' ? 'Saved!' : 'Save Tracking IDs'}
              </button>
            </form>
          ) : (
             <div className="relative p-6 border border-white/[0.04] rounded-xl bg-void overflow-hidden">
                <div className="filter blur-sm space-y-4 max-w-md opacity-30 select-none pointer-events-none">
                  <div>
                    <div className="block text-xs font-mono text-haze mb-1">Google Analytics 4 ID</div>
                    <div className="w-full h-10 bg-white/5 rounded-xl"></div>
                  </div>
                  <div>
                    <div className="block text-xs font-mono text-haze mb-1">Meta Pixel ID</div>
                    <div className="w-full h-10 bg-white/5 rounded-xl"></div>
                  </div>
                </div>
                <div className="absolute inset-0 flex flex-col items-center justify-center bg-stage/60 p-4 text-center backdrop-blur-[1px]">
                  <p className="text-paper text-sm mb-3">Add custom tracking pixels to your event page.</p>
                  <button 
                    onClick={() => navigate('/pricing')}
                    className="bg-spot text-white px-4 py-2 rounded-xl text-sm font-bold shadow-lg"
                  >
                    🚀 Upgrade to Business
                  </button>
                </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  if (loading) return <div className="p-12 text-center text-haze">Loading dashboard...</div>
  if (error) return <div className="p-12 text-center text-red-400">{error}</div>
  if (!profile?.is_organizer) return <div className="p-12 text-center text-haze">You are not an organizer.</div>

  return (
    <div className="min-h-screen pt-24 pb-20 px-6 md:px-12 max-w-7xl mx-auto">
      <div className="flex justify-between items-end mb-8">
        <div>
          <h1 className="text-4xl font-display uppercase tracking-wider text-paper">Organizer Dashboard</h1>
          <p className="text-haze font-mono text-sm mt-2">
            Current Plan: <span className="text-spot uppercase font-bold">{effectivePlan}</span>
            {effectivePlan === 'starter' && <button onClick={() => navigate('/pricing')} className="ml-4 text-xs underline hover:text-white">Upgrade</button>}
          </p>
        </div>
      </div>

      <div className="flex flex-col md:flex-row gap-8">
        {/* Sidebar */}
        <div className="w-full md:w-64 flex-shrink-0 space-y-2">
          <button 
            className={`w-full text-left px-4 py-3 rounded-xl text-sm font-bold transition-colors ${activeTab === 'events' ? 'bg-white/10 text-paper' : 'text-haze hover:bg-white/5'}`}
            onClick={() => { setActiveTab('events'); setSelectedEvent(null) }}
          >
            My Events
          </button>
          <button 
            className={`w-full text-left px-4 py-3 rounded-xl text-sm font-bold transition-colors ${activeTab === 'payouts' ? 'bg-white/10 text-paper' : 'text-haze hover:bg-white/5'}`}
            onClick={() => setActiveTab('payouts')}
          >
            Payout Settings
          </button>
        </div>

        {/* Main Content */}
        <div className="flex-grow">
          {activeTab === 'events' && (
            <div className="space-y-6">
              {!selectedEvent ? (
                <>
                  <h2 className="text-xl font-bold text-paper mb-4">Select an event to manage</h2>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {events.map(ev => (
                      <div 
                        key={ev.event_id}
                        onClick={async () => {
                          setSelectedEvent(ev)
                          setGaId(ev.ga_tracking_id || '')
                          setPixelId(ev.pixel_tracking_id || '')
                          setTrackingStatus('')
                          setEventStats(null)
                          setStatsLoading(true)
                          try {
                            const stats = await api.getEventStats(ev.event_id)
                            setEventStats(stats)
                          } catch (err) {
                            console.error("Failed to load stats", err)
                          } finally {
                            setStatsLoading(false)
                          }
                        }}
                        className="bg-void border border-white/[0.04] p-4 rounded-xl cursor-pointer hover:border-white/[0.12] transition-colors"
                      >
                        <h4 className="font-bold text-paper truncate">{ev.title}</h4>
                        <p className="text-xs text-haze mt-1">{new Date(ev.event_date).toLocaleDateString()}</p>
                      </div>
                    ))}
                    {events.length === 0 && <p className="text-haze">No events found.</p>}
                  </div>
                </>
              ) : (
                <>
                  <button 
                    onClick={() => setSelectedEvent(null)}
                    className="text-haze hover:text-paper text-sm mb-4 inline-flex items-center"
                  >
                    ← Back to Events
                  </button>
                  {renderEventDetails()}
                </>
              )}
            </div>
          )}

          {activeTab === 'payouts' && (
            <div className="space-y-6 max-w-4xl">
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
                    <div className="bg-stage/20 border border-white/[0.04] rounded-xl p-4 flex flex-col justify-center">
                      <p className="text-xs text-haze uppercase tracking-widest mb-1">Lifetime Earned</p>
                      <p className="text-2xl text-go font-semibold">₹{(payouts.total_lifetime_earned || 0).toLocaleString()}</p>
                    </div>
                  </div>
                  <p className="text-xs text-haze mt-4">
                    Payouts are processed automatically every Monday for all events that concluded in the prior week. 
                    Clawbacks occur if an event is cancelled and refunds are issued after a payout has already been processed.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
