import { Link, matchPath, useLocation } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { ROUTES, findRoute, type RouteEntry } from '../lib/routes'
import { useRide, useWorkoutDetail, useMeal } from '../hooks/useApi'

interface Crumb {
  /** URL the crumb links to (last crumb is rendered as plain text). */
  to: string
  /** Visible label. */
  label: string
  /** Path pattern (used to look up dynamic resolvers). */
  path: string
  /** Matched URL params. */
  params: Record<string, string | undefined>
}

/**
 * Find the longest matching RouteEntry for a pathname. Falls back to the leaf
 * pattern if no parameterized route matches.
 */
function matchRouteEntry(pathname: string): { entry: RouteEntry; params: Record<string, string | undefined> } | null {
  for (const entry of ROUTES) {
    const m = matchPath({ path: entry.path, end: true }, pathname)
    if (m) return { entry, params: m.params as Record<string, string | undefined> }
  }
  return null
}

/**
 * Walk the parent chain of a RouteEntry, building the breadcrumb list from
 * root to leaf. Each ancestor reuses its static crumb label (parents are
 * rendered with the URL of their pattern, since the user can't deep-link
 * to "/rides/:id" without an id — but ancestors are always concrete).
 */
function buildChain(leaf: RouteEntry, leafParams: Record<string, string | undefined>): Crumb[] {
  const chain: Crumb[] = []
  let cursor: RouteEntry | undefined = leaf
  let cursorParams = leafParams
  while (cursor) {
    chain.unshift({
      to: cursor.path,
      label: cursor.crumb ? cursor.crumb(cursorParams) : cursor.label,
      path: cursor.path,
      params: cursorParams,
    })
    if (cursor.parent == null) break
    const parent: RouteEntry | undefined = findRoute(cursor.parent)
    if (!parent) break
    cursor = parent
    cursorParams = {}
  }
  return chain
}

/**
 * Resolve a dynamic crumb (ride title, workout name, meal description) for
 * the leaf when its route opts in via `dynamicCrumb`. Returns the override
 * label or `null` while the lookup is pending.
 */
function useDynamicCrumb(path: string, params: Record<string, string | undefined>): string | null {
  const ride = useRide(path === '/rides/:id' && params.id ? Number(params.id) : null)
  const workout = useWorkoutDetail(path === '/workouts/:id' && params.id ? Number(params.id) : null)
  const meal = useMeal(path === '/nutrition/meals/:id' && params.id ? Number(params.id) : null)

  if (path === '/rides/:id') return ride.data?.title ?? null
  if (path === '/workouts/:id') return workout.data?.name ?? null
  if (path === '/nutrition/meals/:id') return meal.data?.description ?? null
  return null
}

interface Props {
  compact?: boolean
}

export default function Breadcrumbs({ compact = false }: Props) {
  const location = useLocation()
  const matched = matchRouteEntry(location.pathname)

  // Always call hooks (Rules of Hooks) — pass dummy values when there's no match.
  const leafPath = matched?.entry.path ?? ''
  const leafParams = matched?.params ?? {}
  const dynamicLabel = useDynamicCrumb(leafPath, leafParams)

  if (!matched) return null
  // Hide on root.
  if (matched.entry.path === '/') return null

  const chain = buildChain(matched.entry, matched.params)
  if (chain.length <= 1) return null

  // Apply the dynamic override (when available) to the leaf crumb.
  if (dynamicLabel && chain.length > 0) {
    chain[chain.length - 1] = { ...chain[chain.length - 1], label: dynamicLabel }
  }

  const sizeText = compact ? 'text-[11px]' : 'text-xs'
  const sizeChevron = compact ? 12 : 14

  return (
    <nav aria-label="breadcrumb" className={`${sizeText} text-text-muted`}>
      <ol className={`flex items-center gap-1 ${compact ? 'overflow-hidden whitespace-nowrap' : ''}`}>
        {chain.map((c, idx) => {
          const isLast = idx === chain.length - 1
          return (
            <li key={`${c.path}-${idx}`} className={`flex items-center gap-1 ${compact && !isLast ? 'shrink-0' : ''} ${compact && isLast ? 'truncate min-w-0' : ''}`}>
              {idx > 0 && <ChevronRight size={sizeChevron} className="opacity-50 shrink-0" />}
              {isLast ? (
                <span className={`font-medium text-text ${compact ? 'truncate' : ''}`} aria-current="page">
                  {c.label}
                </span>
              ) : (
                <Link to={c.to} className="hover:text-accent transition-colors">
                  {c.label}
                </Link>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
