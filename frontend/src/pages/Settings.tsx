import { useState, useEffect, useRef, useCallback } from 'react'
import { useSettings, useUpdateSetting, useResetSettings, useSyncOverview } from '../hooks/useApi'
import { startSync, fetchSyncStatus } from '../lib/api'
import { timeAgo } from '../lib/format'
import { useQueryClient } from '@tanstack/react-query'

const SETTING_CARDS: { key: string; title: string; hint: string }[] = [
  {
    key: 'athlete_profile',
    title: 'Athlete Profile',
    hint: 'Background info about the athlete: age, weight, FTP, goals, strengths, limiters.',
  },
  {
    key: 'coaching_principles',
    title: 'Coaching Principles',
    hint: 'Training philosophy: periodization approach, volume guidelines, recovery rules.',
  },
  {
    key: 'coach_role',
    title: 'Coach Role',
    hint: 'How the AI coach should behave: tone, expertise level, communication style.',
  },
  {
    key: 'plan_management',
    title: 'Plan Management',
    hint: 'Rules for creating and adjusting training plans: workout structure, progression logic.',
  },
]

export default function Settings() {
  const { data: settings, isLoading } = useSettings()
  const { data: syncOverview } = useSyncOverview()
  const updateSetting = useUpdateSetting()
  const resetSettings = useResetSettings()
  const queryClient = useQueryClient()

  const [form, setForm] = useState<Record<string, string>>({})
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saved' | 'failed'>('idle')
  const [showApiKey, setShowApiKey] = useState(false)

  // Sync state
  const [syncing, setSyncing] = useState(false)
  const [syncProgress, setSyncProgress] = useState(0)
  const [syncLogs, setSyncLogs] = useState<string[]>([])
  const [syncResult, setSyncResult] = useState<string | null>(null)
  const logRef = useRef<HTMLDivElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  // Populate form when settings load
  useEffect(() => {
    if (settings) {
      setForm({
        athlete_profile: settings.athlete_profile ?? '',
        coaching_principles: settings.coaching_principles ?? '',
        coach_role: settings.coach_role ?? '',
        plan_management: settings.plan_management ?? '',
        intervals_icu_api_key: settings.intervals_icu_api_key ?? '',
        intervals_icu_athlete_id: settings.intervals_icu_athlete_id ?? '',
        units: settings.units ?? 'imperial',
      })
    }
  }, [settings])

  // Auto-scroll logs
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [syncLogs])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
      if (wsRef.current) wsRef.current.close()
    }
  }, [])

  const handleChange = (key: string, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }))
    setSaveStatus('idle')
  }

  const handleSave = async () => {
    const keys = [
      'athlete_profile',
      'coaching_principles',
      'coach_role',
      'plan_management',
      'intervals_icu_api_key',
      'intervals_icu_athlete_id',
      'units',
    ]
    try {
      for (const key of keys) {
        await updateSetting.mutateAsync({ key, value: form[key] ?? '' })
      }
      setSaveStatus('saved')
    } catch {
      setSaveStatus('failed')
    }
  }

  const handleReset = async () => {
    try {
      await resetSettings.mutateAsync()
      setSaveStatus('idle')
    } catch {
      setSaveStatus('failed')
    }
  }

  const handleSyncStatus = useCallback(
    (status: {
      status: string
      phase?: string
      detail?: string
      rides_downloaded?: number
      rides_skipped?: number
      workouts_uploaded?: number
      workouts_skipped?: number
    }) => {
      if (status.detail) {
        setSyncLogs((prev) => [...prev, status.detail!])
      }

      // Estimate progress from phase
      if (status.phase === 'downloading_rides') setSyncProgress(30)
      else if (status.phase === 'ingesting') setSyncProgress(60)
      else if (status.phase === 'uploading_workouts') setSyncProgress(80)

      if (status.status === 'completed' || status.status === 'failed') {
        setSyncProgress(100)
        setSyncing(false)
        if (pollRef.current) clearInterval(pollRef.current)
        if (wsRef.current) wsRef.current.close()

        if (status.status === 'completed') {
          const rides = status.rides_downloaded ?? 0
          const workouts = status.workouts_uploaded ?? 0
          setSyncResult(`Done — ${rides} rides, ${workouts} workouts synced`)
        } else {
          setSyncResult(status.detail ?? 'Sync failed')
        }

        queryClient.invalidateQueries({ queryKey: ['sync-overview'] })
        queryClient.invalidateQueries({ queryKey: ['rides'] })
        queryClient.invalidateQueries({ queryKey: ['pmc'] })
      }
    },
    [queryClient],
  )

  const handleSync = async () => {
    setSyncing(true)
    setSyncProgress(5)
    setSyncLogs([])
    setSyncResult(null)

    try {
      const { sync_id, ws_url } = await startSync()

      // Try WebSocket first
      let wsConnected = false
      try {
        const ws = new WebSocket(ws_url)
        wsRef.current = ws

        ws.onopen = () => {
          wsConnected = true
        }

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            handleSyncStatus(data)
          } catch {
            setSyncLogs((prev) => [...prev, event.data])
          }
        }

        ws.onerror = () => {
          if (!wsConnected) {
            // Fall back to polling
            startPolling(sync_id)
          }
        }

        ws.onclose = () => {
          wsRef.current = null
        }
      } catch {
        // WebSocket not available, fall back to polling
        startPolling(sync_id)
      }

      // If WS doesn't connect quickly, fall back to polling
      setTimeout(() => {
        if (!wsConnected) {
          startPolling(sync_id)
        }
      }, 2000)
    } catch {
      setSyncing(false)
      setSyncResult('Failed to start sync')
      setSyncProgress(0)
    }
  }

  const startPolling = (syncId: string) => {
    if (pollRef.current) return // already polling
    pollRef.current = setInterval(async () => {
      try {
        const status = await fetchSyncStatus(syncId)
        handleSyncStatus(status)
      } catch {
        // ignore polling errors
      }
    }, 2000)
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="text-text-muted">Loading settings...</span>
      </div>
    )
  }

  return (
    <div className="space-y-8 max-w-4xl mx-auto p-4">
      {/* Display Units */}
      <section>
        <h3 className="text-xl font-semibold text-text mb-1">Display</h3>
        <p className="text-text-muted text-sm mb-4">
          Choose how distances and elevation are displayed throughout the app.
        </p>
        <div className="bg-surface rounded-lg border border-border p-4">
          <div className="flex items-center gap-4">
            <span className="text-text text-sm font-medium">Units</span>
            <div className="flex rounded-md overflow-hidden border border-border">
              <button
                onClick={() => handleChange('units', 'imperial')}
                className={`px-4 py-1.5 text-sm font-medium transition-colors ${
                  (form.units ?? 'imperial') === 'imperial'
                    ? 'bg-accent text-white'
                    : 'bg-surface2 text-text-muted hover:text-text'
                }`}
              >
                Imperial (mi / ft)
              </button>
              <button
                onClick={() => handleChange('units', 'metric')}
                className={`px-4 py-1.5 text-sm font-medium transition-colors ${
                  form.units === 'metric'
                    ? 'bg-accent text-white'
                    : 'bg-surface2 text-text-muted hover:text-text'
                }`}
              >
                Metric (km / m)
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Coach Settings */}
      <section>
        <h3 className="text-xl font-semibold text-text mb-1">Coach Settings</h3>
        <p className="text-text-muted text-sm mb-4">
          Customize how the AI coach understands you and builds your training plans.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {SETTING_CARDS.map((card) => (
            <div key={card.key} className="bg-surface rounded-lg border border-border p-4">
              <h4 className="text-text font-medium mb-1">{card.title}</h4>
              <p className="text-text-muted text-xs mb-2">{card.hint}</p>
              <textarea
                className="w-full bg-surface2 text-text border border-border rounded px-3 py-2 text-sm resize-y min-h-[100px] focus:outline-none focus:border-accent"
                value={form[card.key] ?? ''}
                onChange={(e) => handleChange(card.key, e.target.value)}
                rows={5}
              />
            </div>
          ))}
        </div>

      </section>

      {/* Integrations */}
      <section>
        <h3 className="text-xl font-semibold text-text mb-4">Integrations</h3>

        <div className="bg-surface rounded-lg border border-border p-4 space-y-4">
          <h4 className="text-text font-medium">intervals.icu</h4>

          {/* API Key */}
          <div>
            <label className="block text-text-muted text-xs mb-1">API Key</label>
            <div className="relative">
              <input
                type={showApiKey ? 'text' : 'password'}
                className="w-full bg-surface2 text-text border border-border rounded px-3 py-2 pr-10 text-sm focus:outline-none focus:border-accent"
                value={form.intervals_icu_api_key ?? ''}
                onChange={(e) => handleChange('intervals_icu_api_key', e.target.value)}
                placeholder="Enter your intervals.icu API key"
              />
              <button
                type="button"
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted hover:text-text"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                  {showApiKey && <line x1="1" y1="1" x2="23" y2="23" />}
                </svg>
              </button>
            </div>
          </div>

          {/* Athlete ID */}
          <div>
            <label className="block text-text-muted text-xs mb-1">Athlete ID</label>
            <input
              type="text"
              className="w-full bg-surface2 text-text border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent"
              value={form.intervals_icu_athlete_id ?? ''}
              onChange={(e) => handleChange('intervals_icu_athlete_id', e.target.value)}
              placeholder="e.g. i12345"
            />
          </div>

          {/* Sync */}
          <div className="border-t border-border pt-4 space-y-3">
            <div className="flex items-center gap-3">
              <button
                onClick={handleSync}
                disabled={syncing}
                className="px-4 py-2 bg-yellow text-bg rounded text-sm font-medium hover:opacity-90 disabled:opacity-50"
              >
                {syncing ? 'Syncing...' : 'Sync Now'}
              </button>

              {syncOverview?.last_sync?.completed_at && (
                <span className="text-text-muted text-xs">
                  Last sync: {timeAgo(new Date(syncOverview.last_sync.completed_at))}
                </span>
              )}
            </div>

            {/* Progress bar */}
            {syncing && (
              <div className="w-full bg-surface2 rounded-full overflow-hidden" style={{ height: 6 }}>
                <div
                  className="bg-accent h-full transition-all duration-300"
                  style={{ width: `${syncProgress}%` }}
                />
              </div>
            )}

            {/* Sync logs */}
            {syncLogs.length > 0 && (
              <div
                ref={logRef}
                className="bg-surface2 rounded border border-border p-3 text-xs text-text-muted font-mono max-h-48 overflow-y-auto"
              >
                {syncLogs.map((line, i) => (
                  <div key={i}>{line}</div>
                ))}
              </div>
            )}

            {/* Sync result */}
            {syncResult && (
              <p
                className={
                  syncResult.startsWith('Done')
                    ? 'text-green text-sm'
                    : 'text-red-400 text-sm'
                }
              >
                {syncResult}
              </p>
            )}
          </div>
        </div>
      </section>

      {/* Save / Reset */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={updateSetting.isPending}
          className="px-4 py-2 bg-accent text-white rounded text-sm font-medium hover:opacity-90 disabled:opacity-50"
        >
          {updateSetting.isPending ? 'Saving...' : 'Save Settings'}
        </button>
        <button
          onClick={handleReset}
          disabled={resetSettings.isPending}
          className="px-4 py-2 bg-surface2 text-text border border-border rounded text-sm font-medium hover:opacity-90 disabled:opacity-50"
        >
          {resetSettings.isPending ? 'Resetting...' : 'Reset to Defaults'}
        </button>
        {saveStatus === 'saved' && (
          <span className="text-green text-sm">Saved!</span>
        )}
        {saveStatus === 'failed' && (
          <span className="text-red-400 text-sm">Save failed</span>
        )}
      </div>
    </div>
  )
}
