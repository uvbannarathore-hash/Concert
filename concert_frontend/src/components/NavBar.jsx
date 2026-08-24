import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

export default function NavBar() {
  const navigate = useNavigate()
  const loggedIn = api.isLoggedIn()
  const [profile, setProfile] = useState(null)

  useEffect(() => {
    if (loggedIn) {
      api.myProfile().then(setProfile).catch(() => {})
    }
  }, [loggedIn])

  function handleLogout() {
    api.logout()
    navigate('/login')
  }

  const firstName = profile?.name?.split(' ')[0]

  return (
    <header className="sticky top-0 z-40 backdrop-blur bg-void/80 border-b border-edge">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link to="/" className="font-display text-2xl tracking-wide text-paper">
          LIVE<span className="text-spot">WIRE</span>
        </Link>

        <nav className="flex items-center gap-6 font-body text-sm">
          <Link to="/" className="text-haze hover:text-paper transition">Browse</Link>
          {loggedIn && (
            <Link to="/wishlist" className="text-haze hover:text-paper transition">Wishlist</Link>
          )}
          {loggedIn && (
            <Link to="/bookings" className="text-haze hover:text-paper transition">My Bookings</Link>
          )}
          {loggedIn && (
            <Link to="/chat" className="text-haze hover:text-paper transition">Assistant</Link>
          )}
          {profile?.is_admin && (
            <Link to="/admin" className="text-spot2 hover:text-paper transition">Admin</Link>
          )}

          {loggedIn ? (
            <div className="flex items-center gap-3">
              {firstName && (
                <Link to="/profile" className="text-haze hover:text-paper transition hidden sm:inline">
                  Hey, {firstName}
                </Link>
              )}
              <button onClick={handleLogout} className="btn-ghost !px-4 !py-2 text-sm">
                Log out
              </button>
            </div>
          ) : (
            <Link to="/login" className="btn-spot !px-4 !py-2 text-sm">
              Log in
            </Link>
          )}
        </nav>
      </div>
    </header>
  )
}