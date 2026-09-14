import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../lib/api'
import { MapPin } from 'lucide-react'
import ConcertCard from '../components/ConcertCard'
import ReviewList from '../components/ReviewList'

export default function VenueProfilePage() {
  const { id } = useParams()
  const [venue, setVenue] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [upcomingEvents, setUpcomingEvents] = useState([])
  const [pastEvents, setPastEvents] = useState([])

  useEffect(() => {
    async function fetchVenue() {
      try {
        setLoading(true)
        const data = await api.getVenue(id)
        setVenue(data.venue)
        setUpcomingEvents(data.upcoming_events || [])
        setPastEvents(data.past_events || [])
      } catch (err) {
        setError(err.message || 'Failed to load venue profile.')
      } finally {
        setLoading(false)
      }
    }
    fetchVenue()
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

  if (error || !venue) {
    return (
      <div className="pt-24 min-h-screen p-8 text-center">
        <p className="text-red-400 font-mono text-xl">{error || 'Venue not found'}</p>
      </div>
    )
  }

  return (
    <div className="pt-24 min-h-screen max-w-6xl mx-auto p-4 sm:p-8 animate-fade-in-up">
      {/* Hero Section */}
      <div className="relative glass-card overflow-hidden rounded-2xl mb-12">
        <div className="absolute inset-0 z-0">
          {venue.image_url ? (
            <img 
              src={venue.image_url} 
              alt={venue.name} 
              className="w-full h-full object-cover opacity-30" 
            />
          ) : (
            <div className="w-full h-full bg-gradient-to-br from-spot2/20 to-spot/20"></div>
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-void to-transparent"></div>
        </div>
        
        <div className="relative z-10 p-8 sm:p-12 flex flex-col md:flex-row items-center md:items-start gap-8">
          <div className="w-48 h-48 sm:w-64 sm:h-64 rounded-xl overflow-hidden shrink-0 border-4 border-paper/10 shadow-2xl">
            {venue.image_url ? (
              <img 
                src={venue.image_url} 
                alt={venue.name} 
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full bg-paper/5 flex items-center justify-center">
                <span className="text-6xl font-display text-paper/30">{venue.name.charAt(0)}</span>
              </div>
            )}
          </div>
          
          <div className="text-center md:text-left pt-4 flex-1">
            <h1 className="text-4xl sm:text-6xl font-display uppercase tracking-wider text-paper mb-2 text-glow">
              {venue.name}
            </h1>
            <h2 className="text-xl sm:text-2xl font-display text-spot2 tracking-wide mb-4 uppercase">
              {venue.city}
            </h2>
            
            {venue.address && (
              <p className="text-haze/80 font-body text-base leading-relaxed mb-4 flex items-center gap-2 justify-center md:justify-start">
                <MapPin className="w-4 h-4 text-spot flex-shrink-0" /> {venue.address}
              </p>
            )}
            
            {venue.capacity && (
              <p className="text-haze/60 font-mono text-xs uppercase tracking-wider mb-6 border border-white/10 rounded-full px-3 py-1 inline-block">
                Capacity: {venue.capacity.toLocaleString()}
              </p>
            )}
          </div>
        </div>
      </div>

      {venue.latitude != null && venue.longitude != null && (
        <div className="border border-white/[0.04] p-4 rounded-2xl bg-stage/20 mb-12 shadow-xl">
          <h3 className="font-display text-lg tracking-wider text-paper uppercase mb-4 px-2">Location Map</h3>
          <div className="w-full h-64 rounded-xl overflow-hidden border border-white/[0.04] bg-stage2/20">
            <iframe
              width="100%"
              height="100%"
              style={{ border: 0 }}
              loading="lazy"
              allowFullScreen
              referrerPolicy="no-referrer-when-downgrade"
              src={`https://maps.google.com/maps?q=${venue.latitude},${venue.longitude}&z=15&output=embed`}
            ></iframe>
          </div>
        </div>
      )}

      {/* Upcoming Events */}
      <h2 className="text-2xl font-display text-paper mb-6 tracking-wide flex items-center gap-3">
        <span className="w-2 h-2 rounded-full bg-spot"></span>
        Upcoming Events at this Venue
      </h2>
      
      {upcomingEvents.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-16">
          {upcomingEvents.map(event => (
            <ConcertCard key={event.event_id} event={event} />
          ))}
        </div>
      ) : (
        <div className="glass-card p-12 text-center rounded-xl mb-16">
          <p className="text-haze/60 font-mono">No upcoming events currently scheduled here.</p>
        </div>
      )}

      {/* Past Events */}
      {pastEvents.length > 0 && (
        <div className="opacity-60 grayscale hover:grayscale-0 transition-all duration-500">
          <h2 className="text-2xl font-display text-paper mb-6 tracking-wide">
            Past Events
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {pastEvents.map(event => (
              <ConcertCard key={event.event_id} event={event} />
            ))}
          </div>
        </div>
      )}

      {/* Reviews */}
      <div className="mt-16 border-t border-white/[0.04] pt-12">
        <h2 className="text-2xl font-display text-paper mb-8 tracking-wide">
          Venue Reviews
        </h2>
        <div className="max-w-2xl">
          <ReviewList venueId={id} />
        </div>
      </div>
    </div>
  )
}
