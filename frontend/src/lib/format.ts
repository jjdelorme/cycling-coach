export function fmtDuration(seconds?: number | null): string {
  if (!seconds) return '--'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

export function fmtDistance(meters?: number | null): string {
  if (!meters) return '--'
  const km = meters / 1000
  return km >= 100 ? `${Math.round(km)} km` : `${km.toFixed(1)} km`
}

export function fmtTime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

export function timeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export function zoneColor(pct: number, alpha = 1): string {
  if (pct < 0.56) return `rgba(126, 200, 227, ${alpha})`
  if (pct < 0.76) return `rgba(0, 212, 170, ${alpha})`
  if (pct < 0.91) return `rgba(245, 197, 24, ${alpha})`
  if (pct < 1.06) return `rgba(232, 145, 58, ${alpha})`
  if (pct < 1.21) return `rgba(233, 69, 96, ${alpha})`
  return `rgba(155, 89, 182, ${alpha})`
}

export function zoneLabel(pct: number): string {
  if (pct < 0.56) return 'Z1'
  if (pct < 0.76) return 'Z2'
  if (pct < 0.91) return 'Z3'
  if (pct < 1.06) return 'Z4'
  if (pct < 1.21) return 'Z5'
  return 'Z6'
}
