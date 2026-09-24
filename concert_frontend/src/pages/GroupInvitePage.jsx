import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api } from '../lib/api';

export default function GroupInvitePage() {
  const { inviteId } = useParams();
  const [invite, setInvite] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    fetchInvite();
  }, [inviteId]);

  const fetchInvite = async () => {
    try {
      setLoading(true);
      const data = await api.getGroupInvite(inviteId);
      setInvite(data);
    } catch (err) {
      setError(err.message || 'Failed to load invitation.');
    } finally {
      setLoading(false);
    }
  };

  const handleResponse = async (action) => {
    try {
      setSubmitting(true);
      if (action === 'accept') {
        await api.acceptGroupInvite(inviteId);
      } else {
        await api.declineGroupInvite(inviteId);
      }
      await fetchInvite();
    } catch (err) {
      alert(err.message || 'Failed to submit response.');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center p-6">
        <div className="text-white text-lg">Loading invitation...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center p-6">
        <div className="bg-zinc-900 rounded-2xl p-8 max-w-md w-full border border-zinc-800 text-center">
          <h1 className="text-2xl font-bold text-white mb-4">Oops!</h1>
          <p className="text-zinc-400 mb-6">{error}</p>
          <Link to="/" className="inline-block px-6 py-3 bg-white text-black font-semibold rounded-full hover:bg-zinc-200 transition-colors">
            Go Home
          </Link>
        </div>
      </div>
    );
  }

  const isResponded = invite.status === 'accepted' || invite.status === 'declined';
  const isExpired = invite.session_status === 'expired';
  const isReady = invite.session_status === 'ready';
  const isBooked = invite.session_status === 'booked' || invite.session_status === 'payment_pending';
  const isCancelled = invite.session_status === 'cancelled';
  
  const canRespond = invite.session_status === 'collecting_responses' && invite.status === 'pending';
  const isLoggedIn = api.isLoggedIn();

  return (
    <div className="min-h-screen bg-black text-white flex flex-col items-center justify-center p-6 pt-24">
      <div className="max-w-xl w-full bg-zinc-900 rounded-3xl p-8 md:p-12 border border-zinc-800 shadow-2xl relative overflow-hidden">
        
        {/* Abstract background gradient */}
        <div className="absolute top-0 left-0 right-0 h-32 bg-gradient-to-b from-indigo-900/40 to-transparent pointer-events-none" />

        <div className="relative z-10 text-center mb-10">
          <div className="w-16 h-16 mx-auto bg-indigo-500/20 rounded-2xl flex items-center justify-center mb-6 border border-indigo-500/30">
            <span className="text-3xl">🎫</span>
          </div>
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-3">You're Invited!</h1>
          <p className="text-lg text-zinc-400">
            <span className="text-white font-medium">{invite.initiator_name}</span> wants to go to a concert with you.
          </p>
        </div>

        <div className="bg-black/50 rounded-2xl p-6 mb-10 border border-zinc-800">
          <h2 className="text-2xl font-semibold mb-2">{invite.event_name}</h2>
          <div className="space-y-3 text-zinc-300 mt-4">
            <div className="flex items-start gap-3">
              <span className="text-xl">📅</span>
              <div>
                <p className="font-medium text-white">{invite.event_date}</p>
                <p className="text-sm">{invite.event_time}</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <span className="text-xl">📍</span>
              <div>
                <p className="font-medium text-white">{invite.venue_name}</p>
                <p className="text-sm">{invite.city}</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <span className="text-xl">🎟️</span>
              <div>
                <p className="font-medium text-white">{invite.category} Category</p>
                <p className="text-sm">Group size: {invite.total_seats}</p>
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          {canRespond && (
            <>
              <p className="text-center text-zinc-400 text-sm mb-4">
                Will you join? Let {invite.initiator_name} know!
              </p>
              {!isLoggedIn ? (
                <div className="text-center">
                  <Link
                    to="/login"
                    onClick={() => sessionStorage.setItem('pendingRedirect', window.location.pathname)}
                    className="w-full inline-block py-4 rounded-xl font-bold text-white bg-indigo-600 hover:bg-indigo-500 transition-all text-center"
                  >
                    Log in to respond
                  </Link>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <button
                    onClick={() => handleResponse('accept')}
                    disabled={submitting}
                    className="w-full py-4 rounded-xl font-bold text-white bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {submitting ? 'Updating...' : 'I\'m In! 🤘'}
                  </button>
                  <button
                    onClick={() => handleResponse('decline')}
                    disabled={submitting}
                    className="w-full py-4 rounded-xl font-bold text-white bg-zinc-800 hover:bg-zinc-700 active:bg-zinc-900 transition-all disabled:opacity-50"
                  >
                    {submitting ? 'Updating...' : 'Can\'t make it'}
                  </button>
                </div>
              )}
            </>
          )}

          {!canRespond && (
            <div className="text-center p-6 rounded-2xl bg-zinc-800/50 border border-zinc-700">
              {isExpired && (
                <div>
                  <div className="text-4xl mb-3">⏳</div>
                  <h3 className="text-xl font-bold text-amber-400 mb-1">Time's Up</h3>
                  <p className="text-zinc-400">This group booking invitation has expired.</p>
                </div>
              )}
              {isCancelled && (
                <div>
                  <div className="text-4xl mb-3">❌</div>
                  <h3 className="text-xl font-bold text-red-400 mb-1">Cancelled</h3>
                  <p className="text-zinc-400">This group booking was cancelled by the initiator.</p>
                </div>
              )}
              {isBooked && (
                <div>
                  <div className="text-4xl mb-3">🎉</div>
                  <h3 className="text-xl font-bold text-emerald-400 mb-1">It's Official!</h3>
                  <p className="text-zinc-400">The tickets are booked. See you there!</p>
                </div>
              )}
              {isReady && invite.status === 'accepted' && (
                <div>
                  <div className="text-4xl mb-3">✅</div>
                  <h3 className="text-xl font-bold text-emerald-400 mb-1">You're In!</h3>
                  <p className="text-zinc-400">Everyone accepted. Waiting for {invite.initiator_name} to finalize the payment.</p>
                </div>
              )}
              {invite.status === 'accepted' && invite.session_status === 'collecting_responses' && (
                <div>
                  <div className="text-4xl mb-3">👍</div>
                  <h3 className="text-xl font-bold text-emerald-400 mb-1">You accepted</h3>
                  <p className="text-zinc-400">Waiting for other friends to respond.</p>
                </div>
              )}
              {invite.status === 'declined' && (
                <div>
                  <div className="text-4xl mb-3">👋</div>
                  <h3 className="text-xl font-bold text-zinc-300 mb-1">You declined</h3>
                  <p className="text-zinc-500">Maybe next time!</p>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="mt-8 text-center">
          <Link to="/" className="text-zinc-500 hover:text-white transition-colors text-sm">
            Discover more events on LiveWire
          </Link>
        </div>
      </div>
    </div>
  );
}
