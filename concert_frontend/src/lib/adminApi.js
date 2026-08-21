import { api } from './api'

// Re-uses the same request/auth pattern as api.js, just for /admin/* routes.
// Kept separate so normal users never even load admin logic.

const BASE_URL = 'http://127.0.0.1:8000'

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
  chat: (message) => adminRequest('/admin/agent-chat', { method: 'POST', body: { message } }),
}
