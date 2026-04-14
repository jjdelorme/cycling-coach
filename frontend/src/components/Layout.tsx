import { useState, useEffect, useRef, type ReactNode } from 'react'
import CoachPanel from './CoachPanel'
import UserAvatar from './UserAvatar'
import { useTheme } from '../lib/theme'
import { useAuth } from '../lib/auth'
import {
  LayoutDashboard,
  Bike,
  CalendarDays,
  TrendingUp,
  UtensilsCrossed,
  MessageSquare,
  Sun,
  Moon,
  Users,
  Settings,
  MoreHorizontal,
} from 'lucide-react'

const tabs = [
  { key: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { key: 'rides', label: 'Rides', icon: Bike },
  { key: 'calendar', label: 'Calendar', icon: CalendarDays },
  { key: 'analysis', label: 'Analysis', icon: TrendingUp },
  { key: 'nutrition', label: 'Nutrition', icon: UtensilsCrossed },
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
  nutritionistContext?: string
  nutritionistSessionId?: string
  onOpenNutritionist?: (context?: string, sessionId?: string) => void
  children: ReactNode
}

export default function Layout({ activeTab, onTabChange, viewContext, nutritionistContext, nutritionistSessionId, children }: LayoutProps) {
  const [coachOpen, setCoachOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const moreRef = useRef<HTMLDivElement>(null)
  const { theme, toggle: toggleTheme } = useTheme()

  // Auto-open the coach panel when a nutritionist context or session is injected
  useEffect(() => {
    if (nutritionistContext || nutritionistSessionId) setCoachOpen(true)
  }, [nutritionistContext, nutritionistSessionId])

  // Close More menu on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) setMoreOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const canSettings = user?.role === 'admin' || user?.role === 'readwrite' || user?.role === 'read'
  const isMoreActive = (['rides', 'analysis', 'settings', 'admin'] as TabKey[]).includes(activeTab) && !coachOpen

  return (
    <div className="flex h-screen h-[100dvh] flex-col bg-bg">
      {/* Top nav - desktop */}
      <header className="hidden md:flex items-center justify-between border-b border-border bg-surface px-4 py-2">
        <div className="flex items-center gap-1">
          <div className="mr-4 flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center text-white font-bold italic">
              C
            </div>
            <span className="font-bold text-text tracking-tight">COACH</span>
          </div>
          {tabs.map(t => (
            <button
              key={t.key}
              onClick={() => onTabChange(t.key)}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                activeTab === t.key
                  ? 'bg-surface2 text-text border border-accent/20'
                  : 'text-text-muted hover:text-text hover:bg-surface2/50 border border-transparent'
              }`}
            >
              <t.icon size={16} />
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setCoachOpen(o => !o)}
            className={`p-2 rounded-md text-sm transition-colors ${
              coachOpen
                ? 'bg-accent text-white shadow-sm'
                : 'text-text-muted hover:text-text hover:bg-surface2/50'
            }`}
            title="Coach"
          >
            <MessageSquare size={18} />
          </button>
          <button
            onClick={toggleTheme}
            className="p-2 rounded-md text-sm transition-colors text-text-muted hover:text-text hover:bg-surface2/50"
            title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          {isAdmin && (
            <button
              onClick={() => onTabChange('admin')}
              className={`p-2 rounded-md text-sm transition-colors ${
                activeTab === 'admin'
                  ? 'text-accent bg-surface2 border border-accent/20'
                  : 'text-text-muted hover:text-text hover:bg-surface2/50'
              }`}
              title="User Management"
            >
              <Users size={18} />
            </button>
          )}
          {canSettings && (
            <button
              onClick={() => onTabChange('settings')}
              className={`p-2 rounded-md text-sm transition-colors ${
                activeTab === 'settings'
                  ? 'text-accent bg-surface2 border border-accent/20'
                  : 'text-text-muted hover:text-text hover:bg-surface2/50'
              }`}
              title="Settings"
            >
              <Settings size={18} />
            </button>
          )}
          <div className="ml-2 pl-2 border-l border-border">
            <UserAvatar />
          </div>
        </div>
      </header>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden relative">
        <main className={`flex-1 overflow-y-auto p-4 md:p-6 ${coachOpen ? 'hidden md:block' : ''}`}>
          {children}
        </main>
        {coachOpen && (
          <CoachPanel onClose={() => setCoachOpen(false)} viewContext={viewContext} nutritionistContext={nutritionistContext} nutritionistSessionId={nutritionistSessionId} defaultTab={activeTab === 'nutrition' ? 'nutritionist' : 'coach'} />
        )}
      </div>

      {/* Version indicator */}
      <span className="hidden md:block fixed bottom-1 right-2 text-[10px] text-text-muted/40 select-none pointer-events-none z-50">
        v{__APP_VERSION__}
      </span>

      {/* Bottom nav - mobile */}
      <nav className="md:hidden relative flex border-t border-border bg-surface pb-[env(safe-area-inset-bottom)]">
        {([
          { key: 'dashboard' as const, label: 'Dashboard', icon: LayoutDashboard },
          { key: 'calendar' as const, label: 'Calendar', icon: CalendarDays },
          { key: 'nutrition' as const, label: 'Nutrition', icon: UtensilsCrossed },
        ]).map(t => (
          <button
            key={t.key}
            onClick={() => { onTabChange(t.key); setCoachOpen(false); setMoreOpen(false) }}
            className={`flex-1 flex flex-col items-center py-2 text-[10px] transition-colors ${
              activeTab === t.key && !coachOpen ? 'text-accent' : 'text-text-muted'
            }`}
          >
            <t.icon size={20} className="mb-1" strokeWidth={activeTab === t.key && !coachOpen ? 2.5 : 2} />
            <span>{t.label}</span>
          </button>
        ))}
        <button
          onClick={() => { setCoachOpen(o => !o); setMoreOpen(false) }}
          className={`flex-1 flex flex-col items-center py-2 text-[10px] ${
            coachOpen ? 'text-accent' : 'text-text-muted'
          }`}
        >
          <MessageSquare size={20} className="mb-1" strokeWidth={coachOpen ? 2.5 : 2} />
          <span>Coach</span>
        </button>
        <div className="flex-1" ref={moreRef}>
          <button
            onClick={() => setMoreOpen(o => !o)}
            className={`w-full flex flex-col items-center py-2 text-[10px] transition-colors ${
              moreOpen || isMoreActive ? 'text-accent' : 'text-text-muted'
            }`}
          >
            <MoreHorizontal size={20} className="mb-1" strokeWidth={moreOpen || isMoreActive ? 2.5 : 2} />
            <span>More</span>
          </button>
          {moreOpen && (
            <div className="absolute bottom-full right-0 mb-1 w-44 bg-surface border border-border rounded-lg shadow-lg z-50">
              <button
                onClick={() => { onTabChange('rides'); setCoachOpen(false); setMoreOpen(false) }}
                className={`w-full flex items-center gap-2 px-3 py-2.5 text-sm transition-colors rounded-t-lg ${
                  activeTab === 'rides' ? 'text-accent bg-surface2/50' : 'text-text-muted hover:text-text hover:bg-surface2/50'
                }`}
              >
                <Bike size={16} />
                <span>Rides</span>
              </button>
              <button
                onClick={() => { onTabChange('analysis'); setCoachOpen(false); setMoreOpen(false) }}
                className={`w-full flex items-center gap-2 px-3 py-2.5 text-sm transition-colors ${
                  activeTab === 'analysis' ? 'text-accent bg-surface2/50' : 'text-text-muted hover:text-text hover:bg-surface2/50'
                }`}
              >
                <TrendingUp size={16} />
                <span>Analysis</span>
              </button>
              <div className="border-t border-border my-1" />
              <button
                onClick={() => { toggleTheme(); setMoreOpen(false) }}
                className="w-full flex items-center gap-2 px-3 py-2.5 text-sm text-text-muted hover:text-text hover:bg-surface2/50 transition-colors"
              >
                {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
                <span>{theme === 'dark' ? 'Light Mode' : 'Dark Mode'}</span>
              </button>
              {isAdmin && (
                <button
                  onClick={() => { onTabChange('admin'); setCoachOpen(false); setMoreOpen(false) }}
                  className={`w-full flex items-center gap-2 px-3 py-2.5 text-sm transition-colors ${
                    activeTab === 'admin' ? 'text-accent bg-surface2/50' : 'text-text-muted hover:text-text hover:bg-surface2/50'
                  }`}
                >
                  <Users size={16} />
                  <span>Users</span>
                </button>
              )}
              {canSettings && (
                <button
                  onClick={() => { onTabChange('settings'); setCoachOpen(false); setMoreOpen(false) }}
                  className={`w-full flex items-center gap-2 px-3 py-2.5 text-sm transition-colors rounded-b-lg ${
                    activeTab === 'settings' ? 'text-accent bg-surface2/50' : 'text-text-muted hover:text-text hover:bg-surface2/50'
                  }`}
                >
                  <Settings size={16} />
                  <span>Settings</span>
                </button>
              )}
            </div>
          )}
        </div>
      </nav>
    </div>
  )
}
