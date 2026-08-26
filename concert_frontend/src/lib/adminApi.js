import { api } from './api'

// Re-uses the same request/auth pattern as api.js, just for /admin/* routes.
// Kept separate so normal users never even load admin logic.

// Same env-based URL as api.js — set VITE_API_URL in production.
const BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

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
  dashboardStats: () => adminRequest('/admin/dashboard-stats'),
  listConcerts: () => api.listConcerts(),

  // Chat now supports an optional image file (e.g. event poster) AND an
  // optional venue location (lat/lng) picked via Google Places Autocomplete.
  // Uses multipart/form-data since it may carry a binary file.
  chat: async (message, imageFile, venueLocation) => {
    const token = localStorage.getItem('access_token')
    if (!token) throw new Error('Not logged in')

    const formData = new FormData()
    formData.append('message', message)
    if (imageFile) formData.append('image', imageFile)
    if (venueLocation) {
      formData.append('latitude', venueLocation.latitude)
      formData.append('longitude', venueLocation.longitude)
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
}