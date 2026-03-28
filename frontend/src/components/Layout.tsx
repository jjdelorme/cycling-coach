import { useState, type ReactNode } from 'react'
import CoachPanel from './CoachPanel'
import UserAvatar from './UserAvatar'
import { useTheme } from '../lib/theme'
import { useAuth } from '../lib/auth'

const tabs = [
  { key: 'dashboard', label: 'Dashboard', icon: '📊' },
  { key: 'rides', label: 'Rides', icon: '🚴' },
  { key: 'calendar', label: 'Calendar', icon: '📅' },
  { key: 'analysis', label: 'Analysis', icon: '📈' },
] as const

export type TabKey = (typeof tabs)[number]['key'] | 'settings' | 'admin'

export interface ViewContext {
  tab: TabKey
  rideId?: number
  rideDate?: string
  calendarDate?: string
}

interface LayoutProps {
  activeTab: TabKey
  onTabChange: (tab: TabKey) => void
  viewContext?: ViewContext
  children: ReactNode
}

export default function Layout({ activeTab, onTabChange, viewContext, children }: LayoutProps) {
  const [coachOpen, setCoachOpen] = useState(false)
  const { theme, toggle: toggleTheme } = useTheme()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  return (
    <div className="flex h-screen h-[100dvh] flex-col">
      {/* Top nav - desktop */}
      <header className="hidden md:flex items-center justify-between border-b border-border bg-surface px-4 py-2">
        <div className="flex items-center gap-1">
          {tabs.map(t => (
            <button
              key={t.key}
              onClick={() => onTabChange(t.key)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                activeTab === t.key
                  ? 'bg-surface2 text-text border border-accent'
                  : 'text-text-muted hover:text-text hover:bg-surface2/50 border border-transparent'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setCoachOpen(o => !o)}
            className={`p-1.5 rounded-md text-sm transition-colors ${
              coachOpen
                ? 'bg-accent text-white'
                : 'text-text-muted hover:text-text hover:bg-surface2/50'
            }`}
            title="Coach"
          >
            💬
          </button>
          <button
            onClick={toggleTheme}
            className="p-1.5 rounded-md text-sm transition-colors text-text-muted hover:text-text hover:bg-surface2/50"
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
          {isAdmin && (
            <button
              onClick={() => onTabChange('admin')}
              className={`p-1.5 rounded-md text-sm transition-colors ${
                activeTab === 'admin'
                  ? 'text-accent'
                  : 'text-text-muted hover:text-text hover:bg-surface2/50'
              }`}
              title="User Management"
            >
              👥
            </button>
          )}
          <button
            onClick={() => onTabChange('settings')}
            className={`p-1.5 rounded-md text-sm transition-colors ${
              activeTab === 'settings'
                ? 'text-accent'
                : 'text-text-muted hover:text-text hover:bg-surface2/50'
            }`}
            title="Settings"
          >
            ⚙️
          </button>
          <UserAvatar />
        </div>
      </header>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden relative">
        <main className={`flex-1 overflow-y-auto p-4 md:p-6 ${coachOpen ? 'hidden md:block' : ''}`}>
          {children}
        </main>
        {coachOpen && (
          <CoachPanel onClose={() => setCoachOpen(false)} viewContext={viewContext} />
        )}
      </div>

      {/* Bottom nav - mobile */}
      <nav className="md:hidden flex border-t border-border bg-surface">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => { onTabChange(t.key); setCoachOpen(false) }}
            className={`flex-1 flex flex-col items-center py-2 text-xs transition-colors ${
              activeTab === t.key && !coachOpen ? 'text-accent' : 'text-text-muted'
            }`}
          >
            <span className="text-lg">{t.icon}</span>
            <span>{t.label}</span>
          </button>
        ))}
        <button
          onClick={() => setCoachOpen(o => !o)}
          className={`flex-1 flex flex-col items-center py-2 text-xs ${
            coachOpen ? 'text-accent' : 'text-text-muted'
          }`}
        >
          <span className="text-lg">💬</span>
          <span>Coach</span>
        </button>
        {isAdmin && (
          <button
            onClick={() => { onTabChange('admin'); setCoachOpen(false) }}
            className={`flex-1 flex flex-col items-center py-2 text-xs ${
              activeTab === 'admin' && !coachOpen ? 'text-accent' : 'text-text-muted'
            }`}
          >
            <span className="text-lg">👥</span>
            <span>Users</span>
          </button>
        )}
        <button
          onClick={() => { onTabChange('settings'); setCoachOpen(false) }}
          className={`flex-1 flex flex-col items-center py-2 text-xs ${
            activeTab === 'settings' && !coachOpen ? 'text-accent' : 'text-text-muted'
          }`}
        >
          <span className="text-lg">⚙️</span>
          <span>Settings</span>
        </button>
      </nav>
    </div>
  )
}
