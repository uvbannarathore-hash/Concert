import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { createClient } from '@supabase/supabase-js'

// Publishable key only - safe for frontend use.
const supabase = createClient(
  'https://yacolxewrrlsxsbblulr.supabase.co',
  'sb_publishable_bE-bCQUEYfZ2VVdQFP-yLQ_ALz82-tN'
)

export default function ProfilePage() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')

  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [city, setCity] = useState('')
  const [email, setEmail] = useState('')

  const [notifyTelegramForWebsite, setNotifyTelegramForWebsite] = useState(false)
  const [hasTelegramLinked, setHasTelegramLinked] = useState(false)
  const [prefSaving, setPrefSaving] = useState(false)

  useEffect(() => {
    api
      .myProfile()
      .then((data) => {
        setName(data.name || '')
        setPhone(data.phone || '')
        setCity(data.city || '')
        setEmail(data.email || '')
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))

    // Fetch the Telegram notification preference directly from Supabase
    // (this column isn't part of the FastAPI profile response).
    const userId = localStorage.getItem('user_id')
    if (userId) {
      supabase
        .from('users')
        .select('notify_telegram_for_website, telegram_chat_id')
        .eq('user_id', userId)
        .single()
        .then(({ data }) => {
          if (data) {
            setNotifyTelegramForWebsite(!!data.notify_telegram_for_website)
            setHasTelegramLinked(!!data.telegram_chat_id)
          }
        })
    }
  }, [])

  async function handleSave(e) {
    e.preventDefault()
    setError('')
    setInfo('')
    setSaving(true)
    try {
      await api.updateProfile({ name, phone, city })
      setInfo('Profile successfully updated.')
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleTelegramPrefToggle(checked) {
    const userId = localStorage.getItem('user_id')
    if (!userId) return

    setNotifyTelegramForWebsite(checked) // optimistic update
    setPrefSaving(true)
    try {
      const { error: updateError } = await supabase
        .from('users')
        .update({ notify_telegram_for_website: checked })
        .eq('user_id', userId)

      if (updateError) throw updateError
    } catch (err) {
      setNotifyTelegramForWebsite(!checked) // revert on failure
      setError('Could not update Telegram preference: ' + err.message)
    } finally {
      setPrefSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="max-w-xl mx-auto px-6 py-24 flex justify-center">
        <div className="space-y-3 text-center">
          <div className="w-8 h-8 border-4 border-spot border-t-transparent rounded-full animate-spin mx-auto"></div>
          <p className="text-xs font-mono text-haze">Loading profile data...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-xl mx-auto px-6 py-12 animate-fade-in-up">
      <div className="mb-8">
        <p className="eyebrow mb-1">User account settings</p>
        <h1 className="font-display text-4xl tracking-wide uppercase text-paper">EDIT PROFILE</h1>
        <p className="text-xs text-haze mt-1">Configure your personal information and contact details</p>
      </div>

      <form onSubmit={handleSave} className="glass-card bg-stage/15 border border-white/[0.04] rounded-2xl p-6 space-y-5 shadow-2xl">
        <div>
          <label className="block text-xs font-mono text-haze/60 mb-2 uppercase">Account Email (ReadOnly)</label>
          <input className="field opacity-40 select-none cursor-not-allowed font-mono text-sm bg-stage2/40" value={email} disabled />
        </div>

        <div>
          <label className="block text-xs font-mono text-haze/60 mb-2 uppercase">Display Name</label>
          <input
            className="field"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
            required
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-mono text-haze/60 mb-2 uppercase">Phone Number</label>
            <input
              className="field font-mono"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="e.g. 98765 43210"
            />
          </div>
          <div>
            <label className="block text-xs font-mono text-haze/60 mb-2 uppercase">City</label>
            <input
              className="field"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              placeholder="e.g. Mumbai"
            />
          </div>
        </div>

        {error && (
          <div className="border border-spot/20 bg-spot/5 text-spot text-xs font-mono rounded-xl p-4">
            ⚠️ Update failed: {error}
          </div>
        )}
        
        {info && (
          <div className="border border-go/20 bg-go/5 text-go text-xs font-mono rounded-xl p-4">
            ✅ Success: {info}
          </div>
        )}

        <button type="submit" disabled={saving} className="btn-spot w-full text-sm font-bold flex items-center justify-center gap-1.5 mt-2">
          {saving ? (
            <>
              <span className="w-4 h-4 border-2 border-void border-t-transparent rounded-full animate-spin"></span>
              Saving changes...
            </>
          ) : (
            'Save Profile'
          )}
        </button>
      </form>

      {/* Notification preferences */}
      <div className="glass-card bg-stage/15 border border-white/[0.04] rounded-2xl p-6 space-y-4 shadow-2xl mt-6">
        <div>
          <h2 className="text-sm font-bold text-paper uppercase tracking-wide">Notification Preferences</h2>
          <p className="text-xs text-haze mt-1">
            Control how you get notified when a website booking is confirmed.
          </p>
        </div>

        {hasTelegramLinked ? (
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={notifyTelegramForWebsite}
              disabled={prefSaving}
              onChange={(e) => handleTelegramPrefToggle(e.target.checked)}
              className="mt-1 w-4 h-4 accent-spot cursor-pointer"
            />
            <span className="text-sm text-paper">
              Also notify me on Telegram when I book from the website
              <span className="block text-xs text-haze mt-0.5">
                By default, website bookings only notify you here in the chat and by email.
                Telegram bookings always notify on Telegram.
              </span>
            </span>
          </label>
        ) : (
          <p className="text-xs text-haze">
            Link your Telegram account (via the assistant) to enable Telegram notifications for website bookings too.
          </p>
        )}
      </div>
    </div>
  )
}