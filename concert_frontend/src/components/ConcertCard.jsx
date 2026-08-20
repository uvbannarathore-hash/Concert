import { Link } from 'react-router-dom'

const statusStyles = {
  Upcoming: 'text-go border-go/40 bg-go/10',
  'Sold Out': 'text-spot border-spot/40 bg-spot/10',
  Cancelled: 'text-haze border-edge bg-stage2',
  Completed: 'text-haze border-edge bg-stage2',
}

export default function ConcertCard({ event }) {
  const style = statusStyles[event.status] || statusStyles.Upcoming

  return (
    <Link
      to={`/concerts/${event.event_id}`}
      className="group block rounded-2xl border border-edge bg-stage overflow-hidden
                 hover:border-spot/50 hover:-translate-y-1 transition-all duration-300"
    >
      <div className="h-36 bg-gradient-to-br from-stage2 to-void relative flex items-end p-5">
        <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 bg-spot-radial" />
        <span className={`relative text-[11px] font-mono uppercase tracking-wider px-2.5 py-1 rounded-full border ${style}`}>
          {event.status}
        </span>
      </div>
      <div className="p-5">
        <h3 className="font-display text-2xl leading-none tracking-wide mb-2">
          {event.artist_name}
        </h3>
        <p className="text-sm text-haze mb-3">{event.venue_name}, {event.city}</p>
        <div className="flex items-center justify-between text-xs font-mono text-haze border-t border-edge pt-3">
          <span>{event.event_date}</span>
          <span>{event.event_time}</span>
        </div>
      </div>
    </Link>
  )
}
