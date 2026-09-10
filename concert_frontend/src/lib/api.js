// In dev, falls back to localhost. In production, set VITE_API_URL in your
// hosting provider's environment variables to your deployed backend URL.
const envUrl = import.meta.env.VITE_API_URL
const BASE_URL = (envUrl && envUrl.trim()) ? envUrl.trim().replace(/\/+$/, '') : 'http://127.0.0.1:8000'

function getToken() {
  return localStorage.getItem('access_token')
}

function getRefreshToken() {
  return localStorage.getItem('refresh_token')
}

function setSession({ access_token, refresh_token, user_id, email }) {
  localStorage.setItem('access_token', access_token)
  localStorage.setItem('user_id', user_id)
  localStorage.setItem('email', email)
  // Persist the refresh_token so we can silently renew the access_token
  // when it expires (Supabase default: 1 hour) without forcing a re-login.
  if (refresh_token) localStorage.setItem('refresh_token', refresh_token)
}

function clearSession() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('user_id')
  localStorage.removeItem('email')
}

function getSessionId() {
  // One session_id per browser tab session (short-term memory continuity).
  // A fresh one is generated on each new login, never reused across users.
  let sid = sessionStorage.getItem('chat_session_id')
  if (!sid) {
    sid = crypto.randomUUID()
    sessionStorage.setItem('chat_session_id', sid)
  }
  return sid
}

// Attempts a silent token refresh using the stored refresh_token.
// Returns true if the new access_token was saved, false if refresh failed
// (token expired/revoked) — in which case the session is cleared so the
// next auth check redirects to login cleanly.
let _refreshing = null // deduplicate concurrent refresh attempts
async function tryRefreshToken() {
  if (_refreshing) return _refreshing
  _refreshing = (async () => {
    const refreshToken = getRefreshToken()
    if (!refreshToken) return false
    try {
      // Call Supabase Auth directly — no backend endpoint needed.
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
      if (!supabaseUrl) return false
      const res = await fetch(`${supabaseUrl}/auth/v1/token?grant_type=refresh_token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'apikey': import.meta.env.VITE_SUPABASE_ANON_KEY || '' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })
      if (!res.ok) {
        clearSession()
        return false
      }
      const data = await res.json()
      setSession({
        access_token: data.access_token,
        refresh_token: data.refresh_token,
        user_id: data.user?.id || localStorage.getItem('user_id'),
        email: data.user?.email || localStorage.getItem('email'),
      })
      return true
    } catch {
      clearSession()
      return false
    }
  })()
  try {
    return await _refreshing
  } finally {
    _refreshing = null
  }
}

async function request(path, { method = 'GET', body, auth = false, _retried = false } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (auth) {
    const token = getToken()
    if (!token) throw new Error('Not logged in')
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  })

  // On 401, try a silent token refresh once and replay the request.
  // This handles the common case where the access_token expired mid-session
  // (Supabase default: 1 hour) without forcing the user to log in again.
  if (res.status === 401 && auth && !_retried) {
    const refreshed = await tryRefreshToken()
    if (refreshed) return request(path, { method, body, auth, _retried: true })
    // Refresh failed — session is cleared, surface a clean error.
    throw new Error('Session expired. Please log in again.')
  }

  const data = await res.json().catch(() => ({}))

  if (!res.ok) {
    const message = data.detail
      ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail))
      : `Request failed (${res.status})`
    throw new Error(message)
  }

  return data
}

export const api = {
  // phone, city, and address are now REQUIRED at signup (backend enforces this too)
  signup: (email, password, name, phone, city, address) =>
    request('/auth/signup', { method: 'POST', body: { email, password, name, phone, city, address } }),

  login: async (email, password) => {
    const data = await request('/auth/login', { method: 'POST', body: { email, password } })
    setSession(data)
    // fresh session_id on every new login
    sessionStorage.removeItem('chat_session_id')
    return data
  },

  logout: () => {
    clearSession()
    sessionStorage.removeItem('chat_session_id')
  },

  isLoggedIn: () => !!getToken(),
  currentEmail: () => localStorage.getItem('email'),

  listConcerts: (city, eventType) => {
    const params = new URLSearchParams()
    if (city) params.set('city', city)
    if (eventType) params.set('event_type', eventType)
    const qs = params.toString()
    return request(`/concerts${qs ? `?${qs}` : ''}`)
  },

  getConcert: (eventId) => request(`/concerts/${eventId}`),

  chat: (message) =>
    request('/chat', {
      method: 'POST',
      auth: true,
      body: { message, session_id: getSessionId() },
    }),

  myBookings: () => request('/bookings/me', { auth: true }),

  createOrder: (event_id, category, seats) =>
    request('/bookings/create-order', { method: 'POST', auth: true, body: { event_id, category, seats } }),

  verifyPayment: ({ booking_id, razorpay_order_id, razorpay_payment_id, razorpay_signature }) =>
    request('/bookings/verify-payment', {
      method: 'POST',
      auth: true,
      body: { booking_id, razorpay_order_id, razorpay_payment_id, razorpay_signature },
    }),

  cancelBooking: (bookingId) =>
    request(`/bookings/${bookingId}/cancel`, { method: 'POST', auth: true }),

  myProfile: () => request('/auth/me', { auth: true }),

  // Lets a logged-in user update their name/phone/city/address at any time
  // (e.g. from an Edit Profile page). Only pass the fields you want changed -
  // omit or pass undefined for anything that should stay the same.
  updateProfile: ({ name, phone, city, address } = {}) =>
    request('/auth/me', { method: 'PATCH', auth: true, body: { name, phone, city, address } }),

  getWishlist: () => request('/wishlist', { auth: true }),

  addToWishlist: (eventId) =>
    request('/wishlist', { method: 'POST', auth: true, body: { event_id: eventId } }),

  removeFromWishlist: (eventId) =>
    request(`/wishlist/${eventId}`, { method: 'DELETE', auth: true }),

  // Issues a short-lived LiveKit token for the website speech-to-speech
  // voice booking assistant (see VoiceWidget.jsx).
  getVoiceToken: () => request('/voice/token', { method: 'POST', auth: true }),

  // "List Your Show" - submits an event for admin review. Uses raw fetch
  // (not the request() helper) since this is multipart/form-data - the
  // submission fields go as a JSON string under the 'payload' field
  // alongside an optional poster image file, matching how the admin
  // assistant's image-upload endpoint is structured.
  submitShow: async (submissionData, imageFile) => {
    const token = getToken()
    if (!token) throw new Error('Not logged in')

    const formData = new FormData()
    formData.append('payload', JSON.stringify(submissionData))
    if (imageFile) formData.append('image', imageFile)

    const res = await fetch(`${BASE_URL}/shows/submit`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      const message = data.detail
        ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail))
        : `Request failed (${res.status})`
      throw new Error(message)
    }
    return data
  },

  myShowSubmissions: () => request('/shows/my-submissions', { auth: true }),

  // Seat-map (BookMyShow/PVR-style) - only meaningful for events an admin
  // has built a seat layout for; has_seat_map=false for everything else,
  // in which case the frontend falls back to the plain quantity picker.
  getSeatMap: (eventId) => request(`/concerts/${eventId}/seats`),

  lockSeats: (event_id, seat_ids) =>
    request('/bookings/lock-seats', { method: 'POST', auth: true, body: { event_id, seat_ids } }),

  releaseSeats: (seat_ids) =>
    request('/bookings/release-seats', { method: 'POST', auth: true, body: { seat_ids } }),

  createOrderSeats: (event_id, seat_ids) =>
    request('/bookings/create-order-seats', { method: 'POST', auth: true, body: { event_id, seat_ids } }),

  // Public digital pass endpoint — no auth required, used by QR code scanner / verification page
  getTicketPass: (bookingId) => request(`/bookings/${bookingId}/pass`),
}

export function getPublicPassUrl(bookingId) {
  return `${window.location.origin}/ticket/${bookingId}`
}