import { Routes, Route, Navigate } from 'react-router-dom'
import NavBar from './components/NavBar'
import HomePage from './pages/HomePage'
import ConcertDetailPage from './pages/ConcertDetailPage'
import AuthPage from './pages/AuthPage'
import AuthCallbackPage from './pages/AuthCallbackPage'
import CompleteProfilePage from './pages/CompleteProfilePage'
import BookingsPage from './pages/BookingsPage'
import ChatPage from './pages/ChatPage'
import AdminPage from './pages/AdminPage'
import WishlistPage from './pages/WishlistPage'
import ProfilePage from './pages/ProfilePage'
import TicketPassPage from './pages/TicketPassPage'
import ListYourShowPage from './pages/ListYourShowPage'
import ArtistProfilePage from './pages/ArtistProfilePage'
import VenueProfilePage from './pages/VenueProfilePage'
import GroupInvitePage from './pages/GroupInvitePage'
import ChatWidget from './components/ChatWidget'
import VoiceWidget from './components/VoiceWidget'
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
          <Route path="/artists/:id" element={<ArtistProfilePage />} />
          <Route path="/venues/:id" element={<VenueProfilePage />} />
          <Route path="/ticket/:bookingId" element={<TicketPassPage />} />
          <Route path="/group-invite/:inviteId" element={<GroupInvitePage />} />
          <Route path="/login" element={<AuthPage />} />
          <Route path="/auth/callback" element={<AuthCallbackPage />} />
          <Route path="/complete-profile" element={<CompleteProfilePage />} />
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
          <Route
            path="/list-your-show"
            element={
              <RequireAuth>
                <ListYourShowPage />
              </RequireAuth>
            }
          />
        </Routes>
      </div>
      <ChatWidget />
      <VoiceWidget />
    </div>
  )
}