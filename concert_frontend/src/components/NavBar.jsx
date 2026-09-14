import { useEffect, useState, useRef } from 'react'
import { Link, useNavigate, useLocation, useSearchParams } from 'react-router-dom'
import { api } from '../lib/api'
import { User, LogOut, ShieldCheck, Search, X, ChevronDown, Menu } from 'lucide-react'

export default function NavBar() {
  const navigate = useNavigate()
  const location = useLocation()
  const [loggedIn, setLoggedIn] = useState(api.isLoggedIn())
  
  const [profile, setProfile] = useState(null)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  
  const [searchParams, setSearchParams] = useSearchParams()
  const searchVal = searchParams.get('search') || ''

  const dropdownRef = useRef(null)

  useEffect(() => {
    if (loggedIn) {
      api.myProfile().then(setProfile).catch(() => {})
    } else {
      setProfile(null)
    }
  }, [loggedIn])

  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  useEffect(() => {
    setMobileMenuOpen(false)
    setLoggedIn(api.isLoggedIn())
  }, [location])

  useEffect(() => {
    const handleStorage = () => setLoggedIn(api.isLoggedIn())
    window.addEventListener('storage', handleStorage)
    return () => window.removeEventListener('storage', handleStorage)
  }, [])

  function handleLogout() {
    api.logout()
    setDropdownOpen(false)
    navigate('/login')
  }

  function handleSearchChange(val) {
    if (location.pathname === '/') {
      if (val) {
        setSearchParams({ search: val })
      } else {
        const nextParams = new URLSearchParams(searchParams)
        nextParams.delete('search')
        setSearchParams(nextParams)
      }
    } else {
      navigate(`/?search=${encodeURIComponent(val)}`)
    }
  }

  const firstName = profile?.name?.split(' ')[0] || 'User'
  const activeClass = (path) => 
    location.pathname === path 
      ? 'text-spot font-bold scale-105' 
      : 'text-haze hover:text-paper hover:scale-105'

  return (
    <header className="sticky top-0 z-50 w-full bg-void/70 backdrop-blur-lg border-b border-white/[0.04]">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between gap-4">
        
        {/* Logo */}
        <Link to="/" className="font-display text-2xl tracking-wider text-paper flex items-center gap-1.5 active:scale-95 transition-transform duration-200 flex-shrink-0">
          <span className="w-2.5 h-6 bg-spot rounded-sm inline-block"></span>
          LIVE<span className="text-spot">WIRE</span>
        </Link>

        {/* Header Search Bar (Desktop) */}
        <div className="hidden md:flex items-center relative flex-1 max-w-xs">
          <input
            type="text"
            value={searchVal}
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder="Search shows, cities..."
            className="field !py-2 !pl-9 !pr-8 text-xs bg-stage/40 border border-white/[0.04] focus:bg-stage focus:border-spot/40 transition-all duration-300"
          />
          <Search className="w-3.5 h-3.5 text-haze/60 absolute left-3 top-2.5" />
          {searchVal && (
            <button 
              onClick={() => handleSearchChange('')}
              className="absolute right-3.5 top-2 text-xs text-haze hover:text-paper font-bold"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Desktop Navigation Links */}
        <nav className="hidden md:flex items-center gap-6 font-body text-sm font-medium">
          <Link to="/" className={`${activeClass('/')} transition-all duration-200`}>Browse</Link>
          {loggedIn && (
            <>
              <Link to="/wishlist" className={`${activeClass('/wishlist')} transition-all duration-200`}>Wishlist</Link>
              <Link to="/bookings" className={`${activeClass('/bookings')} transition-all duration-200`}>My Bookings</Link>
              {!profile?.is_admin && (
                <Link to="/list-your-show" className={`${activeClass('/list-your-show')} transition-all duration-200`}>Host Your Show</Link>
              )}
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
        <div className="hidden md:flex items-center gap-4 flex-shrink-0">
          {loggedIn ? (
            <div className="relative" ref={dropdownRef}>
              <button 
                onClick={() => setDropdownOpen(!dropdownOpen)}
                className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-white/[0.04] bg-stage2/40 hover:bg-stage2/80 transition duration-300 outline-none"
              >
                <span className="w-7 h-7 rounded-full bg-gradient-to-tr from-spot to-[#ff5c84] text-void font-bold text-xs flex items-center justify-center uppercase shadow-sm">
                  {firstName.charAt(0)}
                </span>
                <span className="text-sm font-semibold text-paper max-w-[100px] truncate">{firstName}</span>
                <ChevronDown className={`w-4 h-4 text-haze transition-transform duration-300 ${dropdownOpen ? 'rotate-180' : ''}`} />
              </button>

              {dropdownOpen && (
                <div className="absolute right-0 mt-2 w-48 rounded-xl border border-white/[0.06] bg-stage/95 backdrop-blur-xl shadow-2xl p-2 animate-scale-in flex flex-col gap-1 z-50">
                  <Link 
                    to="/profile" 
                    onClick={() => setDropdownOpen(false)}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-paper hover:bg-stage2/60 transition duration-200"
                  >
                    <User className="w-4 h-4 text-paper" />
                    <span>Profile</span>
                  </Link>
                  <button 
                    onClick={handleLogout}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-spot hover:bg-spot/10 text-left transition duration-200"
                  >
                    <LogOut className="w-4 h-4 text-spot" />
                    <span>Log out</span>
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
          {mobileMenuOpen ? <X className="w-5 h-5 text-paper" /> : <Menu className="w-5 h-5 text-paper" />}
        </button>

      </div>

      {/* Mobile Drawer Menu */}
      {mobileMenuOpen && (
        <div className="md:hidden border-t border-white/[0.04] bg-void/95 backdrop-blur-xl animate-fade-in px-6 py-5 space-y-4 flex flex-col">
          
          {/* Mobile Search Bar */}
          <div className="relative w-full pb-2">
            <input
              type="text"
              value={searchVal}
              onChange={(e) => handleSearchChange(e.target.value)}
              placeholder="Search shows, cities..."
              className="field !py-2 !pl-10 !pr-8 text-sm w-full"
            />
            <Search className="w-4 h-4 text-haze/60 absolute left-3.5 top-5" />
            {searchVal && (
              <button 
                onClick={() => handleSearchChange('')}
                className="absolute right-3.5 top-4.5 text-xs text-haze hover:text-paper font-bold"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          <Link to="/" className="text-base font-medium text-paper py-1 border-b border-white/[0.02]">Browse</Link>
          {loggedIn ? (
            <>
              <Link to="/wishlist" className="text-base font-medium text-paper py-1 border-b border-white/[0.02]">Wishlist</Link>
              <Link to="/bookings" className="text-base font-medium text-paper py-1 border-b border-white/[0.02]">My Bookings</Link>
              {!profile?.is_admin && (
                <Link to="/list-your-show" className="text-base font-medium text-paper py-1 border-b border-white/[0.02]">List Your Show</Link>
              )}
              <Link to="/profile" className="flex items-center gap-2 text-base font-medium text-paper py-1 border-b border-white/[0.02]">
                <User className="w-4 h-4" /> Profile ({firstName})
              </Link>
              {profile?.is_admin && (
                <Link to="/admin" className="flex items-center gap-2 text-base font-medium text-spot2 py-1 border-b border-white/[0.02]">
                  <ShieldCheck className="w-4 h-4" /> Admin Backend
                </Link>
              )}
              <button 
                onClick={handleLogout}
                className="w-full text-center py-2.5 rounded-xl border border-spot/30 text-spot font-bold hover:bg-spot/5 transition flex items-center justify-center gap-2"
              >
                <LogOut className="w-4 h-4" />
                <span>Log out</span>
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