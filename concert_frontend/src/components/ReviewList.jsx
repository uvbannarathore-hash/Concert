import { useEffect, useState } from 'react'
import { api } from '../lib/api'

export default function ReviewList({ eventId, artistId, venueId }) {
  const [reviews, setReviews] = useState([])
  const [averageRating, setAverageRating] = useState(0)
  const [totalReviews, setTotalReviews] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    async function load() {
      try {
        setLoading(true)
        const data = await api.getReviews({ event_id: eventId, artist_id: artistId, venue_id: venueId })
        setReviews(data.reviews || [])
        setAverageRating(data.average_rating || 0)
        setTotalReviews(data.total_reviews || 0)
      } catch (err) {
        setError(err.message)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [eventId, artistId, venueId])

  if (loading) {
    return <div className="text-xs font-mono text-haze">Loading reviews...</div>
  }

  if (error) {
    return <div className="text-xs font-mono text-spot">⚠️ {error}</div>
  }

  if (reviews.length === 0) {
    return (
      <div className="text-xs font-mono text-haze italic">
        No reviews yet. Check back later!
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Summary */}
      <div className="flex items-center gap-4">
        <div className="text-4xl font-display text-paper">{averageRating}</div>
        <div>
          <div className="flex text-yellow-400 text-lg">
            {[1, 2, 3, 4, 5].map((star) => (
              <span key={star} className={star <= Math.round(averageRating) ? 'text-yellow-400' : 'text-white/20'}>★</span>
            ))}
          </div>
          <div className="text-[10px] font-mono text-haze uppercase mt-1">
            Based on {totalReviews} review{totalReviews !== 1 ? 's' : ''}
          </div>
        </div>
      </div>

      {/* List */}
      <div className="space-y-4">
        {reviews.map((r) => (
          <div key={r.id} className="p-4 rounded-xl border border-white/[0.04] bg-white/[0.01]">
            <div className="flex items-start justify-between mb-2">
              <div>
                <span className="text-sm font-semibold text-paper mr-2">{r.users?.name || 'Anonymous'}</span>
                {!eventId && (
                  <span className="text-[10px] font-mono text-haze/60 uppercase">
                    for {r.events?.artist_name} @ {r.events?.venue_name}
                  </span>
                )}
              </div>
              <div className="text-yellow-400 text-xs tracking-widest">
                {'★'.repeat(r.rating)}{'☆'.repeat(5 - r.rating)}
              </div>
            </div>
            {r.review_text && (
              <p className="text-sm text-haze/90 leading-relaxed font-body">
                {r.review_text}
              </p>
            )}
            <div className="text-[10px] font-mono text-haze/40 mt-3 uppercase">
              {new Date(r.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
