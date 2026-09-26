import { useEffect, useState } from 'react'
import { api } from '../lib/api'

export default function SoldTicketsList() {
  const [soldTickets, setSoldTickets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.getMySoldTickets()
      .then(data => {
        setSoldTickets(data.results || [])
      })
      .catch(err => {
        setError(err.message)
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

  if (loading) {
    return (
      <div className="flex justify-center p-6 border border-white/[0.04] rounded-2xl bg-stage/15">
        <div className="w-6 h-6 border-2 border-spot border-t-transparent rounded-full animate-spin"></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="border border-spot/20 bg-spot/5 text-spot text-xs font-mono rounded-xl p-4">
        ⚠️ Failed to load sold tickets: {error}
      </div>
    )
  }

  if (soldTickets.length === 0) {
    return (
      <div className="border border-white/[0.04] bg-stage/15 rounded-2xl p-6 text-center text-xs text-haze">
        You haven't sold any tickets on the marketplace yet.
      </div>
    )
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'paid': return 'text-go bg-go/10 border-go/20'
      case 'awaiting_payment': return 'text-spot2 bg-spot2/10 border-spot2/20'
      case 'failed': return 'text-spot bg-spot/10 border-spot/20'
      case 'pending': return 'text-white bg-white/10 border-white/20'
      default: return 'text-haze bg-white/5 border-white/10'
    }
  }

  const formatStatus = (status) => {
    if (status === 'awaiting_payment') return 'Processing Payout'
    return status.replace('_', ' ')
  }

  return (
    <div className="space-y-4">
      {soldTickets.map((t) => (
        <div key={t.resale_booking_id} className="glass-card bg-stage/15 border border-white/[0.04] rounded-xl p-5 shadow-lg flex flex-col md:flex-row justify-between md:items-center gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] font-mono text-haze/60 uppercase">Sale: {t.resale_booking_id}</span>
              <span className={`text-[9px] font-mono uppercase tracking-wider px-2 py-0.5 rounded-full border ${getStatusColor(t.payout_status)}`}>
                {formatStatus(t.payout_status)}
              </span>
            </div>
            <div className="text-xs text-haze/80 font-mono mt-2 space-y-1">
              <div className="flex gap-2">
                <span className="w-24 text-haze/40">Sale Price:</span>
                <span>₹{t.sale_price}</span>
              </div>
              <div className="flex gap-2">
                <span className="w-24 text-haze/40">Platform Fee:</span>
                <span className="text-spot/80">-₹{t.platform_fee}</span>
              </div>
              <div className="flex gap-2 font-bold text-white pt-1 border-t border-white/[0.04] mt-1">
                <span className="w-24 text-haze/60">Your Payout:</span>
                <span className="text-go">₹{t.seller_payout}</span>
              </div>
            </div>
          </div>
          
          <div className="text-left md:text-right text-[10px] text-haze/40 font-mono self-start md:self-end">
            <div>Sold on {new Date(t.created_at).toLocaleDateString()}</div>
            {t.payout_status === 'awaiting_payment' && (
              <div className="mt-1 text-haze/60 max-w-[200px] leading-tight">
                Payouts are processed to your saved UPI ID or Bank Account within 3-5 business days.
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
