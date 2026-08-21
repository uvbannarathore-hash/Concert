const BASE_URL = 'http://127.0.0.1:8000'

function getToken() {
  return localStorage.getItem('access_token')
}

function setSession({ access_token, user_id, email }) {
  localStorage.setItem('access_token', access_token)
  localStorage.setItem('user_id', user_id)
  localStorage.setItem('email', email)
}

function clearSession() {
  localStorage.removeItem('access_token')
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

async function request(path, { method = 'GET', body, auth = false } = {}) {
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
  signup: (email, password, name) =>
    request('/auth/signup', { method: 'POST', body: { email, password, name } }),

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

  createBooking: (event_id, category, seats, payment_method) =>
    request('/bookings', { method: 'POST', auth: true, body: { event_id, category, seats, payment_method } }),

  cancelBooking: (bookingId) =>
    request(`/bookings/${bookingId}/cancel`, { method: 'POST', auth: true }),

  myProfile: () => request('/auth/me', { auth: true }),

  getWishlist: () => request('/wishlist', { auth: true }),

  addToWishlist: (eventId) =>
    request('/wishlist', { method: 'POST', auth: true, body: { event_id: eventId } }),

  removeFromWishlist: (eventId) =>
    request(`/wishlist/${eventId}`, { method: 'DELETE', auth: true }),
}
