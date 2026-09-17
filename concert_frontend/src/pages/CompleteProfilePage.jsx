import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

export default function CompleteProfilePage() {
  const [phone, setPhone] = useState('')
  const [city, setCity] = useState('')
  const [address, setAddress] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    
    try {
      await api.updateProfile({ phone, city, address })
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-[calc(100vh-64px)] bg-spot-radial flex items-center justify-center px-6">
      <div className="w-full max-w-md animate-scale-in">
        <p className="eyebrow mb-3 text-center">Almost there</p>
        <h1 className="font-display text-4xl text-center mb-8 uppercase tracking-wide">
          Complete Profile
        </h1>
        
        <p className="text-center text-haze text-sm mb-6">
          We need a few more details to finalize your account and enable booking.
        </p>

        <form onSubmit={handleSubmit} className="bg-stage border border-edge rounded-2xl p-6 space-y-4 shadow-2xl">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-mono text-haze/75 mb-1.5 uppercase">Phone</label>
              <input
                className="field font-mono"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="98765 43210"
                required
                autoComplete="tel"
              />
            </div>
            <div>
              <label className="block text-xs font-mono text-haze/75 mb-1.5 uppercase">City</label>
              <input
                className="field"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                placeholder="Mumbai"
                required
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-mono text-haze/75 mb-1.5 uppercase">Address</label>
            <input
              className="field"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder="123 MG Road, Near City Mall"
              required
            />
          </div>

          {error && (
            <p className="text-xs text-spot bg-spot/5 border border-spot/20 rounded-xl px-4 py-3 font-mono">
              ⚠️ {error}
            </p>
          )}

          <button type="submit" disabled={loading} className="btn-spot w-full text-xs font-bold uppercase tracking-wider !py-2.5 flex items-center justify-center gap-2 mt-4">
            {loading ? (
              <>
                <span className="w-4 h-4 border-2 border-void border-t-transparent rounded-full animate-spin"></span>
                Saving...
              </>
            ) : (
              'Complete Sign In'
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
