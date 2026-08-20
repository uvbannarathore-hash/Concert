import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

export default function AuthPage() {
  const [mode, setMode] = useState('login') // 'login' | 'signup'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setInfo('')
    setLoading(true)
    try {
      if (mode === 'signup') {
        await api.signup(email, password, name)
        setInfo('Account created. You can log in now.')
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
      <div className="w-full max-w-md">
        <p className="eyebrow mb-3 text-center">
          {mode === 'login' ? 'Welcome back' : 'Join the crowd'}
        </p>
        <h1 className="font-display text-4xl text-center mb-8">
          {mode === 'login' ? 'LOG IN' : 'CREATE ACCOUNT'}
        </h1>

        <form onSubmit={handleSubmit} className="bg-stage border border-edge rounded-2xl p-6 space-y-4">
          {mode === 'signup' && (
            <div>
              <label className="block text-sm text-haze mb-1.5">Name</label>
              <input
                className="field"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
              />
            </div>
          )}
          <div>
            <label className="block text-sm text-haze mb-1.5">Email</label>
            <input
              type="email"
              required
              className="field"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="block text-sm text-haze mb-1.5">Password</label>
            <input
              type="password"
              required
              minLength={6}
              className="field"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </div>

          {error && (
            <p className="text-sm text-spot bg-spot/10 border border-spot/30 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
          {info && (
            <p className="text-sm text-go bg-go/10 border border-go/30 rounded-lg px-3 py-2">
              {info}
            </p>
          )}

          <button type="submit" disabled={loading} className="btn-spot w-full">
            {loading ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Sign up'}
          </button>
        </form>

        <p className="text-center text-sm text-haze mt-5">
          {mode === 'login' ? "Don't have an account?" : 'Already have an account?'}{' '}
          <button
            className="text-spot2 font-semibold hover:underline"
            onClick={() => {
              setMode(mode === 'login' ? 'signup' : 'login')
              setError('')
              setInfo('')
            }}
          >
            {mode === 'login' ? 'Sign up' : 'Log in'}
          </button>
        </p>
      </div>
    </div>
  )
}
