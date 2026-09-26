import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { Check, Crown } from 'lucide-react'

export default function PricingPage() {
  const [tab, setTab] = useState('fans')
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    if (api.isLoggedIn()) {
      api.myProfile().then(setProfile).catch(() => {})
    }
  }, [])

  const loadRazorpay = () => {
    return new Promise((resolve) => {
      if (window.Razorpay) return resolve(true)
      const script = document.createElement('script')
      script.src = 'https://checkout.razorpay.com/v1/checkout.js'
      script.onload = () => resolve(true)
      script.onerror = () => resolve(false)
      document.body.appendChild(script)
    })
  }

  async function handleSubscribe(planType) {
    if (!api.isLoggedIn()) return window.location.href = '/login'
    setError('')
    setSuccess('')
    setLoading(true)
    try {
      const order = await api.subscribePlus(planType)
      const isLoaded = await loadRazorpay()
      if (!isLoaded) throw new Error('Razorpay SDK failed to load')

      const options = {
        key: order.razorpay_key_id,
        amount: order.amount * 100, // Amount should be in paise
        currency: order.currency || 'INR',
        name: 'LiveWire Plus',
        description: `LiveWire Plus - ${planType.toUpperCase()} Plan`,
        order_id: order.razorpay_order_id || order.order_id, // depends on backend
        modal: {
          ondismiss: () => {
            document.body.style.overflow = 'auto';
          }
        },
        handler: async function (response) {
          try {
            await api.verifyPlusSubscription({
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
              plan_type: planType
            })
            setSuccess('Subscription successful! Welcome to LiveWire Plus.')
            const p = await api.myProfile()
            setProfile(p)
          } catch (e) {
            setError(e.message)
          }
        },
        prefill: {
          name: profile?.name || '',
          email: profile?.email || '',
        },
        theme: {
          color: '#f43f5e',
        },
      }

      const rzp = new window.Razorpay(options)
      rzp.on('payment.failed', function (response) {
        setError(response.error.description || 'Payment failed')
      })
      rzp.open()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleUpgrade(planTier) {
    if (!api.isLoggedIn()) return window.location.href = '/login'

    if (profile?.plan_expiry_date && profile.plan_tier !== planTier) {
      const expiry = new Date(profile.plan_expiry_date)
      if (expiry > new Date()) {
        const confirmed = window.confirm(`You already have an active plan until ${expiry.toLocaleDateString()}. Upgrading will restart your billing cycle from today and forfeit any remaining time. Proceed?`)
        if (!confirmed) return
      }
    }

    setError('')
    setSuccess('')
    setLoading(true)
    try {
      const order = await api.upgradePlan(planTier)
      const isLoaded = await loadRazorpay()
      if (!isLoaded) throw new Error('Razorpay SDK failed to load')

      const options = {
        key: order.razorpay_key_id,
        amount: order.amount * 100, // In paise
        currency: order.currency || 'INR',
        name: 'LiveWire Organizer',
        description: `Upgrade to ${planTier.toUpperCase()} Plan`,
        order_id: order.razorpay_order_id || order.order_id, // depends on backend
        modal: {
          ondismiss: () => {
            document.body.style.overflow = 'auto';
          }
        },
        handler: async function (response) {
          try {
            await api.verifyPlanUpgrade({
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
              plan_tier: planTier
            })
            setSuccess(`Successfully upgraded to the ${planTier} plan!`)
            const p = await api.myProfile()
            setProfile(p)
          } catch (e) {
            setError(e.message)
          }
        },
        prefill: {
          name: profile?.name || '',
          email: profile?.email || '',
        },
        theme: {
          color: '#10b981', // green for organizers
        },
      }

      const rzp = new window.Razorpay(options)
      rzp.on('payment.failed', function (response) {
        setError(response.error.description || 'Payment failed')
      })
      rzp.open()
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-24 animate-fade-in-up">
      <div className="text-center mb-16">
        <h1 className="font-display text-5xl tracking-wider text-paper uppercase mb-4">Pricing Plans</h1>
        <p className="text-haze text-lg max-w-2xl mx-auto">Choose the perfect plan to elevate your experience on LiveWire, whether you're front-row for the show or running it from backstage.</p>
      </div>

      <div className="flex justify-center mb-12">
        <div className="bg-stage/50 border border-white/[0.04] p-1.5 rounded-full flex gap-2">
          <button
            onClick={() => setTab('fans')}
            className={`px-8 py-3 rounded-full text-sm font-bold tracking-widest uppercase transition-all ${tab === 'fans' ? 'bg-spot text-white shadow-lg shadow-spot/20' : 'text-haze hover:text-paper hover:bg-white/[0.04]'}`}
          >
            For Fans
          </button>
          <button
            onClick={() => setTab('organizers')}
            className={`px-8 py-3 rounded-full text-sm font-bold tracking-widest uppercase transition-all ${tab === 'organizers' ? 'bg-go text-white shadow-lg shadow-go/20' : 'text-haze hover:text-paper hover:bg-white/[0.04]'}`}
          >
            For Organizers
          </button>
        </div>
      </div>

      {error && <div className="mb-8 p-4 bg-spot/20 border border-spot text-spot rounded-xl text-center max-w-lg mx-auto">{error}</div>}
      {success && <div className="mb-8 p-4 bg-go/20 border border-go text-go rounded-xl text-center max-w-lg mx-auto">{success}</div>}

      {tab === 'fans' && (
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-display text-spot mb-2 uppercase tracking-wide">LiveWire Plus</h2>
            <p className="text-haze">Zero booking fees. Exclusive drops. No nonsense.</p>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {/* Monthly */}
            <div className="bg-stage border border-white/[0.06] rounded-3xl p-8 hover:border-spot/30 transition-all flex flex-col relative overflow-hidden">
              <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-spot to-transparent opacity-50"></div>
              <h3 className="text-xl font-bold text-paper mb-2 uppercase tracking-wider">Monthly Pass</h3>
              <div className="flex items-baseline gap-2 mb-6">
                <span className="text-5xl font-display text-white">₹149</span>
                <span className="text-haze">/ month</span>
              </div>
              <ul className="space-y-4 mb-8 flex-grow">
                <li className="flex gap-3 text-haze"><Check className="text-spot shrink-0" size={20} /><span>0% platform fee on up to 4 bookings per month</span></li>
                <li className="flex gap-3 text-haze"><Check className="text-spot shrink-0" size={20} /><span>Cancel anytime</span></li>
                <li className="flex gap-3 text-haze"><Check className="text-spot shrink-0" size={20} /><span>Early access to select presales</span></li>
              </ul>
              <button 
                onClick={() => handleSubscribe('monthly')}
                disabled={loading}
                className="w-full btn-spot py-4 text-sm"
              >
                {loading ? 'Processing...' : (profile?.is_plus_member && profile?.plus_plan_type === 'monthly' ? 'Extend Monthly Pass' : 'Subscribe Monthly')}
              </button>
            </div>

            {/* Yearly */}
            <div className="bg-gradient-to-b from-spot/10 to-stage border border-spot/50 rounded-3xl p-8 hover:border-spot transition-all flex flex-col relative overflow-hidden shadow-2xl shadow-spot/10 transform md:-translate-y-4">
              <div className="absolute top-4 right-4 bg-spot text-white text-[10px] font-bold px-3 py-1 rounded-full uppercase tracking-widest">
                Best Value
              </div>
              <h3 className="text-xl font-bold text-paper mb-2 uppercase tracking-wider flex items-center gap-2"><Crown size={20} className="text-spot" /> Yearly Pass</h3>
              <div className="flex items-baseline gap-2 mb-6">
                <span className="text-5xl font-display text-white">₹1,499</span>
                <span className="text-haze">/ year</span>
              </div>
              <ul className="space-y-4 mb-8 flex-grow">
                <li className="flex gap-3 text-paper"><Check className="text-spot shrink-0" size={20} /><span>Save ₹289 annually</span></li>
                <li className="flex gap-3 text-paper"><Check className="text-spot shrink-0" size={20} /><span>0% platform fee on up to 4 bookings per month</span></li>
                <li className="flex gap-3 text-paper"><Check className="text-spot shrink-0" size={20} /><span>Priority support channel</span></li>
                <li className="flex gap-3 text-paper"><Check className="text-spot shrink-0" size={20} /><span>Exclusive VIP lounge access at partner venues</span></li>
              </ul>
              <button 
                onClick={() => handleSubscribe('yearly')}
                disabled={loading}
                className="w-full bg-spot hover:bg-spot2 text-white font-bold py-4 rounded-xl uppercase tracking-widest text-sm transition-all shadow-lg shadow-spot/20"
              >
                {loading ? 'Processing...' : (profile?.is_plus_member && profile?.plus_plan_type === 'yearly' ? 'Extend Yearly Pass' : 'Subscribe Yearly')}
              </button>
            </div>
          </div>
        </div>
      )}

      {tab === 'organizers' && (
        <div>
          <div className="text-center mb-12">
            <h2 className="text-3xl font-display text-go mb-2 uppercase tracking-wide">Creator Tiers</h2>
            <p className="text-haze">Maximize your margins. Scale your events.</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Starter */}
            <div className="bg-stage border border-white/[0.06] rounded-3xl p-8 flex flex-col relative">
              <h3 className="text-xl font-bold text-paper mb-2 uppercase tracking-wider">Starter</h3>
              <div className="flex items-baseline gap-2 mb-2">
                <span className="text-5xl font-display text-white">5%</span>
                <span className="text-haze text-xs uppercase tracking-wider">Commission</span>
              </div>
              <p className="text-sm text-haze mb-6 pb-6 border-b border-white/[0.04]">Free forever. Perfect for local gigs and first-time promoters.</p>
              <ul className="space-y-4 mb-8 flex-grow text-sm">
                <li className="flex gap-3 text-haze"><Check className="text-white/40 shrink-0" size={18} /><span>Basic analytics dashboard</span></li>
                <li className="flex gap-3 text-haze"><Check className="text-white/40 shrink-0" size={18} /><span>Standard payout speed (T+3)</span></li>
              </ul>
              {(!profile?.plan_tier || profile.plan_tier === 'starter') ? (
                <div className="text-center text-xs text-go uppercase tracking-widest font-bold py-4 bg-go/10 border border-go/20 rounded-xl">
                  Current Plan
                </div>
              ) : (
                <div className="text-center text-xs text-haze uppercase tracking-widest font-bold py-4 bg-white/[0.02] rounded-xl">
                  Included
                </div>
              )}
            </div>

            {/* Pro */}
            <div className="bg-gradient-to-b from-go/10 to-stage border border-go/40 rounded-3xl p-8 flex flex-col relative shadow-xl shadow-go/5 transform md:-translate-y-4">
               <div className="absolute top-4 right-4 bg-go text-void text-[10px] font-bold px-3 py-1 rounded-full uppercase tracking-widest">
                Most Popular
              </div>
              <h3 className="text-xl font-bold text-paper mb-2 uppercase tracking-wider text-go">Pro</h3>
              <div className="flex items-baseline gap-2 mb-2">
                <span className="text-5xl font-display text-white">3%</span>
                <span className="text-haze text-xs uppercase tracking-wider">Commission</span>
              </div>
              <p className="text-sm text-haze mb-6 pb-6 border-b border-white/[0.04]">₹19,999 / year. Built for touring artists and independent venues.</p>
              <ul className="space-y-4 mb-8 flex-grow text-sm">
                <li className="flex gap-3 text-paper"><Check className="text-go shrink-0" size={18} /><span>Advanced demographic insights</span></li>
                <li className="flex gap-3 text-paper"><Check className="text-go shrink-0" size={18} /><span>Fast payouts (T+1)</span></li>
                <li className="flex gap-3 text-paper"><Check className="text-go shrink-0" size={18} /><span>Custom coupon creation</span></li>
              </ul>
              {profile?.plan_tier === 'pro' ? (
                <div className="text-center text-xs text-go uppercase tracking-widest font-bold py-4 bg-go/10 border border-go/20 rounded-xl">
                  Current Plan
                </div>
              ) : (
                <button 
                  onClick={() => handleUpgrade('pro')}
                  disabled={loading}
                  className="w-full bg-go hover:bg-emerald-400 text-void font-bold py-4 rounded-xl uppercase tracking-widest text-xs transition-all shadow-lg shadow-go/20"
                >
                  {loading ? 'Processing...' : 'Upgrade to Pro'}
                </button>
              )}
            </div>

            {/* Business */}
            <div className="bg-stage border border-white/[0.06] rounded-3xl p-8 flex flex-col relative">
              <h3 className="text-xl font-bold text-paper mb-2 uppercase tracking-wider">Business</h3>
              <div className="flex items-baseline gap-2 mb-2">
                <span className="text-5xl font-display text-white">1.5%</span>
                <span className="text-haze text-xs uppercase tracking-wider">Commission</span>
              </div>
              <p className="text-sm text-haze mb-6 pb-6 border-b border-white/[0.04]">₹79,999 / year. Unrivaled margins for high-volume enterprise organizers.</p>
              <ul className="space-y-4 mb-8 flex-grow text-sm">
                <li className="flex gap-3 text-haze"><Check className="text-white/40 shrink-0" size={18} /><span>API Access</span></li>
                <li className="flex gap-3 text-haze"><Check className="text-white/40 shrink-0" size={18} /><span>Instant payouts (T+0)</span></li>
                <li className="flex gap-3 text-haze"><Check className="text-white/40 shrink-0" size={18} /><span>Dedicated account manager</span></li>
                <li className="flex gap-3 text-haze"><Check className="text-white/40 shrink-0" size={18} /><span>White-label checkout</span></li>
              </ul>
              {profile?.plan_tier === 'business' ? (
                <div className="text-center text-xs text-go uppercase tracking-widest font-bold py-4 bg-go/10 border border-go/20 rounded-xl">
                  Current Plan
                </div>
              ) : (
                <button 
                  onClick={() => handleUpgrade('business')}
                  disabled={loading}
                  className="w-full bg-white/[0.05] hover:bg-white/[0.1] border border-white/[0.1] text-paper font-bold py-4 rounded-xl uppercase tracking-widest text-xs transition-all"
                >
                  {loading ? 'Processing...' : 'Upgrade to Business'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
