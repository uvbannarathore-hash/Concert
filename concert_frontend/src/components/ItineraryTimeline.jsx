import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'

// Fix Leaflet's default icon path issues
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})


export default function ItineraryTimeline() {
  const [itineraries, setItineraries] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getMyItineraries()
      .then(data => setItineraries(data.results || []))
      .catch(err => console.error(err))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex justify-center py-10">
        <div className="w-8 h-8 border-4 border-spot border-t-transparent rounded-full animate-spin"></div>
      </div>
    )
  }

  if (itineraries.length === 0) {
    return (
      <div className="text-center py-10 text-haze">
        You haven't planned any nights yet. Ask the AI concierge to "Plan my night"!
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {itineraries.map((itin) => {
        const plan = itin.plan_json || {}
        const eventTitle = itin.events?.artist_name || 'Event'
        const eventDate = itin.events?.event_date ? new Date(itin.events.event_date).toLocaleDateString() : ''
        
        // Extract restaurant and cab info safely
        const restaurants = plan.restaurant_options || []
        let dinnerName = "Dinner"
        if (plan.dinner) {
           dinnerName = typeof plan.dinner === 'object' ? plan.dinner.name : plan.dinner
        }
        const topRestaurant = restaurants.length > 0 ? restaurants[0] : (plan.dinner ? {name: dinnerName, cuisine: "Unknown", estimated_cost_for_two_inr: plan.dinner_budget || (plan.dinner.total_cost || 0)} : null)
        const directions = plan.travel_directions || (plan.travel_cost ? {estimated_time_mins: '?', distance_km: '?', estimated_cab_fare_inr: plan.travel_cost} : {})
        
        const hasCoords = plan.venue_lat && plan.venue_lon && topRestaurant?.lat && topRestaurant?.lon
        const centerLat = hasCoords ? (plan.venue_lat + topRestaurant.lat) / 2 : 0
        const centerLon = hasCoords ? (plan.venue_lon + topRestaurant.lon) / 2 : 0

        return (
          <div key={itin.id} className="glass-card bg-stage/15 border border-white/[0.04] rounded-2xl p-6 shadow-2xl relative overflow-hidden">
            {/* Header */}
            <div className="mb-6 pb-4 border-b border-white/[0.04] flex justify-between items-start">
              <div>
                <p className="text-xs uppercase tracking-widest text-spot mb-1">Your AI Itinerary</p>
                <h3 className="text-xl font-display uppercase text-paper">{eventTitle}</h3>
                <p className="text-sm font-mono text-haze mt-1">{eventDate}</p>
              </div>
              <div className="text-right">
                <p className="text-[10px] uppercase font-mono text-haze/60">Grand Total</p>
                <p className="text-xl font-bold text-go">₹{plan.grand_total_inr || plan.total_cost || 'N/A'}</p>
              </div>
            </div>

            {/* Timeline */}
            <div className="relative pl-6 space-y-8 before:absolute before:inset-0 before:ml-2 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-white/[0.1] before:to-transparent">
              
              {/* Step 1: Restaurant */}
              {topRestaurant && (
                <div className="relative">
                  <div className="absolute left-[-29px] w-6 h-6 bg-stage border border-white/20 rounded-full flex items-center justify-center text-xs">
                    🍽️
                  </div>
                  <div className="pl-4">
                    <h4 className="text-paper font-bold uppercase">{topRestaurant.name}</h4>
                    <p className="text-xs text-haze mt-1">Cuisine: {topRestaurant.cuisine}</p>
                    <p className="text-xs text-haze font-mono mt-1">Cost for two: ₹{topRestaurant.estimated_cost_for_two_inr}</p>
                    
                    {topRestaurant.google_maps_url && (
                      <a href={topRestaurant.google_maps_url} target="_blank" rel="noreferrer" className="inline-block mt-3 px-4 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-widest border border-white/10 hover:border-white/30 text-white transition-colors bg-white/5 hover:bg-white/10">
                        Get Directions
                      </a>
                    )}
                  </div>
                </div>
              )}

              {/* Step 2: Travel */}
              <div className="relative">
                <div className="absolute left-[-29px] w-6 h-6 bg-stage border border-white/20 rounded-full flex items-center justify-center text-xs">
                  🚕
                </div>
                <div className="pl-4">
                  <h4 className="text-paper font-bold uppercase">Cab to Venue</h4>
                  <p className="text-xs text-haze mt-1">
                    {directions.estimated_time_mins} mins away ({directions.distance_km} km)
                  </p>
                  <p className="text-xs text-haze font-mono mt-1">Est. Fare: ₹{directions.estimated_cab_fare_inr}</p>
                  
                  {directions.uber_deep_link && (
                    <a href={directions.uber_deep_link} target="_blank" rel="noreferrer" className="inline-block mt-3 px-4 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-widest border border-black hover:border-black text-black transition-colors bg-white hover:bg-gray-200">
                      Book Uber
                    </a>
                  )}
                </div>
              </div>

              {/* Step 3: Event */}
              <div className="relative">
                <div className="absolute left-[-29px] w-6 h-6 bg-spot border border-spot rounded-full flex items-center justify-center text-xs">
                  🎫
                </div>
                <div className="pl-4">
                  <h4 className="text-paper font-bold uppercase">{eventTitle}</h4>
                  <p className="text-xs text-haze mt-1">{itin.events?.venue_name}</p>
                  
                  <div className="mt-3">
                    <span className="inline-block px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest bg-spot/20 text-spot border border-spot/30">
                      Tickets Secured
                    </span>
                  </div>
                </div>
              </div>
              
              {/* Map */}
              {hasCoords && (
                <div className="mt-8 rounded-xl overflow-hidden border border-white/10" style={{ height: '200px' }}>
                  <MapContainer center={[centerLat, centerLon]} zoom={14} scrollWheelZoom={false} style={{ height: '100%', width: '100%' }}>
                    <TileLayer
                      attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                      url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                      className="map-tiles"
                    />
                    <Marker position={[topRestaurant.lat, topRestaurant.lon]}>
                      <Popup className="text-black">
                        <strong className="text-black">{topRestaurant.name}</strong><br/>Dinner
                      </Popup>
                    </Marker>
                    <Marker position={[plan.venue_lat, plan.venue_lon]}>
                      <Popup className="text-black">
                        <strong className="text-black">{eventTitle}</strong><br/>Venue
                      </Popup>
                    </Marker>
                  </MapContainer>
                </div>
              )}

              
            </div>
          </div>
        )
      })}
    </div>
  )
}
