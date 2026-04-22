import { useState, useEffect, useRef, useMemo } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import CoachPanel from './CoachPanel'
import UserAvatar from './UserAvatar'
import Breadcrumbs from './Breadcrumbs'
import { useTheme } from '../lib/theme'
import { useAuth } from '../lib/auth'
import { useNutritionistHandoff } from '../lib/nutritionist-handoff'
import { HEADER_ROUTES, MORE_MENU_ROUTES, roleSatisfies } from '../lib/routes'
import {
  LayoutDashboard,
  Bike,
  CalendarDays,
  UtensilsCrossed,
  MessageSquare,
  Sun,
  Moon,
  Users,
  Settings,
  MoreHorizontal,
} from 'lucide-react'

/**
 * Tab key — derived from the URL path's first segment. Retained so existing
 * call-sites (e.g. `CoachPanel`'s `viewContext`) continue to compile during
 * the gradual migration. Phase 6 will remove this in favor of pulling the
 * pathname directly from `useLocation()`.
 */
export type TabKey = 'dashboard' | 'rides' | 'calendar' | 'analysis' | 'nutrition' | 'settings' | 'admin'

export interface ViewContext {
  tab: TabKey
  rideId?: number
  rideDate?: string
  calendarDate?: string
}

/** Map a pathname onto the legacy TabKey for `viewContext`/active-state. */
function pathToTab(pathname: string): TabKey {
  const seg = pathname.split('/').filter(Boolean)[0]
  switch (seg) {
    case 'rides': return 'rides'
    case 'calendar': return 'calendar'
    case 'analysis': return 'analysis'
    case 'nutrition': return 'nutrition'
    case 'settings': return 'settings'
    case 'admin': return 'admin'
    case 'workouts': return 'rides' // workout detail nests under rides
    default: return 'dashboard'
  }
}

export default function Layout() {
  const [coachOpen, setCoachOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const moreRef = useRef<HTMLDivElement>(null)
  const { theme, toggle: toggleTheme } = useTheme()
  const { user } = useAuth()
  const location = useLocation()
  const handoff = useNutritionistHandoff()

  const activeTab = pathToTab(location.pathname)
  const isAdmin = roleSatisfies(user?.role, 'admin')
  const canSettings = roleSatisfies(user?.role, 'read')

  // Auto-open the coach panel when a nutritionist context or session is injected
  useEffect(() => {
    if (handoff.context || handoff.sessionId) setCoachOpen(true)
  }, [handoff.context, handoff.sessionId])

  // Close More menu on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) setMoreOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Reset transient panel state when the route changes.
  useEffect(() => {
    setMoreOpen(false)
    handoff.clear()
    // Intentionally only react to pathname changes; `handoff` is a stable ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname])

  /**
   * Build the legacy ViewContext for CoachPanel from URL.
   *
   * Phase 1 is intentionally minimal: the hook still receives a ViewContext
   * derived only from the path. Phase 2 will start populating `rideId`/
   * `rideDate` from URL params; Phase 6 will move this hook into CoachPanel
   * itself.
   */
  const viewContext = useMemo<ViewContext>(() => ({
    tab: activeTab,
  }), [activeTab])

  const isMoreActive =
    (['rides', 'analysis', 'settings', 'admin'] as TabKey[]).includes(activeTab) && !coachOpen

  // Helper: NavLink className builder for header tabs.
  const headerTabClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
      isActive
        ? 'bg-surface2 text-text border border-accent/20'
        : 'text-text-muted hover:text-text hover:bg-surface2/50 border border-transparent'
    }`

  // Helper: NavLink className builder for header icons.
  const headerIconClass = ({ isActive }: { isActive: boolean }) =>
    `p-2 rounded-md text-sm transition-colors ${
      isActive
        ? 'text-accent bg-surface2 border border-accent/20'
        : 'text-text-muted hover:text-text hover:bg-surface2/50'
    }`

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
          {HEADER_ROUTES.map(r => {
            // Header tabs are visible to anyone authenticated; gated routes
            // appear as icons on the right.
            if (r.requireRole) return null
            const Icon = r.icon
            return (
              <NavLink
                key={r.path}
                to={r.path}
                end={r.path === '/'}
                className={headerTabClass}
              >
                {Icon && <Icon size={16} />}
                {r.label}
              </NavLink>
            )
          })}
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
            <NavLink
              to="/admin"
              className={headerIconClass}
              title="User Management"
            >
              <Users size={18} />
            </NavLink>
          )}
          {canSettings && (
            <NavLink
              to="/settings"
              className={headerIconClass}
              title="Settings"
            >
              <Settings size={18} />
            </NavLink>
          )}
          <div className="ml-2 pl-2 border-l border-border">
            <UserAvatar />
          </div>
        </div>
      </header>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden relative">
        <main className={`flex-1 overflow-y-auto p-4 md:p-6 ${coachOpen ? 'hidden md:block' : ''}`}>
          <div className="hidden md:block mb-4">
            <Breadcrumbs />
          </div>
          <div className="md:hidden mb-3">
            <Breadcrumbs compact />
          </div>
          <Outlet />
        </main>
        {coachOpen && (
          <CoachPanel
            onClose={() => setCoachOpen(false)}
            viewContext={viewContext}
            nutritionistContext={handoff.context}
            nutritionistSessionId={handoff.sessionId}
            defaultTab={activeTab === 'nutrition' ? 'nutritionist' : 'coach'}
          />
        )}
      </div>

      {/* Version indicator */}
      <span className="hidden md:block fixed bottom-1 right-2 text-[10px] text-text-muted/40 select-none pointer-events-none z-50">
        v{__APP_VERSION__}
      </span>

      {/* Bottom nav - mobile */}
      <nav className="md:hidden relative flex border-t border-border bg-surface pb-[env(safe-area-inset-bottom)]">
        {([
          { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
          { to: '/calendar', label: 'Calendar', icon: CalendarDays, end: false },
          { to: '/nutrition', label: 'Nutrition', icon: UtensilsCrossed, end: false },
        ]).map(t => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.end}
            onClick={() => { setCoachOpen(false); setMoreOpen(false) }}
            className={({ isActive }) =>
              `flex-1 flex flex-col items-center py-2 text-[10px] transition-colors ${
                isActive && !coachOpen ? 'text-accent' : 'text-text-muted'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <t.icon size={20} className="mb-1" strokeWidth={isActive && !coachOpen ? 2.5 : 2} />
                <span>{t.label}</span>
              </>
            )}
          </NavLink>
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
              {/* Open routes (no role gate) */}
              {MORE_MENU_ROUTES.filter(r => !r.requireRole).map((r, idx, arr) => {
                const Icon = r.icon ?? Bike
                return (
                  <NavLink
                    key={r.path}
                    to={r.path}
                    end={r.path === '/'}
                    onClick={() => { setCoachOpen(false); setMoreOpen(false) }}
                    className={({ isActive }) =>
                      `w-full flex items-center gap-2 px-3 py-2.5 text-sm transition-colors ${
                        idx === 0 ? 'rounded-t-lg' : ''
                      } ${idx === arr.length - 1 ? '' : ''} ${
                        isActive ? 'text-accent bg-surface2/50' : 'text-text-muted hover:text-text hover:bg-surface2/50'
                      }`
                    }
                  >
                    <Icon size={16} />
                    <span>{r.label}</span>
                  </NavLink>
                )
              })}
              <div className="border-t border-border my-1" />
              <button
                onClick={() => { toggleTheme(); setMoreOpen(false) }}
                className="w-full flex items-center gap-2 px-3 py-2.5 text-sm text-text-muted hover:text-text hover:bg-surface2/50 transition-colors"
              >
                {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
                <span>{theme === 'dark' ? 'Light Mode' : 'Dark Mode'}</span>
              </button>
              {/* Role-gated routes */}
              {MORE_MENU_ROUTES.filter(r => r.requireRole && roleSatisfies(user?.role, r.requireRole)).map((r, idx, arr) => {
                const Icon = r.icon ?? Bike
                const isLast = idx === arr.length - 1
                return (
                  <NavLink
                    key={r.path}
                    to={r.path}
                    end={r.path === '/'}
                    onClick={() => { setCoachOpen(false); setMoreOpen(false) }}
                    className={({ isActive }) =>
                      `w-full flex items-center gap-2 px-3 py-2.5 text-sm transition-colors ${
                        isLast ? 'rounded-b-lg' : ''
                      } ${
                        isActive ? 'text-accent bg-surface2/50' : 'text-text-muted hover:text-text hover:bg-surface2/50'
                      }`
                    }
                  >
                    <Icon size={16} />
                    <span>{r.label}</span>
                  </NavLink>
                )
              })}
            </div>
          )}
        </div>
      </nav>
    </div>
  )
}
