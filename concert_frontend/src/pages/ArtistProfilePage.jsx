import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../lib/api'
import ConcertCard from '../components/ConcertCard'

export default function ArtistProfilePage() {
  const { id } = useParams()
  const [artist, setArtist] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchArtist() {
      try {
        setLoading(true)
        const data = await api.getArtist(id)
        setArtist(data.artist)
      } catch (err) {
        setError(err.message || 'Failed to load artist profile.')
      } finally {
        setLoading(false)
      }
    }
    fetchArtist()
  }, [id])

  if (loading) {
    return (
      <div className="pt-24 min-h-screen flex justify-center p-8">
        <div className="flex space-x-2">
          <div className="w-3 h-3 bg-spot rounded-full animate-bounce"></div>
          <div className="w-3 h-3 bg-spot rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
          <div className="w-3 h-3 bg-spot rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
        </div>
      </div>
    )
  }

  if (error || !artist) {
    return (
      <div className="pt-24 min-h-screen p-8 text-center">
        <p className="text-red-400 font-mono text-xl">{error || 'Artist not found'}</p>
      </div>
    )
  }

  const { upcoming_events = [], past_events = [] } = artist

  return (
    <div className="pt-24 min-h-screen max-w-6xl mx-auto p-4 sm:p-8 animate-fade-in-up">
      {/* Hero Section */}
      <div className="relative glass-card overflow-hidden rounded-2xl mb-12">
        <div className="absolute inset-0 z-0">
          {artist.image_url ? (
            <img 
              src={artist.image_url} 
              alt={artist.name} 
              className="w-full h-full object-cover opacity-30" 
            />
          ) : (
            <div className="w-full h-full bg-gradient-to-br from-spot2/20 to-spot/20"></div>
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-void to-transparent"></div>
        </div>
        
        <div className="relative z-10 p-8 sm:p-12 flex flex-col md:flex-row items-center md:items-start gap-8">
          <div className="w-48 h-48 sm:w-64 sm:h-64 rounded-full overflow-hidden shrink-0 border-4 border-paper/10 shadow-2xl">
            {artist.image_url ? (
              <img 
                src={artist.image_url} 
                alt={artist.name} 
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full bg-paper/5 flex items-center justify-center">
                <span className="text-6xl font-display text-paper/30">{artist.name.charAt(0)}</span>
              </div>
            )}
          </div>
          
          <div className="text-center md:text-left pt-4">
            <h1 className="text-4xl sm:text-6xl font-display uppercase tracking-wider text-paper mb-4 text-glow">
              {artist.name}
            </h1>
            {artist.bio && (
              <p className="text-haze/80 font-body text-lg leading-relaxed max-w-2xl">
                {artist.bio}
              </p>
            )}
            
            {artist.social_links && Object.keys(artist.social_links).length > 0 && (
              <div className="flex gap-4 mt-6 justify-center md:justify-start">
                {Object.entries(artist.social_links).map(([platform, url]) => (
                  <a 
                    key={platform} 
                    href={url} 
                    target="_blank" 
                    rel="noreferrer"
                    className="px-4 py-2 rounded-full glass-card text-spot hover:text-spot2 hover:bg-paper/10 transition-colors text-sm font-semibold capitalize tracking-wide"
                  >
                    {platform}
                  </a>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Upcoming Events */}
      <h2 className="text-2xl font-display text-paper mb-6 tracking-wide flex items-center gap-3">
        <span className="w-2 h-2 rounded-full bg-spot"></span>
        Upcoming Shows
      </h2>
      
      {upcoming_events.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-16">
          {upcoming_events.map(event => (
            <ConcertCard key={event.event_id} event={event} />
          ))}
        </div>
      ) : (
        <div className="glass-card p-12 text-center rounded-xl mb-16">
          <p className="text-haze/60 font-mono">No upcoming shows currently scheduled.</p>
        </div>
      )}

      {/* Past Events */}
      {past_events.length > 0 && (
        <div className="opacity-60 grayscale hover:grayscale-0 transition-all duration-500">
          <h2 className="text-2xl font-display text-paper mb-6 tracking-wide">
            Past Shows
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {past_events.map(event => (
              <ConcertCard key={event.event_id} event={event} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
