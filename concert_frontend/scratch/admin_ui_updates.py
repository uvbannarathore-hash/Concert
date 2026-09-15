import re
import os

filepath = "C:/Users/uvban/OneDrive/Desktop/Concert/concert_frontend/src/pages/AdminPage.jsx"

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. State additions
state_additions = """
  // Multi-chat
  const [activeSessionId, setActiveSessionId] = useState(() => {
    return localStorage.getItem('active_admin_chat_session') || localStorage.getItem('user_id')
  })
  const [chatSessions, setChatSessions] = useState([])
  
  // Pricing Notifications
  const [pricingNotifications, setPricingNotifications] = useState([])
  const [showNotificationsModal, setShowNotificationsModal] = useState(false)
"""
content = re.sub(
    r'(const \[chatSending, setChatSending\] = useState\(false\))',
    r'\1\n' + state_additions,
    content
)

# 2. Add dependencies and Realtime logic for both Chat and Notifications
init_chat_old = r'useEffect\(\(\) => \{[\s\S]*?isUnmounted = true\n      if \(channel\) supabase\.removeChannel\(channel\)\n    \}\n  \}, \[\]\)'

init_chat_new = """
  // Load previous chat sessions for the sidebar
  useEffect(() => {
    async function loadSessions() {
      const adminId = localStorage.getItem('user_id')
      if (!adminId) return
      
      const { data } = await supabase
        .from('admin_chat_history')
        .select('session_id, role, message, created_at')
        .eq('admin_user_id', adminId)
        .order('created_at', { ascending: false })
        
      if (!data) return
      
      const sessionsMap = new Map()
      data.forEach(row => {
        if (!sessionsMap.has(row.session_id)) {
          sessionsMap.set(row.session_id, {
            sessionId: row.session_id,
            latestTimestamp: row.created_at,
            title: 'New Chat'
          })
        }
        if (row.role === 'user') {
          // the oldest user message becomes the title (by overwriting backwards)
          sessionsMap.get(row.session_id).title = row.message.slice(0, 35) + (row.message.length > 35 ? '...' : '')
        }
      })
      setChatSessions(Array.from(sessionsMap.values()))
    }
    loadSessions()
  }, [])

  // Chat messages and Realtime scoping
  useEffect(() => {
    let channel = null
    let isUnmounted = false
    
    async function initChat() {
      if (isUnmounted || !activeSessionId) return
      
      const { data } = await supabase
        .from('admin_chat_history')
        .select('*')
        .eq('session_id', activeSessionId)
        .order('created_at', { ascending: true })
        
      if (isUnmounted) return
        
      const welcomeMsg = { id: 'welcome', role: 'assistant', text: "Welcome to the backstage panel. I'm your AI Admin Assistant. I can create, update, or cancel events, edit ticket pricing, or summarize sales. Type below to get started, and feel free to upload poster images (📎) or map coordinates (📍)." }
      
      if (data && data.length > 0) {
        const historyMsgs = data.map(row => ({ id: row.id, role: row.role, text: row.message }))
        setChatMessages([welcomeMsg, ...historyMsgs])
      } else {
        setChatMessages([welcomeMsg])
      }
      
      channel = supabase.channel(`admin_chat_${activeSessionId}`)
        .on(
          'postgres_changes',
          { event: 'INSERT', schema: 'public', table: 'admin_chat_history', filter: `session_id=eq.${activeSessionId}` },
          (payload) => {
            if (isUnmounted) return
            const newMsg = payload.new
            setChatMessages(prev => {
              if (prev.some(m => m.id === newMsg.id)) return prev
              const optIndex = prev.findIndex(m => !m.id && m.role === newMsg.role && m.text === newMsg.message)
              if (optIndex !== -1) {
                const copy = [...prev]
                copy[optIndex] = { ...copy[optIndex], id: newMsg.id }
                return copy
              }
              return [...prev, { id: newMsg.id, role: newMsg.role, text: newMsg.message }]
            })
          }
        )
        .subscribe()
    }
    
    initChat()
    
    return () => {
      isUnmounted = true
      if (channel) supabase.removeChannel(channel)
    }
  }, [activeSessionId])
  
  // Pricing Notifications Data & Realtime
  useEffect(() => {
    let isUnmounted = false
    
    async function fetchNotifs() {
      try {
        const { notifications } = await adminApi.getPricingNotifications()
        if (!isUnmounted && notifications) {
          setPricingNotifications(notifications)
        }
      } catch (err) {
        console.error('Failed to load notifications:', err)
      }
    }
    fetchNotifs()
    
    const notifChannel = supabase.channel('pricing_notifs')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'pricing_notifications', filter: `admin_user_id=eq.${localStorage.getItem('user_id')}` },
        (payload) => {
          if (isUnmounted) return
          if (payload.new.status === 'pending') {
             setPricingNotifications(prev => [payload.new, ...prev])
          }
        }
      )
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'pricing_notifications', filter: `admin_user_id=eq.${localStorage.getItem('user_id')}` },
        (payload) => {
          if (isUnmounted) return
          if (payload.new.status !== 'pending') {
             setPricingNotifications(prev => prev.filter(n => n.id !== payload.new.id))
          }
        }
      )
      .subscribe()
      
    return () => {
      isUnmounted = true
      supabase.removeChannel(notifChannel)
    }
  }, [])
"""
content = re.sub(init_chat_old, init_chat_new, content)

# 3. Update chat sending to pass activeSessionId
content = re.sub(
    r'(const \{ reply \} = await adminApi\.chat\(msgText, chatImage, venueLocation\))',
    r'const { reply } = await adminApi.chat(msgText, chatImage, venueLocation, activeSessionId)\n' +
    r'      setChatSessions(prev => {\n' +
    r'        if (!prev.find(s => s.sessionId === activeSessionId)) {\n' +
    r'           return [{ sessionId: activeSessionId, title: msgText.slice(0, 35), latestTimestamp: new Date().toISOString() }, ...prev]\n' +
    r'        }\n' +
    r'        return prev\n' +
    r'      })',
    content
)

# 4. Modify Assistant UI layout to include Sidebar
old_assistant_ui = r'<div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden flex flex-col h-\[600px\]">'

new_assistant_ui = """
<div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden flex h-[600px]">
  <div className="w-64 border-r border-gray-200 bg-gray-50 flex flex-col">
    <div className="p-4 border-b border-gray-200">
      <button
        onClick={() => {
          const newId = crypto.randomUUID()
          setActiveSessionId(newId)
          localStorage.setItem('active_admin_chat_session', newId)
        }}
        className="w-full py-2 bg-indigo-600 text-white rounded-md hover:bg-indigo-700 transition font-medium"
      >
        + New Chat
      </button>
    </div>
    <div className="flex-1 overflow-y-auto p-2 space-y-1">
      {chatSessions.length === 0 && (
        <div className="text-sm text-gray-500 text-center mt-4">No previous chats yet.</div>
      )}
      {chatSessions.map(sess => (
        <button
          key={sess.sessionId}
          onClick={() => {
            setActiveSessionId(sess.sessionId)
            localStorage.setItem('active_admin_chat_session', sess.sessionId)
          }}
          className={`w-full text-left p-3 rounded-md text-sm truncate transition ${activeSessionId === sess.sessionId ? 'bg-indigo-100 text-indigo-900 font-semibold' : 'hover:bg-gray-200 text-gray-700'}`}
        >
          {sess.title || 'New Chat'}
        </button>
      ))}
    </div>
  </div>
  <div className="flex-1 flex flex-col overflow-hidden">
"""
content = content.replace(old_assistant_ui, new_assistant_ui)
content = content.replace('      </div>\n    </div>\n  )\n}\n\n// --------------------------\n', '        </div>\n      </div>\n    </div>\n  )\n}\n\n// --------------------------\n')

# 5. Add Bell icon and Notifications Modal
nav_buttons = r'(<button\s+onClick=\{\(\) => setTab\(\'bookings\'\)\}\s+className=\{`px-3 py-2 text-sm font-medium rounded-md \$\{tab === \'bookings\' \? \'bg-indigo-100 text-indigo-700\' : \'text-gray-500 hover:text-gray-700 hover:bg-gray-100\'\}`\}>\s+Bookings\s+</button>)'

bell_icon = """
            <div className="relative">
              <button
                onClick={() => setShowNotificationsModal(true)}
                className="ml-4 p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <span className="sr-only">View notifications</span>
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
                </svg>
                {pricingNotifications.length > 0 && (
                  <span className="absolute top-0 right-0 inline-flex items-center justify-center px-2 py-1 text-xs font-bold leading-none text-white transform translate-x-1/4 -translate-y-1/4 bg-red-600 rounded-full">
                    {pricingNotifications.length}
                  </span>
                )}
              </button>
            </div>
"""
content = re.sub(nav_buttons, r'\1\n' + bell_icon, content)

modal_ui = """
      {showNotificationsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black bg-opacity-50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
            <div className="flex justify-between items-center p-4 border-b">
              <h3 className="text-lg font-semibold">Pricing Notifications</h3>
              <button onClick={() => setShowNotificationsModal(false)} className="text-gray-400 hover:text-gray-600">&times;</button>
            </div>
            <div className="overflow-y-auto p-4 space-y-4">
              {pricingNotifications.length === 0 && (
                <p className="text-gray-500 text-center">No pending notifications.</p>
              )}
              {pricingNotifications.map(notif => (
                <div key={notif.id} className="border rounded-lg p-4 bg-gray-50">
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <span className="font-semibold text-gray-900">High Demand: {notif.category}</span>
                      <p className="text-sm text-gray-500">Event ID: {notif.event_id}</p>
                    </div>
                    <span className="px-2 py-1 text-xs font-medium bg-yellow-100 text-yellow-800 rounded">Pending</span>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4 text-sm mb-4">
                    <div><span className="text-gray-500">Capacity:</span> {notif.percent_full}% full</div>
                    <div><span className="text-gray-500">Remaining:</span> {notif.remaining_seats} seats</div>
                    <div><span className="text-gray-500">Velocity:</span> {notif.velocity_seats} in 48h</div>
                    <div><span className="text-gray-500">Days to event:</span> {notif.days_remaining}</div>
                  </div>
                  
                  <p className="text-sm text-gray-700 italic mb-4">"{notif.justification}"</p>
                  
                  <div className="flex items-center gap-4 bg-white p-3 rounded border">
                    <div>
                      <div className="text-xs text-gray-500">Current Price</div>
                      <div className="font-semibold">₹{notif.current_price}</div>
                    </div>
                    <div>
                      <div className="text-xs text-indigo-500">AI Suggested</div>
                      <div className="font-semibold text-indigo-600">₹{notif.suggested_price}</div>
                    </div>
                    <div className="flex-1">
                      <div className="text-xs text-gray-500">Final Price (Editable)</div>
                      <input 
                        type="number"
                        id={`price_${notif.id}`}
                        defaultValue={notif.suggested_price}
                        className="w-full border-gray-300 rounded shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm mt-1 p-1"
                      />
                    </div>
                  </div>
                  
                  <div className="mt-4 flex justify-end gap-2">
                    <button 
                      onClick={async () => {
                        try {
                          await adminApi.resolvePricingNotification(notif.id, 'dismiss')
                          setPricingNotifications(prev => prev.filter(n => n.id !== notif.id))
                        } catch (err) {
                          alert('Failed to dismiss: ' + err.message)
                        }
                      }}
                      className="px-3 py-1.5 border border-gray-300 text-gray-700 rounded hover:bg-gray-100 text-sm font-medium"
                    >
                      Dismiss
                    </button>
                    <button 
                      onClick={async () => {
                        const val = parseInt(document.getElementById(`price_${notif.id}`).value)
                        if (isNaN(val) || val <= 0) return alert("Valid positive price required.")
                        
                        if (val > notif.current_price * 1.5) {
                          if (!window.confirm(`Warning: ₹${val} is more than 50% higher than the current price (₹${notif.current_price}). Proceed?`)) {
                            return
                          }
                        }
                        
                        try {
                          await adminApi.resolvePricingNotification(notif.id, 'approve', val)
                          setPricingNotifications(prev => prev.filter(n => n.id !== notif.id))
                        } catch (err) {
                          alert('Failed to approve: ' + err.message)
                        }
                      }}
                      className="px-3 py-1.5 bg-indigo-600 text-white rounded hover:bg-indigo-700 text-sm font-medium"
                    >
                      Apply Price
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
"""
content = re.sub(r'(<div className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">)', r'\1\n' + modal_ui, content)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("AdminPage.jsx updated successfully!")
