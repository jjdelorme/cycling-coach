import { useState, useRef, useEffect } from 'react'
import { useAuth } from '../lib/auth'
import { useTheme } from '../lib/theme'

const ROLE_LABELS: Record<string, string> = {
  admin: 'Admin',
  readwrite: 'Read/Write',
  read: 'Read Only',
  none: 'No Access',
}

export default function UserAvatar() {
  const { user, logout } = useAuth()
  const { theme, toggle } = useTheme()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  if (!user) return null

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="w-8 h-8 rounded-full overflow-hidden border-2 border-border hover:border-accent transition-colors flex items-center justify-center bg-surface2 text-text text-sm font-medium"
        title={user.email}
      >
        {user.avatar ? (
          <img src={user.avatar} alt={user.name} className="w-full h-full object-cover" />
        ) : (
          user.name.charAt(0).toUpperCase()
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-10 w-64 bg-surface border border-border rounded-lg shadow-lg z-50">
          <div className="p-3 border-b border-border">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full overflow-hidden bg-surface2 flex items-center justify-center text-text font-medium">
                {user.avatar ? (
                  <img src={user.avatar} alt={user.name} className="w-full h-full object-cover" />
                ) : (
                  user.name.charAt(0).toUpperCase()
                )}
              </div>
              <div className="min-w-0">
                <div className="text-text text-sm font-medium truncate">{user.name}</div>
                <div className="text-text-muted text-xs truncate">{user.email}</div>
                <div className="text-accent text-xs">{ROLE_LABELS[user.role] || user.role}</div>
              </div>
            </div>
          </div>
          <div className="p-1">
            <button
              onClick={() => { toggle(); setOpen(false) }}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-text-muted hover:text-text hover:bg-surface2/50 rounded transition-colors"
            >
              <span>{theme === 'dark' ? '☀️' : '🌙'}</span>
              <span>{theme === 'dark' ? 'Light Mode' : 'Dark Mode'}</span>
            </button>
            <button
              onClick={() => { logout(); setOpen(false) }}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-text-muted hover:text-text hover:bg-surface2/50 rounded transition-colors"
            >
              <span>🚪</span>
              <span>Sign Out</span>
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
