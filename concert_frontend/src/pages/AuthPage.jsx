import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

export default function AuthPage() {
  const [mode, setMode] = useState('login') // 'login' | 'signup'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [city, setCity] = useState('')
  const [address, setAddress] = useState('')
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  // Always reset fields to force fresh entries on mount and mode switch
  useEffect(() => {
    setEmail('')
    setPassword('')
    setShowPassword(false)
    setName('')
    setPhone('')
    setCity('')
    setAddress('')
    setError('')
    setInfo('')
  }, [mode])

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setInfo('')
    setLoading(true)
    try {
      if (mode === 'signup') {
        await api.signup(email, password, name, phone, city, address)
        setInfo('Account created successfully. You can log in now.')
        setMode('login')
      } else {
        await api.login(email, password)
        navigate('/')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-[calc(100vh-64px)] bg-spot-radial flex items-center justify-center px-6">
      <div className="w-full max-w-md animate-scale-in">
        <p className="eyebrow mb-3 text-center">
          {mode === 'login' ? 'Welcome back' : 'Join the crowd'}
        </p>
        <h1 className="font-display text-4xl text-center mb-8 uppercase tracking-wide">
          {mode === 'login' ? 'LOG IN' : 'CREATE ACCOUNT'}
        </h1>

        <form onSubmit={handleSubmit} className="bg-stage border border-edge rounded-2xl p-6 space-y-4 shadow-2xl">
          {mode === 'signup' && (
            <div>
              <label className="block text-xs font-mono text-haze/75 mb-1.5 uppercase">Name</label>
              <input
                className="field"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
                required
                autoComplete="new-name"
              />
            </div>
          )}
          {mode === 'signup' && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-mono text-haze/75 mb-1.5 uppercase">Phone</label>
                <input
                  className="field font-mono"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="98765 43210"
                  required
                  autoComplete="new-phone"
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
                  autoComplete="new-city"
                />
              </div>
            </div>
          )}
          {mode === 'signup' && (
            <div>
              <label className="block text-xs font-mono text-haze/75 mb-1.5 uppercase">Address</label>
              <input
                className="field"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
                placeholder="123 MG Road, Near City Mall"
                required
                autoComplete="new-address"
              />
            </div>
          )}
          <div>
            <label className="block text-xs font-mono text-haze/75 mb-1.5 uppercase">Email</label>
            <input
              type="email"
              required
              className="field font-mono"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="new-email"
            />
          </div>
          <div>
            <label className="block text-xs font-mono text-haze/75 mb-1.5 uppercase">Password</label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                required
                minLength={6}
                className="field pr-10 font-mono"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="new-password"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-2.5 text-haze hover:text-paper outline-none transition duration-150"
                title={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88"></path>
                  </svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                  </svg>
                )}
              </button>
            </div>
          </div>

          {error && (
            <p className="text-xs text-spot bg-spot/5 border border-spot/20 rounded-xl px-4 py-3 font-mono">
              ⚠️ {error}
            </p>
          )}
          {info && (
            <p className="text-xs text-go bg-go/5 border border-go/20 rounded-xl px-4 py-3 font-mono">
              ✓ {info}
            </p>
          )}

          <button type="submit" disabled={loading} className="btn-spot w-full text-xs font-bold uppercase tracking-wider !py-2.5 flex items-center justify-center gap-2">
            {loading ? (
              <>
                <span className="w-4 h-4 border-2 border-void border-t-transparent rounded-full animate-spin"></span>
                Processing...
              </>
            ) : mode === 'login' ? (
              'Log in'
            ) : (
              'Sign up'
            )}
          </button>
        </form>

        <p className="text-center text-sm text-haze mt-6">
          {mode === 'login' ? "Don't have an account?" : 'Already have an account?'}{' '}
          <button
            className="text-spot2 font-semibold hover:underline"
            onClick={() => setMode(mode === 'login' ? 'signup' : 'login')}
          >
            {mode === 'login' ? 'Create one' : 'Sign in'}
          </button>
        </p>
      </div>
    </div>
  )
}