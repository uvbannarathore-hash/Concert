import { useState, useEffect } from 'react'
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts'
import { adminApi } from '../lib/adminApi'

const COLORS = ['#8A2BE2', '#00FFFF', '#FF1493', '#32CD32', '#FF8C00']

export default function AnalyticsDashboard() {
  const [overview, setOverview] = useState(null)
  const [revenueData, setRevenueData] = useState([])
  const [bookingsData, setBookingsData] = useState([])
  const [topEvents, setTopEvents] = useState([])
  const [categorySales, setCategorySales] = useState([])
  
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    async function fetchAnalytics() {
      try {
        setLoading(true)
        const [
          overviewRes,
          revenueRes,
          bookingsRes,
          topEventsRes,
          categorySalesRes
        ] = await Promise.all([
          adminApi.getAnalyticsOverview(),
          adminApi.getAnalyticsRevenue(),
          adminApi.getAnalyticsBookings(),
          adminApi.getTopEvents(),
          adminApi.getCategorySales()
        ])

        setOverview(overviewRes)
        setRevenueData(revenueRes.data || [])
        setBookingsData(bookingsRes.data || [])
        setTopEvents(topEventsRes.data || [])
        setCategorySales(categorySalesRes.data || [])
      } catch (err) {
        setError(err.message || 'Failed to fetch analytics.')
      } finally {
        setLoading(false)
      }
    }
    fetchAnalytics()
  }, [])

  if (loading) {
    return (
      <div className="flex justify-center p-12">
        <div className="flex space-x-2">
          <div className="w-3 h-3 bg-spot rounded-full animate-bounce"></div>
          <div className="w-3 h-3 bg-spot rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
          <div className="w-3 h-3 bg-spot rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="border border-spot/20 bg-spot/5 text-spot text-sm font-mono rounded-xl p-4 text-center">
        ⚠️ {error}
      </div>
    )
  }

  if (!overview) return null

  // Check if we have absolutely no data (e.g. fresh DB)
  const hasData = overview.total_bookings > 0 || overview.upcoming_events > 0

  if (!hasData) {
    return (
      <div className="glass-card p-12 text-center rounded-xl">
        <p className="text-haze/60 font-mono">No analytics data available yet. Start selling tickets!</p>
      </div>
    )
  }

  return (
    <div className="space-y-8 animate-fade-in">
      
      {/* KPI Overview Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="bg-stage/20 border border-white/[0.04] p-4 rounded-2xl shadow-lg flex flex-col justify-center">
          <span className="text-[10px] font-mono text-haze uppercase tracking-wider mb-1">Total Revenue</span>
          <span className="text-2xl font-display text-spot2">₹{overview.total_revenue.toLocaleString()}</span>
        </div>
        <div className="bg-stage/20 border border-white/[0.04] p-4 rounded-2xl shadow-lg flex flex-col justify-center">
          <span className="text-[10px] font-mono text-haze uppercase tracking-wider mb-1">Total Bookings</span>
          <span className="text-2xl font-display text-paper">{overview.total_bookings}</span>
        </div>
        <div className="bg-stage/20 border border-white/[0.04] p-4 rounded-2xl shadow-lg flex flex-col justify-center">
          <span className="text-[10px] font-mono text-haze uppercase tracking-wider mb-1">Tickets Sold</span>
          <span className="text-2xl font-display text-paper">{overview.total_tickets_sold}</span>
        </div>
        <div className="bg-stage/20 border border-white/[0.04] p-4 rounded-2xl shadow-lg flex flex-col justify-center">
          <span className="text-[10px] font-mono text-haze uppercase tracking-wider mb-1">Upcoming Events</span>
          <span className="text-2xl font-display text-go">{overview.upcoming_events}</span>
        </div>
        <div className="bg-stage/20 border border-white/[0.04] p-4 rounded-2xl shadow-lg flex flex-col justify-center">
          <span className="text-[10px] font-mono text-haze uppercase tracking-wider mb-1">Cancel Rate</span>
          <span className="text-2xl font-display text-spot">{overview.cancellation_rate}%</span>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {/* Revenue Over Time */}
        <div className="bg-stage/20 border border-white/[0.04] rounded-2xl p-6 shadow-xl">
          <h3 className="font-display tracking-wider uppercase text-paper mb-6">Revenue Over Time</h3>
          {revenueData.length > 0 ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={revenueData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                  <XAxis dataKey="date" stroke="#8892b0" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis stroke="#8892b0" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(val) => `₹${val}`} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#0B0A10', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                    itemStyle={{ color: '#00FFFF' }}
                  />
                  <Line type="monotone" dataKey="revenue" stroke="#00FFFF" strokeWidth={3} dot={{ r: 4, fill: '#00FFFF' }} activeDot={{ r: 6 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-xs font-mono text-haze/50 text-center py-10">No revenue data</p>
          )}
        </div>

        {/* Booking Volume */}
        <div className="bg-stage/20 border border-white/[0.04] rounded-2xl p-6 shadow-xl">
          <h3 className="font-display tracking-wider uppercase text-paper mb-6">Booking Volume</h3>
          {bookingsData.length > 0 ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={bookingsData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                  <XAxis dataKey="date" stroke="#8892b0" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis stroke="#8892b0" fontSize={12} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#0B0A10', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                    itemStyle={{ color: '#8A2BE2' }}
                  />
                  <Bar dataKey="bookings" fill="#8A2BE2" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-xs font-mono text-haze/50 text-center py-10">No booking data</p>
          )}
        </div>

        {/* Top Events */}
        <div className="bg-stage/20 border border-white/[0.04] rounded-2xl p-6 shadow-xl">
          <h3 className="font-display tracking-wider uppercase text-paper mb-6">Top Events by Revenue</h3>
          {topEvents.length > 0 ? (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={topEvents} layout="vertical" margin={{ top: 0, right: 30, left: 20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" horizontal={true} vertical={false} />
                  <XAxis type="number" stroke="#8892b0" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(val) => `₹${val/1000}k`} />
                  <YAxis dataKey="event_name" type="category" stroke="#8892b0" fontSize={12} tickLine={false} axisLine={false} width={100} />
                  <Tooltip 
                    cursor={{fill: 'rgba(255,255,255,0.05)'}}
                    contentStyle={{ backgroundColor: '#0B0A10', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                    itemStyle={{ color: '#FF1493' }}
                  />
                  <Bar dataKey="revenue" fill="#FF1493" radius={[0, 4, 4, 0]} barSize={20} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-xs font-mono text-haze/50 text-center py-10">No event data</p>
          )}
        </div>

        {/* Category Sales */}
        <div className="bg-stage/20 border border-white/[0.04] rounded-2xl p-6 shadow-xl flex flex-col">
          <h3 className="font-display tracking-wider uppercase text-paper mb-6">Ticket Categories</h3>
          {categorySales.length > 0 ? (
            <div className="h-64 flex-1">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={categorySales}
                    dataKey="tickets_sold"
                    nameKey="category"
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    innerRadius={40}
                    paddingAngle={2}
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {categorySales.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#0B0A10', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#FFF' }}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px', fontFamily: 'monospace', color: '#8892b0' }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-xs font-mono text-haze/50 text-center py-10 my-auto">No category data</p>
          )}
        </div>
      </div>
    </div>
  )
}
