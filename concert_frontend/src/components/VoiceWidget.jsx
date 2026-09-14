import { useEffect, useState, useRef, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import { Room, RoomEvent, Track } from 'livekit-client'
import { api } from '../lib/api'
import { Mic, MicOff, Volume2, VolumeX, Loader2, Square, X, AlertCircle } from 'lucide-react'

const STATE = {
  IDLE: 'idle',
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  AGENT_SPEAKING: 'agent_speaking',
  ERROR: 'error',
}

const SAMPLE_PROMPTS = [
  "Find concerts in New York",
  "Book 2 tickets for Coldplay",
  "Show my upcoming bookings",
]

export default function VoiceWidget() {
  const location = useLocation()
  const [loggedIn, setLoggedIn] = useState(api.isLoggedIn())
  const [isAdmin, setIsAdmin] = useState(null) // null = "not checked yet"

  const [isOpen, setIsOpen] = useState(false)
  const [state, setState] = useState(STATE.IDLE)
  const [isMuted, setIsMuted] = useState(false)
  const [error, setError] = useState('')

  const roomRef = useRef(null)
  const audioElRef = useRef(null)
  const drawerRef = useRef(null)

  const disconnect = useCallback(async () => {
    const room = roomRef.current

    if (room) {
      try {
        await room.localParticipant.setMicrophoneEnabled(false)
      } catch (_) {}

      await room.disconnect()
      roomRef.current = null
    }

    setState(STATE.IDLE)
    setIsMuted(false)
  }, [])

  useEffect(() => {
    return () => {
      roomRef.current?.disconnect()
    }
  }, [])

  // Keep loggedIn state in sync with route changes or storage events
  useEffect(() => {
    const checkLogin = () => setLoggedIn(api.isLoggedIn())
    checkLogin()
    window.addEventListener('storage', checkLogin)
    return () => window.removeEventListener('storage', checkLogin)
  }, [location.pathname])

  // Admins get their own workflow — hide user voice widget for admins
  useEffect(() => {
    if (!loggedIn) {
      setIsAdmin(null)
      return
    }
    api.myProfile().then((p) => setIsAdmin(!!p?.is_admin)).catch(() => {})
  }, [loggedIn])

  useEffect(() => {
    function handleClickOutside(event) {
      if (
        drawerRef.current &&
        !drawerRef.current.contains(event.target) &&
        !event.target.closest('.voice-fab')
      ) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  if (!loggedIn || isAdmin !== false) return null

  async function startCall() {
    setError('')
    setState(STATE.CONNECTING)
    setIsMuted(false)

    try {
      const { livekit_url, token } = await api.getVoiceToken()

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

        setState((prev) => {
          if (prev === STATE.ERROR) return prev

          return agentSpeaking
            ? STATE.AGENT_SPEAKING
            : STATE.CONNECTED
        })
      })

      room.on(RoomEvent.Disconnected, () => {
        roomRef.current = null
        setState(STATE.IDLE)
        setIsMuted(false)
      })

      await room.connect(livekit_url, token)

      await room.localParticipant.setMicrophoneEnabled(true, {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        voiceIsolation: true,
        channelCount: 1,
      })

      setState(STATE.CONNECTED)
    } catch (err) {
      console.error('Voice connection error:', err)
      setError(
        err?.message || 'Could not start the voice assistant'
      )
      setState(STATE.ERROR)
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

  const isLive =
    state === STATE.CONNECTED ||
    state === STATE.AGENT_SPEAKING

  return (
    <>
      {/* Floating Action Button (FAB) for Voice Assistant */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="voice-fab fixed bottom-6 right-24 z-50 w-14 h-14 rounded-full bg-gradient-to-r from-spot to-[#ff5c84] text-void flex items-center justify-center shadow-[0_6px_24px_rgba(255,61,110,0.4)] hover:scale-110 active:scale-95 transition-all duration-300 border border-white/10 outline-none cursor-pointer"
        title="Voice Booking Assistant"
        aria-label="Open Voice Assistant"
      >
        {isOpen ? (
          <X className="w-6 h-6 text-void" />
        ) : (
          <Mic className="w-6 h-6 text-void" />
        )}

        {!isOpen && (
          <span className="absolute top-0 right-0 flex h-3.5 w-3.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-spot2 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-spot2"></span>
          </span>
        )}
      </button>

      <audio ref={audioElRef} autoPlay playsInline />

      {/* Floating Voice Drawer Container */}
      {isOpen && (
        <div
          ref={drawerRef}
          className="fixed bottom-24 right-24 z-50 w-96 max-w-[calc(100vw-48px)] glass-card bg-stage/95 rounded-2xl border border-white/[0.08] shadow-2xl p-4 flex flex-col items-center gap-4 animate-scale-in backdrop-blur-xl"
        >
          {/* Top Header */}
          <div className="w-full border-b border-white/[0.04] pb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`w-2.5 h-2.5 rounded-full ${
                isLive ? 'bg-emerald-400 animate-pulse' : 'bg-go animate-pulse'
              }`} />
              <div>
                <h3 className="text-xs font-mono tracking-wider text-spot2 uppercase font-bold">Voice Assistant</h3>
                <p className="text-[10px] text-haze">Hands-free ticket booking & assistance</p>
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

          {/* Central Audio Visualizer Orb */}
          <div className="relative flex items-center justify-center my-1">
            {/* Outer Pulsing Wave Rings when Active */}
            {state === STATE.AGENT_SPEAKING && (
              <>
                <div className="absolute w-32 h-32 rounded-full border border-spot2/30 animate-ping" />
                <div className="absolute w-28 h-28 rounded-full border border-[#8b5cf6]/40 animate-pulse" />
              </>
            )}

            {isLive && state !== STATE.AGENT_SPEAKING && (
              <div className="absolute w-28 h-28 rounded-full border border-emerald-400/20 animate-pulse" />
            )}

            {/* Core Visualizer Sphere */}
            <div
              className={`relative z-10 w-24 h-24 rounded-full border flex flex-col items-center justify-center transition-all duration-500 shadow-xl ${
                state === STATE.AGENT_SPEAKING
                  ? 'border-spot2 bg-gradient-to-br from-spot2/20 to-[#6c5cff]/30 scale-105 shadow-[0_0_25px_rgba(255,200,87,0.4)]'
                  : isLive
                  ? isMuted
                    ? 'border-spot/40 bg-spot/10 shadow-[0_0_15px_rgba(255,61,110,0.2)]'
                    : 'border-emerald-400 bg-emerald-500/10 shadow-[0_0_20px_rgba(67,217,163,0.3)]'
                  : state === STATE.CONNECTING
                  ? 'border-spot2/50 bg-spot2/10 animate-pulse'
                  : 'border-white/[0.1] bg-stage2 hover:border-white/20'
              }`}
            >
              <span className="transition-transform duration-300">
                {state === STATE.CONNECTING ? (
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
                    state === STATE.AGENT_SPEAKING ? 'h-3 animate-bounce' : 'h-1.5'
                  }`} />
                  <span className={`w-0.5 rounded-full bg-spot2 transition-all duration-300 ${
                    state === STATE.AGENT_SPEAKING ? 'h-4 animate-bounce delay-75' : 'h-2'
                  }`} />
                  <span className={`w-0.5 rounded-full bg-emerald-400 transition-all duration-300 ${
                    state === STATE.AGENT_SPEAKING ? 'h-3 animate-bounce delay-150' : 'h-1.5'
                  }`} />
                </div>
              )}
            </div>
          </div>

          {/* Status Message Card */}
          <div className="w-full bg-stage2/80 border border-white/[0.04] rounded-xl p-3 text-center flex flex-col items-center gap-1.5">
            <span className={`text-[10px] font-mono font-semibold uppercase px-2 py-0.5 rounded-full border ${
              state === STATE.AGENT_SPEAKING
                ? 'bg-spot2/10 text-spot2 border-spot2/30'
                : isLive
                ? isMuted
                  ? 'bg-spot/10 text-spot border-spot/30'
                  : 'bg-emerald-400/10 text-emerald-400 border-emerald-400/30'
                : state === STATE.CONNECTING
                ? 'bg-spot2/10 text-spot2 border-spot2/30'
                : state === STATE.ERROR
                ? 'bg-spot/10 text-spot border-spot/30'
                : 'bg-white/[0.05] text-haze border-white/[0.08]'
            }`}>
              {state === STATE.IDLE && 'Ready to Connect'}
              {state === STATE.CONNECTING && 'Connecting...'}
              {state === STATE.CONNECTED && (isMuted ? 'Microphone Muted' : 'Listening...')}
              {state === STATE.AGENT_SPEAKING && 'Agent Speaking'}
              {state === STATE.ERROR && 'Connection Failed'}
            </span>

            <p className="text-xs text-paper font-medium leading-snug px-1">
              {state === STATE.IDLE && 'Tap start to talk with your AI booking concierge.'}
              {state === STATE.CONNECTING && 'Establishing live WebRTC session...'}
              {state === STATE.CONNECTED && (isMuted ? 'Unmute your mic to continue talking.' : 'Go ahead, ask about concerts, seats, or bookings.')}
              {state === STATE.AGENT_SPEAKING && 'The AI assistant is responding to you...'}
              {state === STATE.ERROR && (error || 'Something went wrong. Please try again.')}
            </p>
          </div>

          {/* Prompt Suggestions when Idle */}
          {state === STATE.IDLE && (
            <div className="w-full space-y-1.5">
              <p className="text-[10px] font-mono text-haze uppercase tracking-wider text-center">
                Try asking:
              </p>
              <div className="flex flex-col gap-1">
                {SAMPLE_PROMPTS.map((prompt, idx) => (
                  <div
                    key={idx}
                    className="text-[11px] text-haze bg-white/[0.02] border border-white/[0.04] rounded-lg px-2.5 py-1 text-center font-mono"
                  >
                    "{prompt}"
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="w-full flex gap-2 pt-1">
            {!isLive && state !== STATE.CONNECTING ? (
              <button
                onClick={startCall}
                className="btn-spot2 w-full !py-2.5 text-xs font-bold flex items-center justify-center gap-2"
              >
                <Mic className="w-4 h-4" />
                <span>Start Voice Session</span>
              </button>
            ) : (
              <>
                {/* Mute Button */}
                <button
                  onClick={toggleMute}
                  disabled={state === STATE.CONNECTING}
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

                {/* End Call Button */}
                <button
                  onClick={disconnect}
                  disabled={state === STATE.CONNECTING}
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
    </>
  )
}
