import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { supabase } from '../lib/supabaseClient'

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
        const pendingRedirect = sessionStorage.getItem('pendingRedirect')
        if (pendingRedirect) {
          sessionStorage.removeItem('pendingRedirect')
          navigate(pendingRedirect, { replace: true })
        } else {
          navigate('/')
        }
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleOAuth(provider) {
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider,
        options: {
          redirectTo: `${window.location.origin}/auth/callback`
        }
      })
      if (error) setError(error.message)
    } catch (err) {
      setError(err.message)
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

        <div className="mt-6 flex items-center justify-between text-haze">
          <span className="w-1/5 border-b border-white/[0.08]"></span>
          <span className="text-xs uppercase font-mono tracking-widest text-haze/50">or continue with</span>
          <span className="w-1/5 border-b border-white/[0.08]"></span>
        </div>

        <div className="mt-6 flex flex-col gap-3">
          <button 
            type="button" 
            onClick={() => handleOAuth('google')}
            className="w-full bg-white text-black font-semibold text-sm rounded-xl py-2.5 flex items-center justify-center gap-2 hover:bg-white/90 transition-colors"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24">
              <path fill="currentColor" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            Google
          </button>
          <button 
            type="button" 
            onClick={() => handleOAuth('apple')}
            className="w-full bg-white text-black font-semibold text-sm rounded-xl py-2.5 flex items-center justify-center gap-2 hover:bg-white/90 transition-colors"
          >
            <svg className="w-5 h-5" viewBox="0 0 384 512">
              <path fill="currentColor" d="M318.7 268.7c-.2-36.7 16.4-64.4 50-84.8-18.8-26.9-47.2-41.7-84.7-44.6-35.5-2.8-74.3 20.7-88.5 20.7-15 0-49.4-19.7-76.4-19.7C63.3 141.2 4 184.8 4 273.5q0 39.3 14.4 81.2c12.8 36.7 59 126.7 107.2 125.2 25.2-.6 43-17.9 75.8-17.9 31.8 0 48.3 17.9 76.4 17.9 48.6-.7 90.4-82.5 102.6-119.3-65.2-30.7-61.7-90-61.7-91.9zm-56.6-164.2c27.3-32.4 24.8-61.9 24-72.5-24.1 1.4-52 16.4-67.9 34.9-17.5 19.8-27.8 44.3-25.6 71.9 26.1 2 49.9-11.4 69.5-34.3z"/>
            </svg>
            Apple
          </button>
        </div>

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