import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'

export default function ChatPage() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: "Hey — I'm your booking assistant. Ask me about artists, venues, showtimes, or your past bookings.",
    },
  ])

  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

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
    <div className="max-w-2xl mx-auto px-6 py-10 flex flex-col h-[calc(100vh-64px)]">
      <p className="eyebrow mb-2">Ask anything</p>

      <h1 className="font-display text-4xl tracking-wide mb-6">
        THE ASSISTANT
      </h1>

      {/* Chat messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1 mb-4">
        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex ${
              m.role === 'user' ? 'justify-end' : 'justify-start'
            }`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap leading-relaxed ${
                m.role === 'user'
                  ? 'bg-spot text-void font-medium rounded-br-sm'
                  : 'bg-stage border border-edge text-paper rounded-bl-sm'
              }`}
            >
              {m.text}
            </div>
          </div>
        ))}

        {sending && (
          <div className="flex justify-start">
            <div className="bg-stage border border-edge rounded-2xl rounded-bl-sm px-4 py-3 text-sm text-haze">
              Thinking…
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Telegram Support */}
      <div
        style={{
          padding: '10px',
          textAlign: 'center',
          fontSize: '14px',
        }}
      >
        💬 We also support Telegram!

        <a
          href="https://t.me/Apra_shaktibot"
          target="_blank"
          rel="noopener noreferrer"
          style={{
            color: '#FF2D55',
            fontWeight: 'bold',
            marginLeft: '6px',
          }}
        >
          Chat with us on Telegram →
        </a>
      </div>

      {/* Error */}
      {error && (
        <p className="text-spot text-sm mb-2">
          {error}
        </p>
      )}

      {/* Message Input */}
      <form onSubmit={handleSend} className="flex gap-2">
        <input
          className="field"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. Show me Arijit Singh concerts in Mumbai"
        />

        <button
          type="submit"
          disabled={sending}
          className="btn-spot !px-6"
        >
          Send
        </button>
      </form>
    </div>
  )
}