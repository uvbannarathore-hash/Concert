import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { createClient } from '@supabase/supabase-js'

// Realtime uses the publishable key only - never the secret key in frontend code.
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

export default function ChatPage() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: "Hey! I'm your booking assistant. Ask me to find concerts, check seat availability, view your tickets, or handle reservation changes.",
    },
  ])

  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  // Listen for booking confirmations in real time (fires when the
  // Razorpay webhook -> n8n -> Supabase update lands on this user's row).
  useEffect(() => {
    const userId = localStorage.getItem('user_id')
    if (!userId) return

    const channel = supabase
      .channel(`bookings-user-${userId}`)
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
          }
        }
      )
      .subscribe()

    return () => {
      supabase.removeChannel(channel)
    }
  }, [])

  async function handleSend(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || sending) return

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

  return (
    <div className="max-w-3xl mx-auto px-6 py-8 flex flex-col h-[calc(100vh-64px)] animate-fade-in-up">
      
      {/* Page Header */}
      <div className="mb-6 flex-shrink-0">
        <p className="eyebrow mb-1">CONVERSATIONAL AI</p>
        <h1 className="font-display text-4xl tracking-wide uppercase text-paper">
          THE ASSISTANT
        </h1>
        <p className="text-xs text-haze mt-1">
          Connected to local database & ticketing systems
        </p>
      </div>

      {/* Chat Messages Stream */}
      <div className="flex-1 overflow-y-auto border border-white/[0.04] bg-stage2/10 rounded-2xl p-5 space-y-4 mb-4 scrollbar-none shadow-inner flex flex-col">
        <div className="flex-grow space-y-4">
          {messages.map((m, i) => {
            const isUser = m.role === 'user'
            return (
              <div
                key={i}
                className={`flex gap-3 items-end ${isUser ? 'justify-end' : 'justify-start'} animate-scale-in`}
              >
                {/* Assistant avatar indicator */}
                {!isUser && (
                  <span className="w-8 h-8 rounded-full border border-spot2/20 bg-spot2/5 text-spot2 font-mono text-xs flex items-center justify-center flex-shrink-0">
                    🤖
                  </span>
                )}
                
                <div
                  className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap leading-relaxed shadow-md ${
                    isUser
                      ? 'bg-gradient-to-r from-spot to-[#ff5c84] text-void font-semibold rounded-br-sm'
                      : 'bg-stage border border-white/[0.04] text-paper rounded-bl-sm'
                  }`}
                >
                  {linkify(m.text)}
                </div>

                {/* User avatar indicator */}
                {isUser && (
                  <span className="w-8 h-8 rounded-full border border-spot/20 bg-spot/5 text-spot font-mono text-xs flex items-center justify-center flex-shrink-0">
                    👤
                  </span>
                )}
              </div>
            )
          })}

          {/* Animative Typing Indicator */}
          {sending && (
            <div className="flex gap-3 items-end justify-start animate-pulse">
              <span className="w-8 h-8 rounded-full border border-spot2/20 bg-spot2/5 text-spot2 font-mono text-xs flex items-center justify-center flex-shrink-0">
                🤖
              </span>
              <div className="bg-stage border border-white/[0.04] rounded-2xl rounded-bl-sm px-5 py-4 flex items-center gap-1.5 shadow-md">
                <span className="w-2 h-2 rounded-full bg-spot2 animate-bounce" style={{ animationDelay: '0ms' }}></span>
                <span className="w-2 h-2 rounded-full bg-spot2 animate-bounce" style={{ animationDelay: '150ms' }}></span>
                <span className="w-2 h-2 rounded-full bg-spot2 animate-bounce" style={{ animationDelay: '300ms' }}></span>
              </div>
            </div>
          )}
        </div>
        <div ref={bottomRef} />
      </div>

      {/* Telegram Fallback helper */}
      <div className="flex-shrink-0 border border-white/[0.04] bg-stage/10 rounded-xl p-3 text-center text-xs text-haze mb-4 flex items-center justify-center gap-2">
        <span>💬 Prefer Telegram? You can also message our agent on external chatrooms:</span>
        <a
          href="https://t.me/Apra_shaktibot"
          target="_blank"
          rel="noopener noreferrer"
          className="text-spot2 font-bold hover:text-spot transition underline underline-offset-4 flex items-center gap-0.5"
        >
          Telegram assistant ↗
        </a>
      </div>

      {/* Error alert */}
      {error && (
        <p className="text-spot text-xs font-mono mb-2 px-1">
          ⚠️ Connection failure: {error}
        </p>
      )}

      {/* Input Field wrapper */}
      <form onSubmit={handleSend} className="flex gap-2.5 flex-shrink-0">
        <input
          className="field"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type your booking query (e.g. Find movies in Mumbai, Show my bookings...)"
          disabled={sending}
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className="btn-spot !px-6 flex items-center gap-1 text-sm font-bold disabled:opacity-40"
        >
          <span>Send</span>
          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M14 5l7 7m0 0l-7 7m7-7H3"></path>
          </svg>
        </button>
      </form>
    </div>
  )
}