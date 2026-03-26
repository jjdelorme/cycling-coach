import type { UnitSystem } from './units'

const KM_TO_MI = 0.621371
const M_TO_FT = 3.28084
const KG_TO_LBS = 2.20462

export function fmtDuration(seconds?: number | null): string {
  if (!seconds) return '--'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

export function fmtDistance(meters?: number | null, units: UnitSystem = 'imperial'): string {
  if (!meters) return '--'
  if (units === 'imperial') {
    const mi = (meters / 1000) * KM_TO_MI
    return mi >= 100 ? `${Math.round(mi)} mi` : `${mi.toFixed(1)} mi`
  }
  const km = meters / 1000
  return km >= 100 ? `${Math.round(km)} km` : `${km.toFixed(1)} km`
}

export function fmtDistanceKm(km?: number | null, units: UnitSystem = 'imperial'): string {
  if (!km) return '--'
  if (units === 'imperial') {
    const mi = km * KM_TO_MI
    return mi >= 100 ? `${Math.round(mi)} mi` : `${mi.toFixed(1)} mi`
  }
  return km >= 100 ? `${Math.round(km)} km` : `${km.toFixed(1)} km`
}

export function fmtElevation(meters?: number | null, units: UnitSystem = 'imperial'): string {
  if (!meters && meters !== 0) return '--'
  if (units === 'imperial') {
    return `${Math.round(meters * M_TO_FT).toLocaleString()} ft`
  }
  return `${Math.round(meters).toLocaleString()} m`
}

export function fmtWeight(kg?: number | null): string {
  if (!kg) return '--'
  const lbs = kg * KG_TO_LBS
  return `${kg.toFixed(1)} kg / ${lbs.toFixed(0)} lbs`
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
