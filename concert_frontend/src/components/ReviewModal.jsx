import { useState } from 'react'
import { createPortal } from 'react-dom'
import { api } from '../lib/api'

export default function ReviewModal({ isOpen, onClose, event, onSuccess }) {
  const [rating, setRating] = useState(0)
  const [hoverRating, setHoverRating] = useState(0)
  const [reviewText, setReviewText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  if (!isOpen || !event) return null

  async function handleSubmit(e) {
    e.preventDefault()
    if (rating === 0) {
      setError('Please select a rating.')
      return
    }

    setLoading(true)
    setError('')
    try {
      await api.createReview(event.event_id, rating, reviewText.trim() || undefined)
      if (onSuccess) onSuccess()
      onClose()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const modalContent = (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-void/80 backdrop-blur-sm p-4 animate-fade-in">
      <div className="bg-stage border border-white/[0.08] rounded-2xl w-full max-w-md p-6 sm:p-8 relative shadow-2xl">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-haze hover:text-white transition"
        >
          ✕
        </button>
        <h2 className="font-display text-2xl uppercase tracking-wide text-paper mb-1">
          Leave a Review
        </h2>
        <p className="text-xs text-haze mb-6">
          For {event.artist_name || 'Event'} at {event.venue_name || 'Venue'}
        </p>

        {error && (
          <div className="border border-spot/20 bg-spot/5 text-spot text-[11px] font-mono rounded-lg p-3 mb-4">
            ⚠️ {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label className="block text-[10px] font-mono text-haze mb-2 uppercase tracking-wider">
              Rating
            </label>
            <div className="flex gap-2">
              {[1, 2, 3, 4, 5].map((star) => (
                <button
                  key={star}
                  type="button"
                  onMouseEnter={() => setHoverRating(star)}
                  onMouseLeave={() => setHoverRating(0)}
                  onClick={() => setRating(star)}
                  className={`text-3xl transition-transform ${
                    (hoverRating || rating) >= star ? 'text-yellow-400 scale-110' : 'text-white/20'
                  }`}
                >
                  ★
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-mono text-haze mb-2 uppercase tracking-wider">
              Review (Optional)
            </label>
            <textarea
              value={reviewText}
              onChange={(e) => setReviewText(e.target.value)}
              placeholder="What did you think of the show?"
              className="w-full bg-void border border-white/[0.06] rounded-xl px-4 py-3 text-sm text-paper h-28 resize-none focus:border-white/[0.2] transition-colors outline-none"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-paper text-void font-bold uppercase tracking-widest text-xs py-4 rounded-xl hover:bg-white transition-colors disabled:opacity-50"
          >
            {loading ? 'Submitting...' : 'Submit Review'}
          </button>
        </form>
      </div>
    </div>
  )

  return createPortal(modalContent, document.body)
}
