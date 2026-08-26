import { useState, useRef } from 'react'
import { api } from '../lib/api'

export default function VoiceAssistantModal({ isOpen, onClose }) {
  const [recording, setRecording] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [botResponse, setBotResponse] = useState('')
  const [extractedLink, setExtractedLink] = useState('')
  const mediaRecorderRef = useRef(null)
  const audioChunksRef = useRef([])

  if (!isOpen) return null

  function getStoredToken() {
    return (
      localStorage.getItem('access_token') ||
      localStorage.getItem('token') ||
      localStorage.getItem('admin_token') ||
      ''
    )
  }

  // Regex to detect URLs in the text
  function formatReplyWithLinks(text) {
    if (!text) return null
    const urlRegex = /(https?:\/\/[^\s]+)/g
    const parts = text.split(urlRegex)

    return parts.map((part, i) => {
      if (part.match(urlRegex)) {
        return (
          <a
            key={i}
            href={part}
            target="_blank"
            rel="noopener noreferrer"
            className="text-spot underline font-mono break-all hover:text-white transition"
          >
            {part}
          </a>
        )
      }
      return part
    })
  }

  async function startRecording() {
    setTranscript('')
    setBotResponse('')
    setExtractedLink('')
    audioChunksRef.current = []

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data)
      }

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
        await sendAudioToBackend(audioBlob)
      }

      mediaRecorder.start()
      setRecording(true)
    } catch (err) {
      alert('Microphone access denied or not available.')
    }
  }

  function stopRecording() {
    if (mediaRecorderRef.current && recording) {
      mediaRecorderRef.current.stop()
      setRecording(false)
    }
  }

  async function sendAudioToBackend(blob) {
    setProcessing(true)
    const formData = new FormData()
    formData.append('audio', blob, 'recording.webm')

    try {
      const token = getStoredToken()
      const headers = {}
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      const res = await fetch('http://localhost:8000/chat/voice', {
        method: 'POST',
        headers: headers,
        body: formData,
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || 'Voice recognition error')
      }

      const transcriptHeader = res.headers.get('X-Transcript') || ''
      const replyHeader = res.headers.get('X-Reply-Text') || ''

      setTranscript(transcriptHeader)
      setBotResponse(replyHeader)

      // Check if reply has a payment link
      const match = replyHeader.match(/(https?:\/\/[^\s]+)/)
      if (match) {
        setExtractedLink(match[0])
      }

      const audioBlob = await res.blob()
      const audioUrl = URL.createObjectURL(audioBlob)
      const audio = new Audio(audioUrl)
      audio.play()
    } catch (err) {
      setBotResponse(err.message || 'Failed to process voice. Make sure backend is running.')
    } finally {
      setProcessing(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-stage border border-edge rounded-3xl p-8 max-w-md w-full text-center relative shadow-2xl max-h-[90vh] overflow-y-auto">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-haze hover:text-paper text-xl"
        >
          ✕
        </button>

        <h2 className="font-display text-2xl tracking-wide mb-1">CONCERT VOICE AGENT</h2>
        <p className="text-xs text-haze mb-6">Talk to search shows, check bookings, or reserve tickets</p>

        <div className="my-6 flex flex-col items-center justify-center">
          <button
            onClick={recording ? stopRecording : startRecording}
            disabled={processing}
            className={`w-24 h-24 rounded-full flex items-center justify-center text-3xl transition duration-300 shadow-xl ${
              recording
                ? 'bg-red-500 text-white animate-pulse shadow-red-500/50 scale-110'
                : 'bg-spot text-void hover:opacity-90'
            }`}
          >
            {recording ? '⏹' : '🎙️'}
          </button>
          <span className="text-sm font-mono mt-4 text-haze">
            {recording ? 'Listening... Tap to stop' : processing ? 'Processing Voice...' : 'Tap Mic to Speak'}
          </span>
        </div>

        {transcript && (
          <div className="bg-void/40 border border-edge rounded-xl p-3 mb-3 text-left">
            <p className="text-xs text-haze font-mono">You said:</p>
            <p className="text-sm text-paper italic">"{transcript}"</p>
          </div>
        )}

        {botResponse && (
          <div className="bg-spot/10 border border-spot/30 rounded-xl p-4 text-left space-y-3">
            <p className="text-xs text-spot font-mono">Agent Reply:</p>
            <div className="text-sm text-paper leading-relaxed">
              {formatReplyWithLinks(botResponse)}
            </div>

            {/* Direct Prominent Payment Button if Link Exists */}
            {extractedLink && (
              <div className="pt-2">
                <a
                  href={extractedLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-spot w-full block text-center py-2.5 text-sm font-semibold tracking-wide shadow-lg"
                >
                  💳 Complete Payment Now
                </a>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}