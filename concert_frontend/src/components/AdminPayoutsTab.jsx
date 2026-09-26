import { useState, useEffect } from 'react'
import { api } from '../lib/api'

export default function AdminPayoutsTab() {
  const [payouts, setPayouts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [processingId, setProcessingId] = useState(null)

  const loadPayouts = () => {
    setLoading(true)
    api.getAdminPayouts()
      .then(res => setPayouts(res.results))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadPayouts()
  }, [])

  const handleMarkPaid = async (ledger_type, ledger_id) => {
    if (!window.confirm(`Are you sure you want to mark this payout as paid?`)) return
    
    setProcessingId(ledger_id)
    try {
      await api.markPayoutsPaid(ledger_type, [ledger_id])
      loadPayouts()
    } catch (err) {
      alert(err.message)
    } finally {
      setProcessingId(null)
    }
  }

  if (loading) return <div className="p-8 text-center text-haze">Loading payouts...</div>
  if (error) return <div className="p-8 text-center text-spot">{error}</div>

  const pendingPayouts = payouts.filter(p => p.status === 'pending')
  const paidPayouts = payouts.filter(p => p.status === 'paid')

  const renderTable = (data, title) => (
    <div className="mb-12">
      <h3 className="text-xl font-display uppercase text-paper mb-4">{title} ({data.length})</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-haze">
          <thead className="text-xs text-paper uppercase bg-stage border-b border-white/[0.04]">
            <tr>
              <th className="px-6 py-4 font-mono tracking-wider">Date</th>
              <th className="px-6 py-4 font-mono tracking-wider">Type</th>
              <th className="px-6 py-4 font-mono tracking-wider">Recipient</th>
              <th className="px-6 py-4 font-mono tracking-wider">Bank Details</th>
              <th className="px-6 py-4 font-mono tracking-wider">Amount</th>
              <th className="px-6 py-4 font-mono tracking-wider text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {data.length === 0 ? (
              <tr>
                <td colSpan="6" className="px-6 py-8 text-center text-haze/50 italic">
                  No records found.
                </td>
              </tr>
            ) : data.map((p) => {
              const dest = p.payout_destination ? (typeof p.payout_destination === 'string' ? JSON.parse(p.payout_destination) : p.payout_destination) : null;
              const bankDetails = dest 
                ? (dest.upi_id ? `UPI: ${dest.upi_id}` : (dest.bank_account ? `Bank: ${dest.bank_account} | IFSC: ${dest.ifsc}` : 'Not Set'))
                : 'Not Set';
                
              return (
                <tr key={p.id} className="border-b border-white/[0.04] bg-void/30 hover:bg-stage/20 transition-colors">
                  <td className="px-6 py-4 font-mono whitespace-nowrap">{new Date(p.created_at).toLocaleDateString()}</td>
                  <td className="px-6 py-4 font-bold">
                    <span className={`px-2 py-1 rounded text-[10px] uppercase ${p.ledger_type === 'booking' ? 'bg-go/10 text-go' : 'bg-spot/10 text-spot'}`}>
                      {p.ledger_type}
                    </span>
                  </td>
                  <td className="px-6 py-4">{p.recipient_name}</td>
                  <td className="px-6 py-4 font-mono text-xs max-w-xs truncate" title={bankDetails}>{bankDetails}</td>
                  <td className="px-6 py-4 font-mono font-bold text-white">₹{p.amount.toFixed(2)}</td>
                  <td className="px-6 py-4 text-right">
                    {p.status === 'pending' ? (
                      <button 
                        onClick={() => handleMarkPaid(p.ledger_type, p.id)}
                        disabled={processingId === p.id}
                        className="btn-go text-[10px] uppercase px-3 py-1 font-bold disabled:opacity-50"
                      >
                        {processingId === p.id ? 'Processing...' : 'Mark Paid'}
                      </button>
                    ) : (
                      <span className="text-go/60 text-[10px] uppercase font-bold tracking-widest border border-go/20 px-2 py-1 rounded">Paid</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )

  return (
    <div className="space-y-8 animate-fade-in-up">
      <div>
        <h2 className="font-display text-3xl uppercase tracking-widest text-paper mb-2">Payout Execution</h2>
        <p className="text-haze text-sm">
          Execute pending bank transfers to organizers and resale sellers. 
          Use your bank portal to initiate transfers, then mark them as paid here.
        </p>
      </div>

      {renderTable(pendingPayouts, 'Pending Payouts')}
      {renderTable(paidPayouts, 'Completed Payouts')}
    </div>
  )
}
