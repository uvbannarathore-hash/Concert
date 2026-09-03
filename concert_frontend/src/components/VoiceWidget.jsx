import { useEffect, useState, useRef, useCallback } from 'react'
import { api } from '../lib/api'

// NOTE: livekit-client is no longer used here — Dograh's embed script
// (loaded once in index.html) handles the WebRTC connection, mic capture,
// and agent audio playback internally via window.DograhWidget. This
// component just drives that API and keeps the exact same UI/UX as before.

const STATE = {
  IDLE: 'idle',
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  AGENT_SPEAKING: 'agent_speaking',
  ERROR: 'error',
}

// Dograh's onStatusChange only reports: idle | connecting | connected | failed.
// There is no dedicated "agent is currently speaking" event exposed by the
// widget API, so unlike the old LiveKit ActiveSpeakersChanged-driven
// AGENT_SPEAKING state, this widget will show CONNECTED ("Listening...")
// for the whole duration of the call rather than switching to
// AGENT_SPEAKING while the agent talks. The STATE.AGENT_SPEAKING constant
// is kept only so the JSX below still compiles/looks the same; it is never
// set by this version. Remove it if you don't need the placeholder.

export default function VoiceWidget() {
  const loggedIn = api.isLoggedIn()

  const [isOpen, setIsOpen] = useState(false)
  const [state, setState] = useState(STATE.IDLE)
  const [error, setError] = useState('')
  const [widgetReady, setWidgetReady] = useState(false)

  const drawerRef = useRef(null)

  // Poll for window.DograhWidget since the embed <script> in index.html
  // loads asynchronously and may not exist yet on first render.
  useEffect(() => {
    let retries = 0
    let cancelled = false

    function tryInit() {
      if (cancelled) return

      if (window.DograhWidget) {
        setWidgetReady(true)

        window.DograhWidget.onStatusChange((status) => {
          // status: 'idle' | 'connecting' | 'connected' | 'failed'
          if (status === 'connecting') setState(STATE.CONNECTING)
          else if (status === 'connected') setState(STATE.CONNECTED)
          else if (status === 'failed') setState(STATE.ERROR)
          else setState(STATE.IDLE)
        })

        window.DograhWidget.onError((err) => {
          console.error('Voice connection error:', err)
          setError(err?.message || 'Could not start the voice assistant')
          setState(STATE.ERROR)
        })

        window.DograhWidget.onCallEnd(() => {
          setState(STATE.IDLE)
        })
      } else if (retries++ < 50) {
        setTimeout(tryInit, 100)
      } else {
        console.error('Dograh widget script did not load in time.')
      }
    }

    tryInit()

    return () => {
      cancelled = true
    }
  }, [])

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

  if (!loggedIn) return null

  const startCall = useCallback(() => {
    if (!widgetReady || !window.DograhWidget) {
      setError('Voice assistant is still loading, try again in a moment.')
      return
    }

    setError('')
    setState(STATE.CONNECTING)

    // Optionally pass page/user context to the agent, e.g. so prompts can
    // reference {{initial_context.customer_name}}. Uncomment and adapt:
    // window.DograhWidget.setContext({
    //   customer_name: api.getCurrentUser?.()?.name,
    // })

    // Must run inside this click handler (user gesture) or the browser
    // will refuse microphone access.
    window.DograhWidget.start()
  }, [widgetReady])

  const disconnect = useCallback(() => {
    if (window.DograhWidget) {
      window.DograhWidget.end()
    }
    setState(STATE.IDLE)
  }, [])

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