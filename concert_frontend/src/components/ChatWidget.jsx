import { useEffect, useState, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from '../lib/api'
import { createClient } from '@supabase/supabase-js'

// Supabase client for realtime updates
const supabase = createClient(
  'https://yacolxewrrlsxsbblulr.supabase.co',
  'sb_publishable_bE-bCQUEYfZ2VVdQFP-yLQ_ALz82-tN'
)

function linkify(text) {
  const urlPattern = /(https?:\/\/[^\s]+)/g
  const parts = []
  let lastIndex = 0
  let match

  while ((match = urlPattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index))
    }
    parts.push(
      <a
        key={match.index}
        href={match[0]}
        target="_blank"
        rel="noopener noreferrer"
        className="underline underline-offset-4 text-spot2 hover:text-spot transition break-all"
      >
        {match[0]}
      </a>
    )
    lastIndex = match.index + match[0].length
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }

  return parts
}

export default function ChatWidget() {
  const location = useLocation()
  const [loggedIn, setLoggedIn] = useState(api.isLoggedIn())
  const [isAdmin, setIsAdmin] = useState(null) // null = "not checked yet"
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: "Hey! I'm your AI booking assistant. Ask me to find concerts, check seat availability, view your tickets, or handle reservation questions!",
    },
  ])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  
  const bottomRef = useRef(null)
  const drawerRef = useRef(null)

  // Keep loggedIn state in sync with route changes or storage events
  useEffect(() => {
    const checkLogin = () => setLoggedIn(api.isLoggedIn())
    checkLogin()
    window.addEventListener('storage', checkLogin)
    return () => window.removeEventListener('storage', checkLogin)
  }, [location.pathname])

  // Admins get their own agent-chat inside the Admin dashboard - this
  // customer-facing widget should stay hidden for them, same as NavBar
  // only shows the customer nav links to non-admins.
  useEffect(() => {
    if (!loggedIn) {
      setIsAdmin(null)
      return
    }
    api.myProfile().then((p) => setIsAdmin(!!p?.is_admin)).catch(() => {})
  }, [loggedIn])

  // Scroll to bottom when messages update
  useEffect(() => {
    if (isOpen) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, sending, isOpen])

  // Listen for realtime booking confirmations when logged in
  useEffect(() => {
    if (!loggedIn) return

    const userId = localStorage.getItem('user_id')
    if (!userId) return

    const channel = supabase
      .channel(`bookings-user-widget-${userId}`)
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'bookings',
          filter: `user_id=eq.${userId}`,
        },
        (payload) => {
          const wasConfirmed = payload.old?.status === 'Confirmed'
          const isNowConfirmed = payload.new?.status === 'Confirmed'

          if (isNowConfirmed && !wasConfirmed) {
            const b = payload.new
            setMessages((m) => [
              ...m,
              {
                role: 'assistant',
                text: `🎉 Your booking is confirmed!\n\nBooking ID: ${b.booking_id}\nCategory: ${b.category}\nSeats: ${b.seats_booked}\n\nSee you at the show!`,
              },
            ])
            setIsOpen(true) // Open widget to notify user
          }
        }
      )
      .subscribe()

    return () => {
      supabase.removeChannel(channel)
    }
  }, [loggedIn])

  // Close widget when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (drawerRef.current && !drawerRef.current.contains(event.target) && !event.target.closest('.user-chat-fab')) {
        setIsOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  async function handleSend(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || sending) return
    
    
    if (!loggedIn) {
      setError('Please log in to chat with the assistant.')
      return
    }

    setMessages((m) => [...m, { role: 'user', text }])
    setInput('')
    setSending(true)
    setError('')

    try {
      const res = await api.chat(text)
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          text: res.reply,
        },
      ])
    } catch (err) {
      setError(err.message)
    } finally {
      setSending(false)
    }
  }
    // Only render floating chat assistant for logged-in, confirmed non-admin
  // customers. isAdmin === null means "not checked yet" - stay hidden until
  // we know for sure, otherwise it flashes visible until the profile fetch
  // resolves and then disappears.
  if (!loggedIn || isAdmin !== false) {
    return null
  }
  return (
    <>
      {/* Floating Action Button (FAB) */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="user-chat-fab fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-gradient-to-r from-spot to-[#ff5c84] text-void flex items-center justify-center shadow-[0_6px_24px_rgba(255,61,110,0.4)] hover:scale-110 active:scale-95 transition-all duration-300 border border-white/10 outline-none cursor-pointer"
        title="Chat Booking Assistant"
        aria-label="Open Chat Assistant"
      >
        <span className="text-xl">{isOpen ? '✕' : '💬'}</span>
        {!isOpen && (
          <span className="absolute top-0 right-0 flex h-3.5 w-3.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-spot2 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-spot2"></span>
          </span>
        )}
      </button>

      {/* Floating Chat Drawer Container */}
      {isOpen && (
        <div
          ref={drawerRef}
          className="fixed bottom-24 right-6 z-50 w-96 h-[520px] max-w-[calc(100vw-48px)] glass-card bg-stage/95 rounded-2xl border border-white/[0.08] shadow-2xl p-4 flex flex-col justify-between animate-scale-in backdrop-blur-xl"
        >
          {/* Header */}
          <div className="border-b border-white/[0.04] pb-3 mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-go animate-pulse"></span>
              <div>
                <h3 className="text-xs font-mono tracking-wider text-spot uppercase font-bold">Concert Assistant</h3>
                <p className="text-[10px] text-haze">Find shows & coordinate bookings</p>
              </div>
            </div>
            <button 
              onClick={() => setIsOpen(false)}
              className="text-haze hover:text-paper text-xs font-mono px-2 py-1 rounded hover:bg-white/[0.05] transition"
              >
              ✕
            </button>
          </div>

          {/* Messages Container */}
          <div className="flex-grow overflow-y-auto space-y-3 pr-1 mb-3 scrollbar-none flex flex-col">
            <div className="flex-grow space-y-3">
              {messages.map((m, i) => {
                const isUser = m.role === 'user'
                return (
                  <div key={i} className={`flex gap-2.5 items-end ${isUser ? 'justify-end' : 'justify-start'} animate-scale-in`}>
                    {!isUser && (
                      <span className="w-6 h-6 rounded-full border border-spot2/20 bg-spot2/5 text-spot2 font-mono text-[10px] flex items-center justify-center flex-shrink-0">
                        🤖
                      </span>
                    )}
                    <div
                      className={`max-w-[80%] rounded-xl px-3 py-2 text-xs whitespace-pre-wrap leading-relaxed shadow-sm ${
                        isUser
                          ? 'bg-gradient-to-r from-spot to-[#ff5c84] text-void font-semibold rounded-br-sm'
                          : 'bg-stage2 border border-white/[0.04] text-paper rounded-bl-sm'
                      }`}
                    >
                      {linkify(m.text)}
                    </div>
                    {isUser && (
                      <span className="w-6 h-6 rounded-full border border-spot/20 bg-spot/5 text-spot font-mono text-[10px] flex items-center justify-center flex-shrink-0">
                        👤
                      </span>
                    )}
                  </div>
                )
              })}
              
              {sending && (
                <div className="flex gap-2.5 items-end justify-start animate-pulse">
                  <span className="w-6 h-6 rounded-full border border-spot2/20 bg-spot2/5 text-spot2 font-mono text-[10px] flex items-center justify-center flex-shrink-0">
                    🤖
                  </span>
                  <div className="bg-stage2 border border-white/[0.04] rounded-xl rounded-bl-sm px-3 py-2 text-xs text-haze">
                    Thinking…
                  </div>
                </div>
              )}
            </div>
            <div ref={bottomRef} />
          </div>

          {error && (
            <p className="text-[10px] text-spot font-mono mb-2 px-1">⚠️ Error: {error}</p>
          )}

          {/* Form Action */}
          <form onSubmit={handleSend} className="flex gap-1.5 border-t border-white/[0.04] pt-3 flex-shrink-0">
            <input
              className="field text-xs !py-2"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask anything (e.g. 'Show me concerts')..."
              disabled={sending}
            />
            <button type="submit" disabled={sending || !input.trim()} className="btn-spot !px-4 !py-2 text-xs font-bold disabled:opacity-40">
              Send
            </button>
          </form>
        </div>
      )}
    </>
  )
}
