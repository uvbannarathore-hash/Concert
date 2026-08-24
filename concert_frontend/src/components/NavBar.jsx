import { useEffect, useState, useRef } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { api } from '../lib/api'

export default function NavBar() {
  const navigate = useNavigate()
  const location = useLocation()
  const loggedIn = api.isLoggedIn()
  
  const [profile, setProfile] = useState(null)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  
  const dropdownRef = useRef(null)

  useEffect(() => {
    if (loggedIn) {
      api.myProfile().then(setProfile).catch(() => {})
    } else {
      setProfile(null)
    }
  }, [loggedIn])

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Close mobile menu on route change
  useEffect(() => {
    setMobileMenuOpen(false)
  }, [location])

  function handleLogout() {
    api.logout()
    setDropdownOpen(false)
    navigate('/login')
  }

  const firstName = profile?.name?.split(' ')[0] || 'User'
  const activeClass = (path) => 
    location.pathname === path 
      ? 'text-spot font-bold scale-105' 
      : 'text-haze hover:text-paper hover:scale-105'

  return (
    <header className="sticky top-0 z-50 w-full bg-void/70 backdrop-blur-lg border-b border-white/[0.04]">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        
        {/* Logo */}
        <Link to="/" className="font-display text-2xl tracking-wider text-paper flex items-center gap-1.5 active:scale-95 transition-transform duration-200">
          <span className="w-2.5 h-6 bg-spot rounded-sm inline-block"></span>
          LIVE<span className="text-spot">WIRE</span>
        </Link>

        {/* Desktop Navigation Links */}
        <nav className="hidden md:flex items-center gap-8 font-body text-sm font-medium">
          <Link to="/" className={`${activeClass('/')} transition-all duration-200`}>Browse</Link>
          {loggedIn && (
            <>
              <Link to="/wishlist" className={`${activeClass('/wishlist')} transition-all duration-200`}>Wishlist</Link>
              <Link to="/bookings" className={`${activeClass('/bookings')} transition-all duration-200`}>My Bookings</Link>
              <Link to="/chat" className={`${activeClass('/chat')} transition-all duration-200`}>Assistant</Link>
            </>
          )}
          {profile?.is_admin && (
            <Link to="/admin" className="text-spot2 hover:brightness-110 flex items-center gap-1 transition-all duration-200 border border-spot2/30 px-3 py-1 rounded-full bg-spot2/5">
              <span className="w-1.5 h-1.5 bg-spot2 rounded-full animate-pulse"></span>
              Admin
            </Link>
          )}
        </nav>

        {/* User Account / Actions (Desktop) */}
        <div className="hidden md:flex items-center gap-4">
          {loggedIn ? (
            <div className="relative" ref={dropdownRef}>
              <button 
                onClick={() => setDropdownOpen(!dropdownOpen)}
                className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-white/[0.04] bg-stage2/40 hover:bg-stage2/80 transition duration-300 outline-none"
              >
                {/* Simulated Avatar Badge */}
                <span className="w-7 h-7 rounded-full bg-gradient-to-tr from-spot to-[#ff5c84] text-void font-bold text-xs flex items-center justify-center uppercase shadow-sm">
                  {firstName.charAt(0)}
                </span>
                <span className="text-sm font-semibold text-paper max-w-[120px] truncate">{firstName}</span>
                <svg className={`w-4 h-4 text-haze transition-transform duration-300 ${dropdownOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7"></path>
                </svg>
              </button>

              {/* Profile Dropdown Sheet */}
              {dropdownOpen && (
                <div className="absolute right-0 mt-2 w-48 rounded-xl border border-white/[0.06] bg-stage/95 backdrop-blur-xl shadow-2xl p-2 animate-scale-in flex flex-col gap-1 z-50">
                  <Link 
                    to="/profile" 
                    onClick={() => setDropdownOpen(false)}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-paper hover:bg-stage2/60 transition duration-200"
                  >
                    👤 Profile
                  </Link>
                  <button 
                    onClick={handleLogout}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-spot hover:bg-spot/10 text-left transition duration-200"
                  >
                    🚪 Log out
                  </button>
                </div>
              )}
            </div>
          ) : (
            <Link to="/login" className="btn-spot !px-5 !py-2 text-sm">
              Log in
            </Link>
          )}
        </div>

        {/* Mobile Menu Hamburger Button */}
        <button 
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="md:hidden flex items-center justify-center w-9 h-9 rounded-lg border border-white/[0.04] bg-stage2/40 hover:bg-stage2/80 transition outline-none"
          aria-label="Toggle menu"
        >
          <svg className="w-5 h-5 text-paper" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            {mobileMenuOpen ? (
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12"></path>
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16"></path>
            )}
          </svg>
        </button>

      </div>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div className="md:hidden border-t border-white/[0.04] bg-void/95 backdrop-blur-xl animate-fade-in px-6 py-5 space-y-4 flex flex-col">
          <Link to="/" className="text-base font-medium text-paper py-1 border-b border-white/[0.02]">Browse</Link>
          {loggedIn ? (
            <>
              <Link to="/wishlist" className="text-base font-medium text-paper py-1 border-b border-white/[0.02]">Wishlist</Link>
              <Link to="/bookings" className="text-base font-medium text-paper py-1 border-b border-white/[0.02]">My Bookings</Link>
              <Link to="/chat" className="text-base font-medium text-paper py-1 border-b border-white/[0.02]">Assistant</Link>
              <Link to="/profile" className="text-base font-medium text-paper py-1 border-b border-white/[0.02]">👤 Profile ({firstName})</Link>
              {profile?.is_admin && (
                <Link to="/admin" className="text-base font-medium text-spot2 py-1 border-b border-white/[0.02]">⚙️ Admin Backend</Link>
              )}
              <button 
                onClick={handleLogout}
                className="w-full text-center py-2.5 rounded-xl border border-spot/30 text-spot font-bold hover:bg-spot/5 transition"
              >
                Log out
              </button>
            </>
          ) : (
            <Link to="/login" className="w-full text-center py-2.5 rounded-xl bg-spot text-void font-bold transition shadow-md">
              Log in
            </Link>
          )}
        </div>
      )}
    </header>
  )
}