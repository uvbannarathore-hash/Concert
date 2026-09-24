import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { supabase } from '../lib/supabaseClient'
import { api } from '../lib/api'

export default function AuthCallbackPage() {
  const navigate = useNavigate()
  const [error, setError] = useState(null)

  useEffect(() => {
    async function handleCallback() {
      try {
        const { data: { session }, error: sessionError } = await supabase.auth.getSession()
        
        if (sessionError) throw sessionError
        if (!session) throw new Error('No session found')

        // Bridge the Supabase session into our custom local storage format
        api.setSessionExternal({
          access_token: session.access_token,
          refresh_token: session.refresh_token,
          user_id: session.user.id,
          email: session.user.email,
        })
        
        // Fresh session ID for chat memory continuity per tab
        sessionStorage.removeItem('chat_session_id')

        // Check if the user's profile is complete (OAuth only provides name and email)
        try {
          const profile = await api.myProfile()
          if (!profile.phone || !profile.city || !profile.address) {
            navigate('/complete-profile', { replace: true })
          } else {
            const pendingRedirect = sessionStorage.getItem('pendingRedirect')
            if (pendingRedirect) {
              sessionStorage.removeItem('pendingRedirect')
              navigate(pendingRedirect, { replace: true })
            } else {
              navigate('/', { replace: true })
            }
          }
        } catch (profileError) {
          // If profile fetch fails, assume incomplete or error
          console.error("Profile fetch error:", profileError)
          navigate('/complete-profile', { replace: true })
        }
        
      } catch (err) {
        console.error('OAuth Callback Error:', err)
        setError(err.message)
      }
    }

    handleCallback()
  }, [navigate])

  if (error) {
    return (
      <div className="min-h-[calc(100vh-64px)] flex items-center justify-center p-6">
        <div className="bg-stage border border-edge rounded-2xl p-6 text-center max-w-sm w-full">
          <p className="text-spot font-mono mb-4">Authentication Error</p>
          <p className="text-haze text-sm mb-6">{error}</p>
          <button onClick={() => navigate('/auth')} className="btn-spot w-full text-xs font-bold uppercase py-2">
            Return to Login
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-[calc(100vh-64px)] flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="w-8 h-8 border-2 border-void border-t-spot rounded-full animate-spin"></div>
        <p className="text-haze font-mono text-sm tracking-widest uppercase">Completing Sign In...</p>
      </div>
    </div>
  )
}
