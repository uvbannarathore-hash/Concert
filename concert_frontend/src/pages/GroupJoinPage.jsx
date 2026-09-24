import React, { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { api } from '../lib/api';

export default function GroupJoinPage() {
  const { shareToken } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function handleJoin() {
      if (!api.isLoggedIn()) {
        sessionStorage.setItem('pendingRedirect', window.location.pathname);
        navigate('/login', { replace: true });
        return;
      }

      try {
        const res = await api.claimGroupInvite(shareToken);
        if (res.success === false) {
          setError(res.reason || 'Failed to claim invitation.');
          setLoading(false);
          return;
        }
        navigate(`/group-invite/${res.invite_id}`, { replace: true });
      } catch (err) {
        setError(err.message || 'Failed to claim invitation.');
        setLoading(false);
      }
    }

    handleJoin();
  }, [shareToken, navigate]);

  if (loading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center p-6">
        <div className="text-white text-lg flex items-center gap-3">
          <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
          Securing your spot...
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-6">
      <div className="bg-zinc-900 rounded-2xl p-8 max-w-md w-full border border-zinc-800 text-center">
        <div className="text-4xl mb-4">❌</div>
        <h1 className="text-2xl font-bold text-white mb-2">Couldn't join group</h1>
        <p className="text-zinc-400 mb-6">{error}</p>
        <Link to="/" className="inline-block px-6 py-3 bg-white text-black font-semibold rounded-full hover:bg-zinc-200 transition-colors">
          Browse Events
        </Link>
      </div>
    </div>
  );
}
