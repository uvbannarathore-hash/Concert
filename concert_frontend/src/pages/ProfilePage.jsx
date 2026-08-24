import { useEffect, useState } from 'react'
import { api } from '../lib/api'

export default function ProfilePage() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')

  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [city, setCity] = useState('')
  const [email, setEmail] = useState('')

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
  }, [])

  async function handleSave(e) {
    e.preventDefault()
    setError('')
    setInfo('')
    setSaving(true)
    try {
      await api.updateProfile({ name, phone, city })
      setInfo('Profile updated.')
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <p className="text-haze text-center py-24">Loading profile…</p>
  }

  return (
    <div className="max-w-lg mx-auto px-6 py-14">
      <p className="eyebrow mb-3">Your account</p>
      <h1 className="font-display text-4xl tracking-wide mb-8">EDIT PROFILE</h1>

      <form onSubmit={handleSave} className="bg-stage border border-edge rounded-2xl p-6 space-y-4">
        <div>
          <label className="block text-sm text-haze mb-1.5">Email</label>
          <input className="field opacity-60" value={email} disabled />
        </div>

        <div>
          <label className="block text-sm text-haze mb-1.5">Name</label>
          <input
            className="field"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-haze mb-1.5">Phone</label>
            <input
              className="field"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="98765 43210"
            />
          </div>
          <div>
            <label className="block text-sm text-haze mb-1.5">City</label>
            <input
              className="field"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              placeholder="Mumbai"
            />
          </div>
        </div>

        {error && (
          <p className="text-sm text-spot bg-spot/10 border border-spot/30 rounded-lg px-3 py-2">
            {error}
          </p>
        )}
        {info && (
          <p className="text-sm text-go bg-go/10 border border-go/30 rounded-lg px-3 py-2">
            {info}
          </p>
        )}

        <button type="submit" disabled={saving} className="btn-spot w-full">
          {saving ? 'Saving…' : 'Save changes'}
        </button>
      </form>
    </div>
  )
}