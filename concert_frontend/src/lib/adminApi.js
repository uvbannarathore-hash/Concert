import { api, BASE_URL } from './api'

// Re-uses the same request/auth pattern as api.js, just for /admin/* routes.
// Kept separate so normal users never even load admin logic.

async function adminRequest(path, { method = 'GET', body } = {}) {
  const token = localStorage.getItem('access_token')
  if (!token) throw new Error('Not logged in')

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: body ? JSON.stringify(body) : undefined,
  })

  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const message = data.detail
      ? typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
      : `Request failed (${res.status})`
    throw new Error(message)
  }
  return data
}

export const adminApi = {
  createEvent: (payload) => adminRequest('/admin/events', { method: 'POST', body: payload }),
  updateEventStatus: (eventId, status) =>
    adminRequest(`/admin/events/${eventId}/status`, { method: 'PATCH', body: { status } }),
  addTicketCategory: (payload) => adminRequest('/admin/ticket-categories', { method: 'POST', body: payload }),
  updatePricing: (eventId, category, price_inr) =>
    adminRequest(`/admin/ticket-categories/${eventId}/${category}`, { method: 'PATCH', body: { price_inr } }),
  allBookings: () => adminRequest('/admin/bookings'),
  listConcerts: () => api.listConcerts(),

  // Chat now supports an optional image file (e.g. event poster) AND an
  // optional venue location (lat/lng) picked via Google Places Autocomplete.
  // Uses multipart/form-data since it may carry a binary file.
  chat: async (message, imageFile, venueLocation, sessionId) => {
    const token = localStorage.getItem('access_token')
    if (!token) throw new Error('Not logged in')

    const formData = new FormData()
    formData.append('message', message)
    if (imageFile) formData.append('image', imageFile)
    if (venueLocation) {
      formData.append('latitude', venueLocation.latitude)
      formData.append('longitude', venueLocation.longitude)
    }
    if (sessionId) {
      formData.append('session_id', sessionId)
    }

    const res = await fetch(`${BASE_URL}/admin/agent-chat`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        // Do NOT set Content-Type manually - the browser sets the correct
        // multipart/form-data boundary automatically when body is FormData.
      },
      body: formData,
    })

    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      const message = data.detail
        ? typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
        : `Request failed (${res.status})`
      throw new Error(message)
    }
    return data
  },

  // "List Your Show" review queue
  getShowSubmissions: (status = 'Pending') =>
    adminRequest(`/admin/show-submissions?status=${encodeURIComponent(status)}`),

  approveShowSubmission: (submissionId) =>
    adminRequest(`/admin/show-submissions/${submissionId}/approve`, { method: 'POST' }),

  rejectShowSubmission: (submissionId, reason) =>
    adminRequest(`/admin/show-submissions/${submissionId}/reject`, {
      method: 'POST',
      body: { reason },
    }),

  // Seat layout builder — defines the interactive seat map for an event,
  // one row at a time (see seat_selection_migration.sql). Events with no
  // rows added stay on the plain quantity-based booking flow.
  addSeatRow: (payload) => adminRequest('/admin/seat-layout/add-row', { method: 'POST', body: payload }),
  getSeatLayout: (eventId) => adminRequest(`/admin/seat-layout/${eventId}`),
  deleteSeatRow: (eventId, seatRow) =>
    adminRequest(`/admin/seat-layout/${eventId}/row/${encodeURIComponent(seatRow)}`, { method: 'DELETE' }),

  // Analytics Dashboard
  getAnalyticsOverview: () => adminRequest('/admin/analytics/overview'),
  getAnalyticsRevenue: () => adminRequest('/admin/analytics/revenue'),
  getAnalyticsBookings: () => adminRequest('/admin/analytics/bookings'),
  getTopEvents: () => adminRequest('/admin/analytics/top-events'),
  getCategorySales: () => adminRequest('/admin/analytics/category-sales'),

  // Pricing Notifications
  getPricingNotifications: () => adminRequest('/admin/pricing-notifications'),
  resolvePricingNotification: (notificationId, action, finalPrice) =>
    adminRequest(`/admin/pricing-notifications/${notificationId}`, {
      method: 'PATCH',
      body: { action, final_price: finalPrice }
    }),
}