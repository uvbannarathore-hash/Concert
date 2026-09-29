import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../lib/api'

export default function LiveWireInsider() {
  const [email, setEmail] = useState('')
  const [city, setCity] = useState('')
  const [status, setStatus] = useState('idle') // idle, loading, success, error
  const [errorMsg, setErrorMsg] = useState('')

  const location = useLocation()
  
  // If we are on an artist page (e.g., /artists/ART_12345), grab the ID
  const artistMatch = location.pathname.match(/^\/artists\/([^/]+)$/)
  const currentArtistId = artistMatch ? artistMatch[1] : null

  const handleSubscribe = async (e) => {
    e.preventDefault()
    if (!email) return

    setStatus('loading')
    try {
      await api.subscribeInsider({ 
        email, 
        city, 
        artist_id: currentArtistId 
      })
      setStatus('success')
      setEmail('')
      setCity('')
    } catch (err) {
      console.error('Subscribe error:', err)
      setStatus('error')
      setErrorMsg(err.message || 'Failed to subscribe.')
    }
  }

  return (
    <div className="bg-stage border-t border-white/[0.04] py-12 md:py-16 mt-auto">
      <div className="max-w-7xl mx-auto px-6 md:px-12 flex flex-col items-center text-center">
        <h2 className="font-display text-3xl md:text-4xl uppercase tracking-wide text-paper mb-3">
          Join LiveWire Insider
        </h2>
        <p className="text-haze text-sm md:text-base max-w-lg mb-8">
          {currentArtistId 
            ? "Get the backstage pass. We'll alert you the second this artist announces a new show."
            : "Get the backstage pass. We'll alert you the second your favorite artists announce a new show in your city."}
        </p>

        {status === 'success' ? (
          <div className="bg-go/10 border border-go/30 text-go px-6 py-4 rounded-xl animate-fade-in font-mono text-sm">
            ✅ You're on the list! We'll keep you posted.
          </div>
        ) : (
          <form onSubmit={handleSubscribe} className="w-full max-w-xl flex flex-col md:flex-row gap-3">
            <input
              type="email"
              required
              placeholder="Your email address"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="flex-grow bg-void border border-white/[0.08] rounded-xl px-4 py-3 text-sm text-paper focus:outline-none focus:border-spot/40 transition-colors"
            />
            <input
              type="text"
              placeholder="City (Optional)"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              className="md:w-48 bg-void border border-white/[0.08] rounded-xl px-4 py-3 text-sm text-paper focus:outline-none focus:border-spot/40 transition-colors"
            />
            <button
              type="submit"
              disabled={status === 'loading'}
              className="btn-spot shrink-0 flex items-center justify-center min-w-[120px]"
            >
              {status === 'loading' ? 'Joining...' : 'Subscribe'}
            </button>
          </form>
        )}

        {status === 'error' && (
          <p className="text-spot text-xs mt-4 font-mono">⚠️ {errorMsg}</p>
        )}
      </div>
    </div>
  )
}
