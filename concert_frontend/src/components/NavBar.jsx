import { Link, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'

export default function NavBar() {
  const navigate = useNavigate()
  const loggedIn = api.isLoggedIn()

  function handleLogout() {
    api.logout()
    navigate('/login')
  }

  return (
    <header className="sticky top-0 z-40 backdrop-blur bg-void/80 border-b border-edge">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link to="/" className="font-display text-2xl tracking-wide text-paper">
          LIVE<span className="text-spot">WIRE</span>
        </Link>

        <nav className="flex items-center gap-6 font-body text-sm">
          <Link to="/" className="text-haze hover:text-paper transition">Concerts</Link>
          {loggedIn && (
            <Link to="/bookings" className="text-haze hover:text-paper transition">My Bookings</Link>
          )}
          {loggedIn && (
            <Link to="/chat" className="text-haze hover:text-paper transition">Assistant</Link>
          )}

          {loggedIn ? (
            <button onClick={handleLogout} className="btn-ghost !px-4 !py-2 text-sm">
              Log out
            </button>
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
