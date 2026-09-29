// In dev, falls back to localhost. In production, set VITE_API_URL in your
// hosting provider's environment variables to your deployed backend URL.
const getBaseUrl = () => {
  const envUrl = import.meta.env.VITE_API_URL
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://127.0.0.1:8000'
    }
    // If envUrl is explicitly set to a public URL (e.g. trycloudflare or vercel), use it
    if (envUrl && !envUrl.includes('127.0.0.1') && !envUrl.includes('localhost')) {
      return envUrl.trim().replace(/\/+$/, '')
    }
    // Otherwise, route mobile requests to LAN IP so mobile devices on Wi-Fi reach the backend
    const devIp = import.meta.env.VITE_DEV_HOST_IP || '192.168.11.215'
    return `http://${devIp}:8000`
  }
  return (envUrl && envUrl.trim()) ? envUrl.trim().replace(/\/+$/, '') : 'http://127.0.0.1:8000'
}
export const BASE_URL = getBaseUrl()

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

export function getSessionId() {
  // One session_id per browser tab session (short-term memory continuity).
  // A fresh one is generated on each new login, never reused across users.
  let sid = sessionStorage.getItem('chat_session_id')
  if (!sid) {
    sid = crypto.randomUUID()
    sessionStorage.setItem('chat_session_id', sid)
  }
  return sid
}

export function getPageSessionId() {
  let psid = sessionStorage.getItem('page_view_session_id')
  if (!psid) {
    psid = crypto.randomUUID()
    sessionStorage.setItem('page_view_session_id', psid)
  }
  return psid
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

async function request(path, { method = 'GET', body, auth = false, rawText = false, _retried = false, signal } = {}) {
  const headers = { 
    'Content-Type': 'application/json',
    'Bypass-Tunnel-Reminder': 'true',
    'ngrok-skip-browser-warning': 'true'
  }
  if (auth) {
    const token = getToken()
    if (!token) throw new Error('Not logged in')
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  })

  // On 401, try a silent token refresh once and replay the request.
  // This handles the common case where the access_token expired mid-session
  // (Supabase default: 1 hour) without forcing the user to log in again.
  if (res.status === 401 && auth && !_retried) {
    const refreshed = await tryRefreshToken()
    if (refreshed) return request(path, { method, body, auth, _retried: true, signal })
    // Refresh failed — session is cleared, surface a clean error.
    throw new Error('Session expired. Please log in again.')
  }

  if (rawText) {
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}))
      const message = errData.detail
        ? (typeof errData.detail === 'string' ? errData.detail : JSON.stringify(errData.detail))
        : `Request failed (${res.status})`
      throw new Error(message)
    }
    return res.text()
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
  // Bridge for OAuth flows to inject Supabase sessions into our custom token storage
  setSessionExternal: (sessionData) => setSession(sessionData),

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

  listConcerts: (city, eventType, dateFrom, dateTo, options = {}) => {
    const params = new URLSearchParams()
    if (city) params.set('city', city)
    if (eventType) params.set('event_type', eventType)
    if (dateFrom) params.set('date_from', dateFrom)
    if (dateTo) params.set('date_to', dateTo)
    const qs = params.toString()
    return request(`/concerts${qs ? `?${qs}` : ''}`, options)
  },

  getRecommendations: () => request('/concerts/recommendations', { auth: true }),

  getConcert: (eventId) => request(`/concerts/${eventId}`),

  chat: (message) =>
    request('/chat', {
      method: 'POST',
      auth: true,
      body: { message, session_id: getSessionId() },
    }),

  chatStream: async function* (message) {
    const token = getToken();
    if (!token) throw new Error('Not logged in');
    
    const res = await fetch(`${BASE_URL}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ message, session_id: getSessionId() })
    });
    
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const msg = data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : `Request failed (${res.status})`;
      throw new Error(msg);
    }
    
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      yield decoder.decode(value, { stream: true });
    }
  },

  myBookings: () => request('/bookings/me', { auth: true }),

  createOrder: (event_id, category, seats, coupon_code) =>
    request('/bookings/create-order', { method: 'POST', auth: true, body: { event_id, category, seats, coupon_code } }),

  verifyPayment: ({ booking_id, razorpay_order_id, razorpay_payment_id, razorpay_signature }) =>
    request('/bookings/verify-payment', {
      method: 'POST',
      auth: true,
      body: { booking_id, razorpay_order_id, razorpay_payment_id, razorpay_signature },
    }),

  checkCancellationEligibility: (bookingId) =>
    request(`/bookings/${bookingId}/cancellation-eligibility`, { auth: true }),

  cancelBooking: (bookingId) =>
    request(`/bookings/${bookingId}/cancel`, { method: 'POST', auth: true }),

  initiateRefund: (bookingId) =>
    request(`/bookings/${bookingId}/refund`, { method: 'POST', auth: true }),

  getPaymentRetry: (bookingId) =>
    request(`/bookings/${bookingId}/payment-retry`, { auth: true }),

  myProfile: () => request('/auth/me', { auth: true }),

  // Lets a logged-in user update their name/phone/city/address at any time
  // (e.g. from an Edit Profile page or Organizer Dashboard). Only pass the fields 
  // you want changed - omit or pass undefined for anything that should stay the same.
  updateProfile: ({ name, phone, city, address, payout_upi_id, payout_bank_account, payout_ifsc } = {}) =>
    request('/auth/me', { method: 'PATCH', auth: true, body: { name, phone, city, address, payout_upi_id, payout_bank_account, payout_ifsc } }),

  getWishlist: () => request('/wishlist', { auth: true }),
  
  getPendingPayouts: () => request('/payouts/pending', { auth: true }),
  
  // Admin Payout APIs
  getAdminPayouts: () => request('/admin/payouts', { auth: true }),
  markPayoutsPaid: (ledger_type, ledger_ids) => 
    request('/admin/payouts/mark-paid', { method: 'POST', auth: true, body: { ledger_type, ledger_ids } }),

  addToWishlist: (eventId) =>
    request('/wishlist', { method: 'POST', auth: true, body: { event_id: eventId } }),

  removeFromWishlist: (eventId) =>
    request(`/wishlist/${eventId}`, { method: 'DELETE', auth: true }),

  // Issues a short-lived LiveKit token for the website speech-to-speech
  // voice booking assistant (see ChatWidget.jsx).
  getVoiceToken: (sessionId) => request('/voice/token', { method: 'POST', auth: true, body: { session_id: sessionId } }),

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
  getPricingNotifications: () => request('/shows/pricing-notifications', { auth: true }),
  resolvePricingNotification: (id, payload) => request(`/shows/pricing-notifications/${id}`, {
    method: 'PATCH',
    auth: true,
    body: JSON.stringify(payload)
  }),
  // Seat-map (BookMyShow/PVR-style) - only meaningful for events an admin
  // has built a seat layout for; has_seat_map=false for everything else,
  // in which case the frontend falls back to the plain quantity picker.
  getSeatMap: (eventId) => request(`/concerts/${eventId}/seats`),

  lockSeats: (event_id, seat_ids) =>
    request('/bookings/lock-seats', { method: 'POST', auth: true, body: { event_id, seat_ids } }),

  releaseSeats: (seat_ids) =>
    request('/bookings/release-seats', { method: 'POST', auth: true, body: { seat_ids } }),

  createOrderSeats: (event_id, seat_ids, coupon_code) =>
    request('/bookings/create-order-seats', { method: 'POST', auth: true, body: { event_id, seat_ids, coupon_code } }),

  // Public digital pass endpoint — no auth required, used by QR code scanner / verification page
  getTicketPass: (bookingId) => request(`/bookings/${bookingId}/pass`),

  // Coupons
  validateCoupon: (code, event_id, category, seats) =>
    request('/coupons/validate', { method: 'POST', auth: true, body: { code, event_id, category, seats } }),

  adminCreateCoupon: (data) =>
    request('/admin/coupons', { method: 'POST', auth: true, body: data }),

  adminGetCoupons: () =>
    request('/admin/coupons', { auth: true }),

  adminToggleCoupon: (coupon_id, is_active) =>
    request(`/admin/coupons/${coupon_id}`, { method: 'PATCH', auth: true, body: { is_active } }),

  // Artists
  getArtists: () => request('/artists'),
  getArtist: (artistId) => request(`/artists/${artistId}`),
  adminUpdateArtist: (artistId, data) => request(`/admin/artists/${artistId}`, { method: 'PATCH', auth: true, body: data }),
  adminUploadArtistImage: async (artistId, imageFile) => {
    const token = getToken()
    const formData = new FormData()
    formData.append('image', imageFile)
    const res = await fetch(`${BASE_URL}/admin/artists/${artistId}/upload-image`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    })
    if (!res.ok) throw new Error('Image upload failed')
    return res.json()
  },

  // Venues
  getVenues: () => request('/venues'),
  getVenue: (venueId) => request(`/venues/${venueId}`),
  adminUpdateVenue: (venueId, data) => request(`/admin/venues/${venueId}`, { method: 'PATCH', auth: true, body: data }),
  adminUploadVenueImage: async (venueId, imageFile) => {
    const token = getToken()
    const formData = new FormData()
    formData.append('image', imageFile)
    const res = await fetch(`${BASE_URL}/admin/venues/${venueId}/upload-image`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    })
    if (!res.ok) throw new Error('Image upload failed')
    return res.json()
  },

  adminGetPlatformRevenue: () => request('/admin/platform-revenue', { auth: true }),

  // Reviews
  createReview: (event_id, rating, review_text) =>
    request('/reviews', { method: 'POST', auth: true, body: { event_id, rating, review_text } }),
  
  getReviews: ({ event_id, artist_id, venue_id }) => {
    const params = new URLSearchParams()
    if (event_id) params.set('event_id', event_id)
    if (artist_id) params.set('artist_id', artist_id)
    if (venue_id) params.set('venue_id', venue_id)
    return request(`/reviews?${params.toString()}`)
  },

  getReviewSummary: ({ event_id, artist_id, venue_id }) => {
    const params = new URLSearchParams()
    if (event_id) params.set('event_id', event_id)
    if (artist_id) params.set('artist_id', artist_id)
    if (venue_id) params.set('venue_id', venue_id)
    return request(`/reviews/summary?${params.toString()}`)
  },

  // Waitlist endpoints
  joinWaitlist: (eventId) => request(`/waitlist/join/${eventId}`, { method: 'POST', auth: true }),
  getWaitlistStatus: (eventId) => request(`/waitlist/status/${eventId}`, { auth: true }),
  leaveWaitlist: (eventId) => request(`/waitlist/leave/${eventId}`, { method: 'DELETE', auth: true }),

  // AI Semantic Search
  semanticSearch: (query, options = {}) => request('/ai/search', { method: 'POST', body: { query }, ...options }),

  // Buy Advice Demand Signal
  getBuyAdvice: (eventId) => request(`/ai/events/${eventId}/buy-advice`),
  getMyItineraries: () => request('/ai/my-itineraries', { auth: true }),

  // Group Bookings
  getGroupInvite: (inviteId) => request(`/group-invite/${inviteId}`),
  acceptGroupInvite: (inviteId) => request(`/group-invite/${inviteId}/accept`, { method: 'POST', auth: true }),
  declineGroupInvite: (inviteId) => request(`/group-invite/${inviteId}/decline`, { method: 'POST', auth: true }),
  claimGroupInvite: (shareToken) => request(`/group-invite/claim/${shareToken}`, { method: 'POST', auth: true }),

  // Resale
  listResaleTicket: (payload) => request('/resale/list', { method: 'POST', auth: true, body: payload }),
  getResaleTickets: (eventId) => request(`/resale/events/${eventId}/tickets`),
  createResaleOrder: (listingId) => request('/resale/create-order', { method: 'POST', auth: true, body: { listing_id: listingId } }),
  buyResaleTicket: (payload) => request('/resale/buy', { method: 'POST', auth: true, body: payload }),
  cancelResaleListing: (listingId) => request(`/resale/${listingId}/cancel`, { method: 'POST', auth: true }),
  getMyResaleListings: () => request('/resale/my-listings', { auth: true }),
  getMySoldTickets: () => request('/resale/my-sold-tickets', { auth: true }),

  // --- Organizer Endpoints ---
  upgradePlan: (plan_tier) => request('/organizer/plan/upgrade', { method: 'POST', body: { plan_tier }, auth: true }),
  verifyPlanUpgrade: (payload) => request('/organizer/plan/upgrade/verify', { method: 'POST', body: payload, auth: true }),
  updatePayoutDetails: (payload) => request('/organizer/payout-details', { method: 'PATCH', body: payload, auth: true }),
  cancelOrganizerEvent: (eventId) => request(`/organizer/events/${eventId}/cancel`, { method: 'POST', auth: true }),

  // --- LiveWire Plus Membership ---
  getMembershipStatus: () => request('/membership/status', { auth: true }),
  subscribePlus: (plan_type) => request('/membership/subscribe', { method: 'POST', body: { plan_type }, auth: true }),
  verifyPlusSubscription: (payload) => request('/membership/subscribe/verify', { method: 'POST', body: payload, auth: true }),

  subscribeInsider: (payload) => request('/insider/subscribe', { method: 'POST', body: payload, auth: true }),
  
  // --- Organizer ---
  getOrganizerEvents: () => request('/organizer/events', { auth: true }),
  updateTrackingIds: (eventId, payload) => request(`/organizer/analytics/events/${eventId}/tracking`, { method: 'PATCH', body: payload, auth: true }),
  trackPageView: (payload) => request('/organizer/analytics/track-view', { method: 'POST', body: payload }),
  exportAttendeesCsv: (eventId) => request(`/organizer/analytics/events/${eventId}/export-attendees`, { auth: true, rawText: true }),
  getEventStats: (eventId) => request(`/organizer/analytics/events/${eventId}/stats`, { auth: true }),
}


export function getPublicPassUrl(bookingId) {
  // If a public URL (e.g. Vercel deployment or tunnel URL) is set, use it for mobile data compatibility
  const publicUrl = import.meta.env.VITE_PUBLIC_URL
  if (publicUrl && publicUrl.trim()) {
    return `${publicUrl.trim().replace(/\/+$/, '')}/ticket/${bookingId}`
  }

  const origin = window.location.origin
  if (origin.includes('localhost') || origin.includes('127.0.0.1')) {
    const localIp = import.meta.env.VITE_DEV_HOST_IP || '192.168.11.215'
    const port = window.location.port || '5173'
    return `http://${localIp}:${port}/ticket/${bookingId}`
  }
  return `${origin}/ticket/${bookingId}`
}
