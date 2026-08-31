import { Routes, Route, Navigate } from 'react-router-dom'
import NavBar from './components/NavBar'
import HomePage from './pages/HomePage'
import ConcertDetailPage from './pages/ConcertDetailPage'
import AuthPage from './pages/AuthPage'
import BookingsPage from './pages/BookingsPage'
import ChatPage from './pages/ChatPage'
import AdminPage from './pages/AdminPage'
import WishlistPage from './pages/WishlistPage'
import ProfilePage from './pages/ProfilePage'
import TicketPassPage from './pages/TicketPassPage'
import ChatWidget from './components/ChatWidget'
import { api } from './lib/api'

function RequireAuth({ children }) {
  return api.isLoggedIn() ? children : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <div className="min-h-screen bg-void flex flex-col justify-between">
      <div className="w-full flex-grow">
        <NavBar />
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/concerts/:eventId" element={<ConcertDetailPage />} />
          <Route path="/ticket/:bookingId" element={<TicketPassPage />} />
          <Route path="/login" element={<AuthPage />} />
          <Route
            path="/bookings"
            element={
              <RequireAuth>
                <BookingsPage />
              </RequireAuth>
            }
          />
          <Route
            path="/chat"
            element={
              <RequireAuth>
                <ChatPage />
              </RequireAuth>
            }
          />
          <Route
            path="/admin"
            element={
              <RequireAuth>
                <AdminPage />
              </RequireAuth>
            }
          />
          <Route
            path="/wishlist"
            element={
              <RequireAuth>
                <WishlistPage />
              </RequireAuth>
            }
          />
          <Route
            path="/profile"
            element={
              <RequireAuth>
                <ProfilePage />
              </RequireAuth>
            }
          />
        </Routes>
      </div>
      <ChatWidget />
    </div>
  )
}