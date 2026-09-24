import { useEffect, useState, useRef, useCallback } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api, getSessionId } from '../lib/api'
import { createClient } from '@supabase/supabase-js'
import { MessageSquare, Sparkles, User, X, Send, AlertCircle, Mic, MicOff, Volume2, VolumeX, Loader2, Square } from 'lucide-react'
import { Room, RoomEvent, Track } from 'livekit-client'

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

const VOICE_STATE = {
  IDLE: 'idle',
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  AGENT_SPEAKING: 'agent_speaking',
  ERROR: 'error',
}

export default function ChatWidget() {
  const location = useLocation()
  const [loggedIn, setLoggedIn] = useState(api.isLoggedIn())
  const [isAdmin, setIsAdmin] = useState(null) // null = "not checked yet"
  const [isOpen, setIsOpen] = useState(false)
  const [mode, setMode] = useState('text') // 'text' or 'voice'

  const [messages, setMessages] = useState(() => {
    const saved = sessionStorage.getItem('chat_widget_messages')
    if (saved) {
      try { return JSON.parse(saved) } catch (e) {}
    }
    return [
      {
        role: 'assistant',
        text: "Hey! I'm your AI booking assistant. Ask me to find concerts, check seat availability, view your tickets, or handle reservation questions!",
      },
    ]
  })

  useEffect(() => {
    sessionStorage.setItem('chat_widget_messages', JSON.stringify(messages))
  }, [messages])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')

  const [voiceState, setVoiceState] = useState(VOICE_STATE.IDLE)
  const [isMuted, setIsMuted] = useState(false)
  
  const bottomRef = useRef(null)
  const drawerRef = useRef(null)
  const roomRef = useRef(null)
  const audioElRef = useRef(null)

  // Keep loggedIn state in sync with route changes or storage events
  useEffect(() => {
    const checkLogin = () => setLoggedIn(api.isLoggedIn())
    checkLogin()
    window.addEventListener('storage', checkLogin)
    return () => window.removeEventListener('storage', checkLogin)
  }, [location.pathname])

  useEffect(() => {
    if (!loggedIn) {
      setIsAdmin(null)
      return
    }
    api.myProfile().then((p) => setIsAdmin(!!p?.is_admin)).catch(() => {})
  }, [loggedIn])

  // Scroll to bottom when messages update
  useEffect(() => {
    if (isOpen && mode === 'text') {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, sending, isOpen, mode])

  // Cleanup LiveKit on unmount
  useEffect(() => {
    return () => {
      roomRef.current?.disconnect()
    }
  }, [])

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
                text: `Your booking is confirmed!\n\nBooking ID: ${b.booking_id}\nCategory: ${b.category}\nSeats: ${b.seats_booked}\n\nSee you at the show!`,
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

  const disconnectVoice = useCallback(async () => {
    const room = roomRef.current

    if (room) {
      try {
        await room.localParticipant.setMicrophoneEnabled(false)
      } catch (_) {}

      await room.disconnect()
      roomRef.current = null
    }

    setVoiceState(VOICE_STATE.IDLE)
    setIsMuted(false)
    setMode('text') // return to text mode automatically
  }, [])

  async function startVoiceCall() {
    setError('')
    setVoiceState(VOICE_STATE.CONNECTING)
    setIsMuted(false)
    setMode('voice')

    try {
      // Pass the shared session ID so text & voice share the same history
      const sessionId = getSessionId()
      const { livekit_url, token } = await api.getVoiceToken(sessionId)

      const room = new Room({
        adaptiveStream: true,
        audioCaptureDefaults: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          voiceIsolation: true,
          channelCount: 1,
        },
        disconnectOnPageLeave: true,
      })

      roomRef.current = room

      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === Track.Kind.Audio) {
          const audioElement = track.attach()
          audioElement.autoplay = true
          audioElement.setAttribute('playsinline', '')
          audioElRef.current = audioElement
          audioElement.volume = 1.0
        }
      })

      room.on(RoomEvent.TrackUnsubscribed, (track) => {
        if (track.kind === Track.Kind.Audio) {
          track.detach()
        }
      })

      room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
        const agentSpeaking = speakers.some(
          (participant) => !participant.isLocal
        )

        setVoiceState((prev) => {
          if (prev === VOICE_STATE.ERROR) return prev
          return agentSpeaking ? VOICE_STATE.AGENT_SPEAKING : VOICE_STATE.CONNECTED
        })
      })

      room.on(RoomEvent.Disconnected, () => {
        roomRef.current = null
        setVoiceState(VOICE_STATE.IDLE)
        setIsMuted(false)
        setMode('text')
      })

      await room.connect(livekit_url, token)

      await room.localParticipant.setMicrophoneEnabled(true, {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        voiceIsolation: true,
        channelCount: 1,
      })

      setVoiceState(VOICE_STATE.CONNECTED)
    } catch (err) {
      console.error('Voice connection error:', err)
      setError(
        err?.message || 'Could not start the voice assistant'
      )
      setVoiceState(VOICE_STATE.ERROR)
      roomRef.current = null
    }
  }

  const toggleMute = async () => {
    if (!roomRef.current) return
    try {
      const nextMute = !isMuted
      await roomRef.current.localParticipant.setMicrophoneEnabled(!nextMute)
      setIsMuted(nextMute)
    } catch (e) {
      console.error("Failed to toggle mute:", e)
    }
  }

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

  if (!loggedIn || isAdmin !== false) {
    return null
  }

  const isLive =
    voiceState === VOICE_STATE.CONNECTED ||
    voiceState === VOICE_STATE.AGENT_SPEAKING

  return (
    <>
      {/* Floating Action Button (FAB) */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="user-chat-fab fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-gradient-to-r from-spot to-[#ff5c84] text-void flex items-center justify-center shadow-[0_6px_24px_rgba(255,61,110,0.4)] hover:scale-110 active:scale-95 transition-all duration-300 border border-white/10 outline-none cursor-pointer"
        title="Chat Booking Assistant"
        aria-label="Open Chat Assistant"
      >
        {isOpen ? (
          <X className="w-6 h-6 text-void" />
        ) : (
          <MessageSquare className="w-6 h-6 text-void fill-current" />
        )}

        {!isOpen && (
          <span className="absolute top-0 right-0 flex h-3.5 w-3.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-spot2 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-spot2"></span>
          </span>
        )}
      </button>

      {/* Hidden audio element for LiveKit */}
      <audio ref={audioElRef} autoPlay playsInline />

      {/* Floating Chat Drawer Container */}
      {isOpen && (
        <div
          ref={drawerRef}
          className="fixed bottom-24 right-6 z-50 w-96 h-[520px] max-h-[calc(100vh-180px)] max-w-[calc(100vw-48px)] glass-card bg-stage/95 rounded-2xl border border-white/[0.08] shadow-2xl p-4 flex flex-col justify-between animate-scale-in backdrop-blur-xl"
        >
          {/* Header */}
          <div className="border-b border-white/[0.04] pb-3 mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`w-2.5 h-2.5 rounded-full ${isLive ? 'bg-emerald-400' : 'bg-go'} animate-pulse`}></span>
              <div>
                <h3 className="text-xs font-mono tracking-wider text-spot uppercase font-bold">LiveWire AI</h3>
                <p className="text-[10px] text-haze">Booking Assistant</p>
              </div>
            </div>
            <button 
              onClick={() => setIsOpen(false)}
              className="text-haze hover:text-paper p-1 rounded hover:bg-white/[0.05] transition"
              title="Close"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {mode === 'text' ? (
            <>
              {/* Text Mode Messages Container */}
              <div className="flex-grow overflow-y-auto space-y-3 pr-1 mb-3 scrollbar-none flex flex-col">
                <div className="flex-grow space-y-3">
                  {messages.map((m, i) => {
                    const isUser = m.role === 'user'
                    return (
                      <div key={i} className={`flex gap-2.5 items-end ${isUser ? 'justify-end' : 'justify-start'} animate-scale-in`}>
                        {!isUser && (
                          <span className="w-6 h-6 rounded-full border border-spot2/20 bg-spot2/10 text-spot2 flex items-center justify-center flex-shrink-0">
                            <Sparkles className="w-3.5 h-3.5 text-spot2" />
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
                          <span className="w-6 h-6 rounded-full border border-spot/20 bg-spot/10 text-spot flex items-center justify-center flex-shrink-0">
                            <User className="w-3.5 h-3.5 text-spot" />
                          </span>
                        )}
                      </div>
                    )
                  })}
                  
                  {sending && (
                    <div className="flex gap-2.5 items-end justify-start animate-pulse">
                      <span className="w-6 h-6 rounded-full border border-spot2/20 bg-spot2/10 text-spot2 flex items-center justify-center flex-shrink-0">
                        <Sparkles className="w-3.5 h-3.5 text-spot2" />
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
                <div className="flex items-center gap-1.5 text-[10px] text-spot font-mono mb-2 px-1">
                  <AlertCircle className="w-3.5 h-3.5" />
                  <span>Error: {error}</span>
                </div>
              )}

              {/* Text Mode Form Action */}
              <form onSubmit={handleSend} className="flex gap-1.5 border-t border-white/[0.04] pt-3 flex-shrink-0">
                <input
                  className="field text-xs !py-2"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask anything..."
                  disabled={sending}
                />
                <button type="submit" disabled={sending || !input.trim()} className="btn-spot !px-3.5 !py-2 text-xs font-bold disabled:opacity-40 flex items-center gap-1">
                  <Send className="w-3.5 h-3.5" />
                </button>
                <button 
                  type="button" 
                  onClick={startVoiceCall} 
                  className="btn-spot2 !px-3.5 !py-2 text-xs font-bold flex items-center gap-1"
                  title="Switch to Voice"
                >
                  <Mic className="w-3.5 h-3.5" />
                </button>
              </form>
            </>
          ) : (
            /* Voice Mode View */
            <div className="flex-grow flex flex-col justify-between items-center py-4">
              
              {/* Central Audio Visualizer Orb */}
              <div className="relative flex items-center justify-center my-6 flex-grow">
                {/* Outer Pulsing Wave Rings when Active */}
                {voiceState === VOICE_STATE.AGENT_SPEAKING && (
                  <>
                    <div className="absolute w-32 h-32 rounded-full border border-spot2/30 animate-ping" />
                    <div className="absolute w-28 h-28 rounded-full border border-[#8b5cf6]/40 animate-pulse" />
                  </>
                )}

                {isLive && voiceState !== VOICE_STATE.AGENT_SPEAKING && (
                  <div className="absolute w-28 h-28 rounded-full border border-emerald-400/20 animate-pulse" />
                )}

                {/* Core Visualizer Sphere */}
                <div
                  className={`relative z-10 w-24 h-24 rounded-full border flex flex-col items-center justify-center transition-all duration-500 shadow-xl ${
                    voiceState === VOICE_STATE.AGENT_SPEAKING
                      ? 'border-spot2 bg-gradient-to-br from-spot2/20 to-[#6c5cff]/30 scale-105 shadow-[0_0_25px_rgba(255,200,87,0.4)]'
                      : isLive
                      ? isMuted
                        ? 'border-spot/40 bg-spot/10 shadow-[0_0_15px_rgba(255,61,110,0.2)]'
                        : 'border-emerald-400 bg-emerald-500/10 shadow-[0_0_20px_rgba(67,217,163,0.3)]'
                      : voiceState === VOICE_STATE.CONNECTING
                      ? 'border-spot2/50 bg-spot2/10 animate-pulse'
                      : 'border-white/[0.1] bg-stage2 hover:border-white/20'
                  }`}
                >
                  <span className="transition-transform duration-300">
                    {voiceState === VOICE_STATE.CONNECTING ? (
                      <Loader2 className="w-8 h-8 text-spot2 animate-spin" />
                    ) : isLive ? (
                      isMuted ? <MicOff className="w-8 h-8 text-spot" /> : <Mic className="w-8 h-8 text-emerald-400" />
                    ) : (
                      <Mic className="w-8 h-8 text-paper/70" />
                    )}
                  </span>

                  {/* Dynamic Sound Equalizer Waveform Lines */}
                  {isLive && !isMuted && (
                    <div className="flex gap-1 items-center mt-2 h-3">
                      <span className={`w-0.5 rounded-full bg-emerald-400 transition-all duration-300 ${
                        voiceState === VOICE_STATE.AGENT_SPEAKING ? 'h-3 animate-bounce' : 'h-1.5'
                      }`} />
                      <span className={`w-0.5 rounded-full bg-spot2 transition-all duration-300 ${
                        voiceState === VOICE_STATE.AGENT_SPEAKING ? 'h-4 animate-bounce delay-75' : 'h-2'
                      }`} />
                      <span className={`w-0.5 rounded-full bg-emerald-400 transition-all duration-300 ${
                        voiceState === VOICE_STATE.AGENT_SPEAKING ? 'h-3 animate-bounce delay-150' : 'h-1.5'
                      }`} />
                    </div>
                  )}
                </div>
              </div>

              {/* Status Message Card */}
              <div className="w-full bg-stage2/80 border border-white/[0.04] rounded-xl p-3 text-center flex flex-col items-center gap-1.5 mb-6">
                <span className={`text-[10px] font-mono font-semibold uppercase px-2 py-0.5 rounded-full border ${
                  voiceState === VOICE_STATE.AGENT_SPEAKING
                    ? 'bg-spot2/10 text-spot2 border-spot2/30'
                    : isLive
                    ? isMuted
                      ? 'bg-spot/10 text-spot border-spot/30'
                      : 'bg-emerald-400/10 text-emerald-400 border-emerald-400/30'
                    : voiceState === VOICE_STATE.CONNECTING
                    ? 'bg-spot2/10 text-spot2 border-spot2/30'
                    : voiceState === VOICE_STATE.ERROR
                    ? 'bg-spot/10 text-spot border-spot/30'
                    : 'bg-white/[0.05] text-haze border-white/[0.08]'
                }`}>
                  {voiceState === VOICE_STATE.IDLE && 'Ready to Connect'}
                  {voiceState === VOICE_STATE.CONNECTING && 'Connecting...'}
                  {voiceState === VOICE_STATE.CONNECTED && (isMuted ? 'Microphone Muted' : 'Listening...')}
                  {voiceState === VOICE_STATE.AGENT_SPEAKING && 'Agent Speaking'}
                  {voiceState === VOICE_STATE.ERROR && 'Connection Failed'}
                </span>

                <p className="text-xs text-paper font-medium leading-snug px-1">
                  {voiceState === VOICE_STATE.IDLE && 'Tap start to talk with your AI booking concierge.'}
                  {voiceState === VOICE_STATE.CONNECTING && 'Establishing live WebRTC session...'}
                  {voiceState === VOICE_STATE.CONNECTED && (isMuted ? 'Unmute your mic to continue talking.' : 'Go ahead, ask about concerts, seats, or bookings.')}
                  {voiceState === VOICE_STATE.AGENT_SPEAKING && 'The AI assistant is responding to you...'}
                  {voiceState === VOICE_STATE.ERROR && (error || 'Something went wrong. Please try again.')}
                </p>
              </div>

              {/* Voice Actions */}
              <div className="w-full flex gap-2">
                {!isLive && voiceState !== VOICE_STATE.CONNECTING ? (
                  <>
                    <button
                      onClick={() => setMode('text')}
                      className="flex-1 !py-2.5 text-xs font-bold rounded-xl border border-white/[0.1] hover:bg-white/[0.05] transition flex items-center justify-center gap-2 text-paper"
                    >
                      Return to Text
                    </button>
                    <button
                      onClick={startVoiceCall}
                      className="btn-spot2 flex-1 !py-2.5 text-xs font-bold flex items-center justify-center gap-2"
                    >
                      <Mic className="w-4 h-4" />
                      <span>Start Voice</span>
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={toggleMute}
                      disabled={voiceState === VOICE_STATE.CONNECTING}
                      className={`flex-1 !py-2 text-xs font-bold rounded-xl border transition flex items-center justify-center gap-1.5 ${
                        isMuted
                          ? 'bg-spot/20 border-spot/40 text-spot hover:bg-spot/30'
                          : 'bg-white/[0.05] border-white/[0.1] text-paper hover:bg-white/[0.1]'
                      }`}
                    >
                      {isMuted ? (
                        <>
                          <Volume2 className="w-3.5 h-3.5" />
                          <span>Unmute</span>
                        </>
                      ) : (
                        <>
                          <VolumeX className="w-3.5 h-3.5" />
                          <span>Mute</span>
                        </>
                      )}
                    </button>

                    <button
                      onClick={disconnectVoice}
                      disabled={voiceState === VOICE_STATE.CONNECTING}
                      className="flex-1 !py-2 text-xs font-bold rounded-xl border border-spot/40 text-spot hover:bg-spot/10 transition disabled:opacity-40 flex items-center justify-center gap-1.5"
                    >
                      <Square className="w-3.5 h-3.5 fill-current" />
                      <span>End Session</span>
                    </button>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </>
  )
}
