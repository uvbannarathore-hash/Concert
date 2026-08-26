import { useEffect, useState } from 'react'
import { adminApi } from '../lib/adminApi'

export default function AdminPage() {
  const [forbidden, setForbidden] = useState(false)
  const [stats, setStats] = useState(null)
  const [statsLoading, setStatsLoading] = useState(true)
  const [bookings, setBookings] = useState([])
  const [error, setError] = useState('')

  function loadDashboardData() {
    setStatsLoading(true)
    setError('')
    
    // Fetch stats
    adminApi.dashboardStats()
      .then((data) => {
        setStats(data)
      })
      .catch((err) => {
        if (err.message.includes('403')) {
          setForbidden(true)
        } else {
          setError(err.message)
        }
      })
      .finally(() => setStatsLoading(false))

    // Fetch recent bookings for the activity feed
    adminApi.allBookings()
      .then((data) => {
        setBookings(data.bookings || [])
      })
      .catch((err) => {
        if (err.message.includes('403')) {
          setForbidden(true)
        } else {
          setError(err.message)
        }
      })
  }

  useEffect(() => {
    loadDashboardData()
  }, [])

  if (forbidden) {
    return (
      <div className="max-w-lg mx-auto px-6 py-24 text-center">
        <p className="eyebrow mb-3">Backstage Access Required</p>
        <h1 className="font-display text-4xl mb-4 text-paper">NOT ON THE LIST</h1>
        <p className="text-haze text-sm leading-relaxed">
          Your account is not configured with administrative privileges. Please flip the
          <code className="mx-1.5 px-2 py-0.5 bg-stage2 border border-white/[0.04] rounded font-mono text-xs text-spot2">is_admin</code>
          flag inside public.users schema in Supabase.
        </p>
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-12 animate-fade-in-up space-y-8">
      
      {/* Header section */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 border-b border-white/[0.04] pb-6">
        <div>
          <p className="eyebrow mb-1">Backstage activity monitor</p>
          <h1 className="font-display text-5xl tracking-wide uppercase text-paper">ANALYTICS DASHBOARD</h1>
          <p className="text-xs text-haze mt-1">Real-time revenue, bookings stats, and live user activities</p>
        </div>
        <button 
          onClick={loadDashboardData} 
          disabled={statsLoading}
          className="btn-ghost text-xs uppercase tracking-wider font-mono px-4 py-2 self-start sm:self-auto disabled:opacity-50"
        >
          {statsLoading ? 'Refreshing...' : 'Refresh Stats ⟳'}
        </button>
      </div>

      {error && (
        <div className="border border-spot/20 bg-spot/5 text-spot text-xs font-mono rounded-xl p-4">
          ⚠️ Load failed: {error}
        </div>
      )}

      {statsLoading && !stats ? (
        <div className="flex items-center justify-center py-24">
          <div className="space-y-4 text-center">
            <div className="w-10 h-10 border-4 border-spot border-t-transparent rounded-full animate-spin mx-auto"></div>
            <p className="text-sm font-mono text-haze">Compiling real-time dashboard analytics...</p>
          </div>
        </div>
      ) : (
        <div className="space-y-8">
          
          {/* Stats Grid */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Stat Card 1: Total Revenue */}
            <div className="glass-card bg-stage/15 border border-white/[0.04] p-5 rounded-2xl relative overflow-hidden group hover:border-go/20 transition-all duration-300">
              <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-go to-[#5cffcc] opacity-70"></div>
              <span className="text-[10px] font-mono tracking-wider text-haze uppercase block mb-1">TOTAL REVENUE</span>
              <span className="font-display text-2xl sm:text-3xl text-paper block">₹{(stats?.total_sales || 0).toLocaleString()}</span>
              <div className="absolute right-4 bottom-4 w-7 h-7 rounded-full bg-go/5 border border-go/20 flex items-center justify-center text-go font-mono text-xs">₹</div>
            </div>

            {/* Stat Card 2: Confirmed Sales */}
            <div className="glass-card bg-stage/15 border border-white/[0.04] p-5 rounded-2xl relative overflow-hidden group hover:border-spot/20 transition-all duration-300">
              <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-spot to-[#ff5c84] opacity-70"></div>
              <span className="text-[10px] font-mono tracking-wider text-haze uppercase block mb-1">CONFIRMED SALES</span>
              <span className="font-display text-2xl sm:text-3xl text-paper block">{stats?.confirmed_bookings || 0} / {stats?.total_bookings || 0}</span>
              <div className="absolute right-4 bottom-4 w-7 h-7 rounded-full bg-spot/5 border border-spot/20 flex items-center justify-center text-spot font-mono text-xs">✓</div>
            </div>

            {/* Stat Card 3: Tickets Sold */}
            <div className="glass-card bg-stage/15 border border-white/[0.04] p-5 rounded-2xl relative overflow-hidden group hover:border-spot2/20 transition-all duration-300">
              <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-spot2 to-[#ffdf57] opacity-70"></div>
              <span className="text-[10px] font-mono tracking-wider text-haze uppercase block mb-1">TICKETS SOLD</span>
              <span className="font-display text-2xl sm:text-3xl text-paper block">{(stats?.total_sold || 0).toLocaleString()} seats</span>
              <div className="absolute right-4 bottom-4 w-7 h-7 rounded-full bg-spot2/5 border border-spot2/20 flex items-center justify-center text-spot2 font-mono text-xs">🎫</div>
            </div>

            {/* Stat Card 4: Occupancy Rate */}
            <div className="glass-card bg-stage/15 border border-white/[0.04] p-5 rounded-2xl relative overflow-hidden group hover:border-indigo-500/30 transition-all duration-300">
              <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-indigo-500 to-[#8a7cff] opacity-70"></div>
              <span className="text-[10px] font-mono tracking-wider text-haze uppercase block mb-1">OCCUPANCY RATE</span>
              <span className="font-display text-2xl sm:text-3xl text-paper block">{stats?.occupancy_rate || 0}%</span>
              <div className="absolute right-4 bottom-4 w-7 h-7 rounded-full bg-indigo-500/5 border border-indigo-500/20 flex items-center justify-center text-indigo-400 font-mono text-xs">%</div>
            </div>
          </div>

          {/* Charts block */}
          <div className="glass-card bg-stage/15 border border-white/[0.04] p-6 rounded-2xl shadow-2xl">
            <div className="flex justify-between items-center mb-6">
              <div>
                <h3 className="font-display text-lg text-paper uppercase tracking-wider">Sales by Show</h3>
                <p className="text-[10px] font-mono text-haze">Total revenue generated by active concerts</p>
              </div>
              <span className="text-[9px] font-mono border border-white/[0.08] px-2 py-0.5 rounded text-haze bg-white/[0.01]">REALTIME BREAKDOWN</span>
            </div>

            {(!stats?.sales_by_event || stats.sales_by_event.length === 0) ? (
              <p className="text-xs font-mono text-haze py-10 text-center">No sales logged to aggregate by show.</p>
            ) : (
              <div className="space-y-5">
                {stats.sales_by_event.map((item, idx) => {
                  const maxRevenue = Math.max(...stats.sales_by_event.map(s => s.revenue), 1)
                  const percentage = (item.revenue / maxRevenue) * 100
                  return (
                    <div key={idx} className="space-y-1.5 group animate-scale-in">
                      <div className="flex justify-between text-xs">
                        <span className="font-semibold text-paper group-hover:text-spot transition duration-150">{item.event}</span>
                        <span className="font-mono text-haze">
                          {item.tickets_sold} sold · <span className="font-semibold text-spot2">₹{item.revenue.toLocaleString()}</span>
                        </span>
                      </div>
                      <div className="w-full bg-white/[0.02] border border-white/[0.03] h-3.5 rounded-full overflow-hidden relative shadow-inner">
                        <div 
                          className="h-full bg-gradient-to-r from-spot to-[#ff5c84] rounded-full transition-all duration-1000 ease-out"
                          style={{ width: `${percentage}%` }}
                        ></div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Activity Feed */}
          <div className="glass-card bg-stage/15 border border-white/[0.04] p-6 rounded-2xl shadow-2xl">
            <div className="flex justify-between items-center mb-4 pb-3 border-b border-white/[0.03]">
              <h3 className="font-display text-lg text-paper uppercase tracking-wider">Recent Activity Stream</h3>
              <p className="text-[9px] font-mono text-haze">Showing latest 5 ticket bookings</p>
            </div>

            {bookings.length === 0 ? (
              <p className="text-xs font-mono text-haze py-4 text-center">No bookings logged yet.</p>
            ) : (
              <div className="divide-y divide-white/[0.03] space-y-3">
                {bookings.slice(0, 5).map((b) => {
                  const eventObj = b.events || {}
                  return (
                    <div key={b.booking_id} className="pt-3 flex justify-between items-center text-xs flex-wrap gap-2 animate-scale-in">
                      <div>
                        <span className="font-mono font-bold text-paper">{b.booking_id}</span>
                        <span className="text-[10px] text-haze ml-2">({b.user_id.split('-')[0]}...)</span>
                        <p className="text-haze mt-0.5">
                          Purchased <span className="text-spot2 font-semibold">{b.seats_booked} seats</span> for{' '}
                          <span className="font-bold text-paper">{eventObj.artist_name || `Ref ID: ${b.event_id}`}</span>{' '}
                          ({b.category})
                        </p>
                      </div>
                      <span className={`text-[10px] font-mono uppercase px-2 py-0.5 rounded ${
                        b.status === 'Confirmed' 
                          ? 'border border-go/25 bg-go/5 text-go' 
                          : 'border border-amber-500/25 bg-amber-500/5 text-amber-400'
                      }`}>
                        {b.status}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

        </div>
      )}
    </div>
  )
}