/**
 * Centralized route table & breadcrumb metadata.
 *
 * This is the single source of truth for the app's URL scheme. It is consumed
 * by `App.tsx` (route definitions), `Layout.tsx` (nav links), and
 * `Breadcrumbs.tsx` (Phase 5).
 *
 * Conventions:
 *   - Resource paths use the path itself (`/rides/:id`).
 *   - Filters / view-state use search params (`?date=YYYY-MM-DD`).
 *   - Path is the canonical identifier; `label` powers nav text and
 *     breadcrumbs.
 */
import type { ComponentType } from 'react'
import {
  LayoutDashboard,
  Bike,
  CalendarDays,
  TrendingUp,
  UtensilsCrossed,
  Settings as SettingsIcon,
  Users,
} from 'lucide-react'

export type Role = 'admin' | 'readwrite' | 'read'

export interface RouteEntry {
  /** Path pattern, e.g. `/rides/:id`. Index route is `/`. */
  path: string
  /** Human-readable label used by nav links and static breadcrumbs. */
  label: string
  /** Optional icon for nav rendering. */
  icon?: ComponentType<{ size?: number; className?: string; strokeWidth?: number }>
  /** Path of the parent route (for breadcrumb chain). `null` for root. */
  parent?: string | null
  /** If set, only users with this role (or higher) can see/access. */
  requireRole?: Role
  /** Show in the primary header nav (desktop). */
  showInHeader?: boolean
  /** Show in the mobile bottom nav. */
  showInMobileNav?: boolean
  /** Show in the mobile "More" overflow menu. */
  showInMoreMenu?: boolean
  /** Show as a header icon (gear, users, etc.). */
  showAsHeaderIcon?: boolean
  /**
   * Static crumb resolver. Receives matched route params and returns the
   * label to render in the breadcrumb. When omitted, `label` is used.
   */
  crumb?: (params: Record<string, string | undefined>) => string
  /**
   * True when the crumb requires async data (ride title, meal description,
   * etc.). The breadcrumb component renders the static `crumb()` output as
   * a placeholder until the lookup resolves.
   */
  dynamicCrumb?: boolean
}

/**
 * Canonical route table.
 *
 * Order matters for nav rendering — primary tabs first.
 */
export const ROUTES: RouteEntry[] = [
  {
    path: '/',
    label: 'Dashboard',
    icon: LayoutDashboard,
    parent: null,
    showInHeader: true,
    showInMobileNav: true,
    crumb: () => 'Dashboard',
  },
  {
    path: '/rides',
    label: 'Rides',
    icon: Bike,
    parent: '/',
    showInHeader: true,
    showInMoreMenu: true,
    crumb: () => 'Rides',
  },
  {
    path: '/rides/:id',
    label: 'Ride',
    parent: '/rides',
    crumb: ({ id }) => (id ? `#${id}` : 'Ride'),
    dynamicCrumb: true,
  },
  {
    path: '/rides/by-date/:date',
    label: 'Ride',
    parent: '/rides',
    crumb: ({ date }) => date ?? 'Ride',
  },
  {
    path: '/workouts/:id',
    label: 'Workout',
    parent: '/calendar',
    crumb: ({ id }) => (id ? `#${id}` : 'Workout'),
    dynamicCrumb: true,
  },
  {
    path: '/calendar',
    label: 'Calendar',
    icon: CalendarDays,
    parent: '/',
    showInHeader: true,
    showInMobileNav: true,
    crumb: () => 'Calendar',
  },
  {
    path: '/analysis',
    label: 'Analysis',
    icon: TrendingUp,
    parent: '/',
    showInHeader: true,
    showInMoreMenu: true,
    crumb: () => 'Analysis',
  },
  {
    path: '/nutrition',
    label: 'Nutrition',
    icon: UtensilsCrossed,
    parent: '/',
    showInHeader: true,
    showInMobileNav: true,
    crumb: () => 'Nutrition',
  },
  {
    path: '/nutrition/week',
    label: 'Week',
    parent: '/nutrition',
    crumb: () => 'Week',
  },
  {
    path: '/nutrition/plan',
    label: 'Plan',
    parent: '/nutrition',
    crumb: () => 'Plan',
  },
  {
    path: '/nutrition/plan/:date',
    label: 'Plan Day',
    parent: '/nutrition/plan',
    crumb: ({ date }) => date ?? 'Day',
  },
  {
    path: '/nutrition/meals/:id',
    label: 'Meal',
    parent: '/nutrition',
    crumb: ({ id }) => (id ? `#${id}` : 'Meal'),
    dynamicCrumb: true,
  },
  {
    path: '/settings',
    label: 'Settings',
    icon: SettingsIcon,
    parent: '/',
    requireRole: 'read',
    showAsHeaderIcon: true,
    showInMoreMenu: true,
    crumb: () => 'Settings',
  },
  {
    path: '/admin',
    label: 'Users',
    icon: Users,
    parent: '/',
    requireRole: 'admin',
    showAsHeaderIcon: true,
    showInMoreMenu: true,
    crumb: () => 'Users',
  },
]

/** Get a route entry by exact path. */
export function findRoute(path: string): RouteEntry | undefined {
  return ROUTES.find(r => r.path === path)
}

/** Routes shown in the desktop header tabs. */
export const HEADER_ROUTES = ROUTES.filter(r => r.showInHeader)
/** Routes shown in the mobile bottom-nav. */
export const MOBILE_NAV_ROUTES = ROUTES.filter(r => r.showInMobileNav)
/** Routes shown in the mobile "More" menu. */
export const MORE_MENU_ROUTES = ROUTES.filter(r => r.showInMoreMenu)
/** Routes shown as header icons (right side of desktop nav). */
export const HEADER_ICON_ROUTES = ROUTES.filter(r => r.showAsHeaderIcon)

/**
 * Role hierarchy used for `requireRole` matching.
 * Higher index = more privileged.
 */
const ROLE_RANK: Record<Role, number> = { read: 1, readwrite: 2, admin: 3 }

/** Returns true if `actual` satisfies `required` (e.g. admin satisfies readwrite). */
export function roleSatisfies(actual: string | undefined | null, required: Role | undefined): boolean {
  if (!required) return true
  if (!actual || actual === 'none') return false
  const actualRank = ROLE_RANK[actual as Role]
  if (actualRank == null) return false
  return actualRank >= ROLE_RANK[required]
}
