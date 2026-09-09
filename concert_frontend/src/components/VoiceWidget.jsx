import { useEffect, useState, useRef, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import { Room, RoomEvent, Track } from 'livekit-client'
import { api } from '../lib/api'

const STATE = {
  IDLE: 'idle',
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  AGENT_SPEAKING: 'agent_speaking',
  ERROR: 'error',
}

export default function VoiceWidget() {
  const location = useLocation()
  const [loggedIn, setLoggedIn] = useState(api.isLoggedIn())
  const [isAdmin, setIsAdmin] = useState(false)

  const [isOpen, setIsOpen] = useState(false)
  const [state, setState] = useState(STATE.IDLE)
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
  }, [])

  useEffect(() => {
    return () => {
      roomRef.current?.disconnect()
    }
  }, [])

  // Keep loggedIn state in sync with route changes or storage events
  // (same pattern as ChatWidget) - otherwise this stays stuck at whatever
  // api.isLoggedIn() returned on first mount, even after the user logs in.
  useEffect(() => {
    const checkLogin = () => setLoggedIn(api.isLoggedIn())
    checkLogin()
    window.addEventListener('storage', checkLogin)
    return () => window.removeEventListener('storage', checkLogin)
  }, [location.pathname])

  // The backend already blocks admins from booking via voice
  // (see voice_routes.py get_voice_token 403), so hide the FAB for them
  // too instead of letting them open it and hit an error.
  useEffect(() => {
    if (!loggedIn) {
      setIsAdmin(false)
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

  if (!loggedIn || isAdmin) return null

  async function startCall() {
    setError('')
    setState(STATE.CONNECTING)

    try {
      const { livekit_url, token } = await api.getVoiceToken()

      const room = new Room({
        // Keep the connection lightweight.
        adaptiveStream: true,

        // These are the important microphone defaults.
        audioCaptureDefaults: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,

          // Browser support varies, so this is only a preference.
          voiceIsolation: true,

          // Mono is enough for speech and keeps processing simple.
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

          // Prevent the agent audio from being accidentally
          // muted by browser media policies.
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
      })

      await room.connect(livekit_url, token)

      // Explicitly enable browser/WebRTC audio processing.
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

  const isLive =
    state === STATE.CONNECTED ||
    state === STATE.AGENT_SPEAKING

  return (
    <>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="voice-fab fixed bottom-6 right-24 z-50 w-14 h-14 rounded-full bg-gradient-to-r from-spot2 to-[#6c5cff] text-void flex items-center justify-center shadow-[0_6px_24px_rgba(108,92,255,0.4)] hover:scale-110 active:scale-95 transition-all duration-300 border border-white/10 outline-none"
        title="Voice Booking Assistant"
      >
        <span className="text-xl">
          {isOpen ? '✕' : '🎙️'}
        </span>

        {isLive && (
          <span className="absolute top-0 right-0 flex h-3.5 w-3.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-emerald-400" />
          </span>
        )}
      </button>

      <audio
        ref={audioElRef}
        autoPlay
        playsInline
      />

      {isOpen && (
        <div
          ref={drawerRef}
          className="fixed bottom-24 right-24 z-50 w-80 max-w-[calc(100vw-48px)] glass-card bg-stage/95 rounded-2xl border border-white/[0.08] shadow-2xl p-5 flex flex-col items-center gap-4 animate-scale-in"
        >
          <div className="text-center">
            <h3 className="text-xs font-mono tracking-wider text-spot2 uppercase">
              Voice Booking Assistant
            </h3>

            <p className="text-[10px] text-haze mt-1">
              Talk to book tickets, hands-free
            </p>
          </div>

          <div
            className={`w-24 h-24 rounded-full border flex items-center justify-center transition-all duration-300 ${
              state === STATE.AGENT_SPEAKING
                ? 'border-spot2 bg-spot2/10 scale-110 animate-pulse'
                : isLive
                ? 'border-emerald-400 bg-emerald-400/10'
                : 'border-white/[0.08] bg-stage2'
            }`}
          >
            <span className="text-3xl">
              {state === STATE.CONNECTING
                ? '⏳'
                : isLive
                ? '🎙️'
                : '🔇'}
            </span>
          </div>

          <p className="text-[11px] text-haze text-center min-h-[1.5em]">
            {state === STATE.IDLE &&
              'Tap start and ask about any event.'}

            {state === STATE.CONNECTING &&
              'Connecting…'}

            {state === STATE.CONNECTED &&
              'Listening — go ahead, ask away.'}

            {state === STATE.AGENT_SPEAKING &&
              'Agent is speaking…'}

            {state === STATE.ERROR &&
              'Something went wrong.'}
          </p>

          {error && (
            <p className="text-[10px] text-spot font-mono px-1 text-center">
              ⚠️ {error}
            </p>
          )}

          {!isLive && state !== STATE.CONNECTING ? (
            <button
              onClick={startCall}
              className="btn-spot !px-6 !py-2 text-xs font-bold w-full"
            >
              Start Voice Session
            </button>
          ) : (
            <button
              onClick={disconnect}
              disabled={state === STATE.CONNECTING}
              className="!px-6 !py-2 text-xs font-bold w-full rounded-lg border border-spot/30 text-spot hover:bg-spot/10 transition disabled:opacity-40"
            >
              End Call
            </button>
          )}
        </div>
      )}
    </>
  )
}