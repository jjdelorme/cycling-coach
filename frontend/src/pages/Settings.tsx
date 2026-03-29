import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import {
  useSettings,
  useUpdateSetting,
  useResetSettings,
  useSyncOverview,
  useAthleteSettings,
  useUpdateAthleteSetting,
} from '../hooks/useApi'
import { startSync, fetchSyncStatus, fetchVersion } from '../lib/api'
import { timeAgo } from '../lib/format'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTheme } from '../lib/theme'
import { useAuth } from '../lib/auth'
import { 
  User, 
  Bot, 
  Settings as SettingsIcon, 
  Monitor, 
  Heart, 
  Cpu, 
  Cloud,
  Eye,
  EyeOff,
  RefreshCw,
  Trash2,
  Info,
  Sun,
  Moon
} from 'lucide-react'

type Tab = 'athlete' | 'coach' | 'system'

const SETTING_CARDS: { key: string; title: string; hint: string; icon: any }[] = [
  {
    key: 'athlete_profile',
    title: 'Athlete Profile',
    hint: 'Age, weight, FTP, goals, strengths, and limiters.',
    icon: User
  },
  {
    key: 'coaching_principles',
    title: 'Coaching Principles',
    hint: 'Training philosophy, volume, and recovery rules.',
    icon: Heart
  },
  {
    key: 'coach_role',
    title: 'Coach Role',
    hint: 'Tone, expertise level, and communication style.',
    icon: Bot
  },
  {
    key: 'plan_management',
    title: 'Plan Management',
    hint: 'Workout structure and progression logic.',
    icon: SettingsIcon
  },
]

export default function Settings() {
  const { theme, toggle: toggleTheme } = useTheme()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const isReadOnly = user?.role === 'read'

  const [activeTab, setActiveTab] = useState<Tab>('athlete')

  const { data: settings, isLoading } = useSettings()
  const { data: syncOverview } = useSyncOverview()
  const updateSetting = useUpdateSetting()
  const resetSettings = useResetSettings()
  const queryClient = useQueryClient()

  // Version info
  const { data: backendVersion } = useQuery({
    queryKey: ['version'],
    queryFn: fetchVersion,
    staleTime: Infinity,
  })

  // Athlete settings
  const { data: athleteSettings } = useAthleteSettings()
  const updateAthleteSetting = useUpdateAthleteSetting()
  const [athleteForm, setAthleteForm] = useState<Record<string, string>>({})
  const [athleteSaveStatus, setAthleteSaveStatus] = useState<'idle' | 'saved' | 'failed'>('idle')

  const [form, setForm] = useState<Record<string, string>>({})
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saved' | 'failed'>('idle')
  const [showApiKey, setShowApiKey] = useState(false)
  const [showGeminiKey, setShowGeminiKey] = useState(false)

  // Sync state
  const [syncing, setSyncing] = useState(false)
  const [syncProgress, setSyncProgress] = useState(0)
  const [syncLogs, setSyncLogs] = useState<string[]>([])
  const [syncResult, setSyncResult] = useState<string | null>(null)
  const logRef = useRef<HTMLDivElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  // Populate athlete form
  useEffect(() => {
    if (athleteSettings) {
      setAthleteForm({ ...athleteSettings })
    }
  }, [athleteSettings])

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
        gemini_model: settings.gemini_model ?? '',
        gcp_location: settings.gcp_location ?? '',
        gemini_api_key: settings.gemini_api_key ?? '',
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

  const handleSaveGeneral = async () => {
    try {
      await updateSetting.mutateAsync({ key: 'units', value: form.units ?? 'imperial' })
      for (const [key, value] of Object.entries(athleteForm)) {
        await updateAthleteSetting.mutateAsync({ key, value })
      }
      setAthleteSaveStatus('saved')
      setTimeout(() => setAthleteSaveStatus('idle'), 3000)
    } catch {
      setAthleteSaveStatus('failed')
    }
  }

  const handleSaveCoach = async () => {
    const keys = ['athlete_profile', 'coaching_principles', 'coach_role', 'plan_management']
    try {
      for (const key of keys) {
        await updateSetting.mutateAsync({ key, value: form[key] ?? '' })
      }
      setSaveStatus('saved')
      setTimeout(() => setSaveStatus('idle'), 3000)
    } catch {
      setSaveStatus('failed')
    }
  }

  const handleSaveSystem = async () => {
    const keys = [
      'intervals_icu_api_key',
      'intervals_icu_athlete_id',
      'gemini_model',
      'gcp_location',
      'gemini_api_key',
    ]
    try {
      for (const key of keys) {
        await updateSetting.mutateAsync({ key, value: form[key] ?? '' })
      }
      setSaveStatus('saved')
      setTimeout(() => setSaveStatus('idle'), 3000)
    } catch {
      setSaveStatus('failed')
    }
  }

  const handleReset = async () => {
    if (!confirm('Are you sure you want to reset all coaching settings to defaults? This cannot be undone.')) return
    try {
      await resetSettings.mutateAsync()
      setSaveStatus('idle')
      setActiveTab('athlete')
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
      let wsConnected = false
      try {
        const ws = new WebSocket(ws_url)
        wsRef.current = ws
        ws.onopen = () => { wsConnected = true }
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            handleSyncStatus(data)
          } catch {
            setSyncLogs((prev) => [...prev, event.data])
          }
        }
        ws.onerror = () => { if (!wsConnected) startPolling(sync_id) }
        ws.onclose = () => { wsRef.current = null }
      } catch {
        startPolling(sync_id)
      }
      setTimeout(() => { if (!wsConnected) startPolling(sync_id) }, 2000)
    } catch {
      setSyncing(false)
      setSyncResult('Failed to start sync')
      setSyncProgress(0)
    }
  }

  const startPolling = (syncId: string) => {
    if (pollRef.current) return
    pollRef.current = setInterval(async () => {
      try {
        const status = await fetchSyncStatus(syncId)
        handleSyncStatus(status)
      } catch { /* ignore */ }
    }, 2000)
  }

  const tabs = useMemo(() => {
    const baseTabs: { key: Tab; label: string; icon: any }[] = [
      { key: 'athlete', label: 'Athlete', icon: User },
      { key: 'coach', label: 'Coach', icon: Bot },
    ]
    if (isAdmin) baseTabs.push({ key: 'system', label: 'System', icon: Cpu })
    return baseTabs
  }, [isAdmin])

  if (isLoading) {
    return <div className="p-6 text-text-muted animate-pulse">Loading settings...</div>
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto p-4 pb-12">
      <h1 className="text-2xl font-bold text-text">Settings</h1>

      {/* Tabs Header */}
      <div className="flex items-center border-b border-border">
        <div className="flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-5 py-3 text-sm font-bold uppercase tracking-wider rounded-t-xl transition-all ${
                activeTab === tab.key
                  ? 'bg-surface text-accent border-b-2 border-accent'
                  : 'text-text-muted hover:text-text hover:bg-surface/50'
              }`}
            >
              <tab.icon size={16} />
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-6">
        {/* Athlete Tab */}
        {activeTab === 'athlete' && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
            {/* Display Units */}
            <section className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm">
              <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center gap-2">
                <Monitor size={18} className="text-blue" />
                <h3 className="text-sm font-bold text-text uppercase tracking-wider">Display Settings</h3>
              </div>
              <div className="p-6 space-y-6">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <p className="text-sm font-bold text-text mb-1">Measurement Units</p>
                    <p className="text-xs text-text-muted">Choose how distance and elevation are displayed.</p>
                  </div>
                  <div className="flex bg-surface-low rounded-lg p-1 border border-border">
                    <button
                      onClick={() => !isReadOnly && handleChange('units', 'imperial')}
                      className={`px-4 py-2 text-xs font-bold rounded-md transition-all ${
                        (form.units ?? 'imperial') === 'imperial'
                          ? 'bg-accent text-white shadow-md'
                          : 'text-text-muted hover:text-text'
                      } ${isReadOnly ? 'cursor-not-allowed' : ''}`}
                    >
                      IMPERIAL (mi / ft)
                    </button>
                    <button
                      onClick={() => !isReadOnly && handleChange('units', 'metric')}
                      className={`px-4 py-2 text-xs font-bold rounded-md transition-all ${
                        form.units === 'metric'
                          ? 'bg-accent text-white shadow-md'
                          : 'text-text-muted hover:text-text'
                      } ${isReadOnly ? 'cursor-not-allowed' : ''}`}
                    >
                      METRIC (km / m)
                    </button>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-6 border-t border-border/50">
                  <div>
                    <p className="text-sm font-bold text-text mb-1">Visual Theme</p>
                    <p className="text-xs text-text-muted">Switch between dark and light modes.</p>
                  </div>
                  <div className="flex bg-surface-low rounded-lg p-1 border border-border">
                    <button
                      onClick={() => theme !== 'dark' && toggleTheme()}
                      className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-md transition-all ${
                        theme === 'dark' ? 'bg-accent text-white shadow-md' : 'text-text-muted hover:text-text'
                      }`}
                    >
                      <Moon size={14} /> DARK
                    </button>
                    <button
                      onClick={() => theme !== 'light' && toggleTheme()}
                      className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-md transition-all ${
                        theme === 'light' ? 'bg-accent text-white shadow-md' : 'text-text-muted hover:text-text'
                      }`}
                    >
                      <Sun size={14} /> LIGHT
                    </button>
                  </div>
                </div>
              </div>
            </section>

            {/* Physiological Settings */}
            <section className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm">
              <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center gap-2">
                <Heart size={18} className="text-red" />
                <h3 className="text-sm font-bold text-text uppercase tracking-wider">Physiological Profile</h3>
              </div>
              <div className="p-6">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                  {[
                    { key: 'lthr', label: 'LTHR', unit: 'bpm', hint: 'Lactate threshold heart rate' },
                    { key: 'max_hr', label: 'Max HR', unit: 'bpm', hint: 'Maximum heart rate' },
                    { key: 'resting_hr', label: 'Resting HR', unit: 'bpm', hint: 'Resting heart rate' },
                    { key: 'ftp', label: 'FTP', unit: 'Watts', hint: 'Functional threshold power' },
                    { key: 'weight_kg', label: 'Weight', unit: 'kg', hint: 'Body weight' },
                    { key: 'age', label: 'Age', unit: 'yrs', hint: 'Current age' },
                  ].map((field) => (
                    <div key={field.key} className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <label className="text-[10px] font-bold text-text-muted uppercase tracking-widest">{field.label}</label>
                        <span className="text-[10px] font-medium text-text-muted/60">{field.unit}</span>
                      </div>
                      <input
                        type="number"
                        disabled={isReadOnly}
                        className="w-full bg-surface-low text-text border border-border rounded-lg px-3 py-2.5 text-sm font-medium focus:outline-none focus:border-accent disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        value={athleteForm[field.key] ?? ''}
                        onChange={(e) => {
                          setAthleteForm((prev) => ({ ...prev, [field.key]: e.target.value }))
                          setAthleteSaveStatus('idle')
                        }}
                      />
                    </div>
                  ))}
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-widest">Gender</label>
                    <select
                      disabled={isReadOnly}
                      className="w-full bg-surface-low text-text border border-border rounded-lg px-3 py-2.5 text-sm font-medium focus:outline-none focus:border-accent disabled:opacity-50 disabled:cursor-not-allowed transition-colors appearance-none"
                      value={athleteForm.gender ?? 'male'}
                      onChange={(e) => {
                        setAthleteForm((prev) => ({ ...prev, gender: e.target.value }))
                        setAthleteSaveStatus('idle')
                      }}
                    >
                      <option value="male">Male</option>
                      <option value="female">Female</option>
                    </select>
                  </div>
                </div>

                {!isReadOnly && (
                  <div className="mt-8 pt-6 border-t border-border flex items-center gap-4">
                    <button
                      onClick={handleSaveGeneral}
                      disabled={updateAthleteSetting.isPending || updateSetting.isPending}
                      className="px-6 py-2.5 bg-accent text-white rounded-lg text-xs font-bold uppercase tracking-widest hover:opacity-90 disabled:opacity-50 transition-all shadow-lg shadow-accent/20 flex items-center gap-2"
                    >
                      {updateAthleteSetting.isPending || updateSetting.isPending ? <RefreshCw size={14} className="animate-spin" /> : 'Save Profile'}
                    </button>
                    {athleteSaveStatus === 'saved' && (
                      <span className="text-green text-xs font-bold animate-in fade-in zoom-in duration-300">✓ UPDATED SUCCESSFULLY</span>
                    )}
                    {athleteSaveStatus === 'failed' && (
                      <span className="text-red text-xs font-bold animate-in shake duration-300">✗ ERROR SAVING</span>
                    )}
                  </div>
                )}
              </div>
            </section>
          </div>
        )}

        {/* Coach Tab */}
        {activeTab === 'coach' && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {SETTING_CARDS.map((card) => (
                <section key={card.key} className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm flex flex-col">
                  <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center gap-3">
                    <card.icon size={18} className="text-accent" />
                    <div>
                      <h3 className="text-xs font-bold text-text uppercase tracking-wider">{card.title}</h3>
                      <p className="text-[10px] text-text-muted mt-0.5">{card.hint}</p>
                    </div>
                  </div>
                  <div className="p-4 flex-1">
                    <textarea
                      disabled={isReadOnly}
                      className="w-full h-full bg-surface-low text-text border border-border rounded-lg px-4 py-3 text-sm focus:outline-none focus:border-accent disabled:opacity-50 disabled:cursor-not-allowed transition-all min-h-[160px] leading-relaxed"
                      value={form[card.key] ?? ''}
                      onChange={(e) => handleChange(card.key, e.target.value)}
                    />
                  </div>
                </section>
              ))}
            </div>

            {!isReadOnly && (
              <div className="pt-2 flex items-center gap-4">
                <button
                  onClick={handleSaveCoach}
                  disabled={updateSetting.isPending}
                  className="px-8 py-3 bg-accent text-white rounded-lg text-xs font-bold uppercase tracking-widest hover:opacity-90 disabled:opacity-50 transition-all shadow-lg shadow-accent/20"
                >
                  {updateSetting.isPending ? 'Processing...' : 'Save Coaching Settings'}
                </button>
                {saveStatus === 'saved' && (
                  <span className="text-green text-xs font-bold animate-in fade-in zoom-in duration-300">✓ SAVED SUCCESSFULLY</span>
                )}
                {saveStatus === 'failed' && (
                  <span className="text-red text-xs font-bold animate-in shake duration-300">✗ SAVE FAILED</span>
                )}
              </div>
            )}
          </div>
        )}

        {/* System Tab */}
        {activeTab === 'system' && isAdmin && (
          <div className="space-y-6 animate-in fade-in slide-in-from-bottom-2 duration-300">
            {/* Gemini AI */}
            <section className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm">
              <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center gap-2">
                <Cloud size={18} className="text-blue" />
                <h3 className="text-sm font-bold text-text uppercase tracking-wider">Gemini AI Engine</h3>
              </div>
              <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-text-muted uppercase tracking-widest">Model</label>
                  <input
                    type="text"
                    className="w-full bg-surface-low text-text border border-border rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-accent transition-colors"
                    value={form.gemini_model ?? ''}
                    onChange={(e) => handleChange('gemini_model', e.target.value)}
                    placeholder="gemini-2.0-flash"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-[10px] font-bold text-text-muted uppercase tracking-widest">Region</label>
                  <input
                    type="text"
                    className="w-full bg-surface-low text-text border border-border rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-accent transition-colors"
                    value={form.gcp_location ?? ''}
                    onChange={(e) => handleChange('gcp_location', e.target.value)}
                    placeholder="us-central1"
                  />
                </div>
                <div className="md:col-span-2 space-y-1.5">
                  <label className="text-[10px] font-bold text-text-muted uppercase tracking-widest">API Key (Optional)</label>
                  <div className="relative">
                    <input
                      type={showGeminiKey ? 'text' : 'password'}
                      className="w-full bg-surface-low text-text border border-border rounded-lg px-3 py-2.5 pr-10 text-sm focus:outline-none focus:border-accent transition-colors"
                      value={form.gemini_api_key ?? ''}
                      onChange={(e) => handleChange('gemini_api_key', e.target.value)}
                      placeholder="Using Application Default Credentials"
                    />
                    <button
                      type="button"
                      onClick={() => setShowGeminiKey(!showGeminiKey)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text"
                    >
                      {showGeminiKey ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>
              </div>
            </section>

            {/* Integrations */}
            <section className="bg-surface rounded-xl border border-border overflow-hidden shadow-sm">
              <div className="px-5 py-4 border-b border-border bg-surface-low flex items-center gap-2">
                <RefreshCw size={18} className="text-yellow" />
                <h3 className="text-sm font-bold text-text uppercase tracking-wider">Intervals.icu Sync</h3>
              </div>
              <div className="p-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-widest">API Key</label>
                    <div className="relative">
                      <input
                        type={showApiKey ? 'text' : 'password'}
                        className="w-full bg-surface-low text-text border border-border rounded-lg px-3 py-2.5 pr-10 text-sm focus:outline-none focus:border-accent transition-colors"
                        value={form.intervals_icu_api_key ?? ''}
                        onChange={(e) => handleChange('intervals_icu_api_key', e.target.value)}
                        placeholder="Enter Intervals API key"
                      />
                      <button
                        type="button"
                        onClick={() => setShowApiKey(!showApiKey)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text"
                      >
                        {showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-widest">Athlete ID</label>
                    <input
                      type="text"
                      className="w-full bg-surface-low text-text border border-border rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:border-accent transition-colors"
                      value={form.intervals_icu_athlete_id ?? ''}
                      onChange={(e) => handleChange('intervals_icu_athlete_id', e.target.value)}
                      placeholder="e.g. i12345"
                    />
                  </div>
                </div>

                <div className="bg-surface-low rounded-xl p-6 border border-border">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-6">
                    <div className="flex items-center gap-4">
                      <button
                        onClick={handleSync}
                        disabled={syncing}
                        className="px-6 py-2.5 bg-yellow text-bg rounded-lg text-xs font-bold uppercase tracking-widest hover:opacity-90 disabled:opacity-50 transition-all flex items-center gap-2 shadow-lg shadow-yellow/10"
                      >
                        {syncing ? <RefreshCw size={14} className="animate-spin" /> : 'Sync Now'}
                      </button>
                      {syncOverview?.last_sync?.completed_at && !syncing && (
                        <div className="flex flex-col">
                          <span className="text-[10px] font-bold text-text-muted uppercase tracking-tighter">Last Synchronized</span>
                          <span className="text-xs font-medium">{timeAgo(new Date(syncOverview.last_sync.completed_at))}</span>
                        </div>
                      )}
                    </div>
                  </div>
                  {syncing && (
                    <div className="mt-6 space-y-3">
                      <div className="w-full bg-bg rounded-full overflow-hidden h-2 border border-border">
                        <div className="bg-accent h-full transition-all duration-500 ease-out" style={{ width: `${syncProgress}%` }} />
                      </div>
                      <div ref={logRef} className="bg-bg rounded-lg border border-border p-4 text-[10px] text-text-muted font-mono h-32 overflow-y-auto leading-relaxed">
                        {syncLogs.map((line, i) => <div key={i} className="mb-1">{line}</div>)}
                      </div>
                    </div>
                  )}
                  {syncResult && !syncing && (
                    <div className={`mt-4 p-3 rounded-lg flex items-center gap-2 text-xs font-bold ${syncResult.startsWith('Done') ? 'bg-green/10 text-green' : 'bg-red/10 text-red'}`}>
                      <Info size={14} /> {syncResult.toUpperCase()}
                    </div>
                  )}
                </div>
              </div>
            </section>

            {/* Danger Zone & Info */}
            <section className="pt-6 flex flex-col sm:flex-row items-center justify-between gap-6 border-t border-border/50">
              <div className="flex items-center gap-3">
                <button
                  onClick={handleSaveSystem}
                  disabled={updateSetting.isPending}
                  className="px-6 py-2.5 bg-accent text-white rounded-lg text-xs font-bold uppercase tracking-widest hover:opacity-90 disabled:opacity-50 transition-all shadow-lg shadow-accent/20"
                >
                  Save System Config
                </button>
                <button
                  onClick={handleReset}
                  disabled={resetSettings.isPending}
                  className="px-4 py-2.5 bg-surface-low text-text-muted hover:text-red hover:bg-red/5 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center gap-2"
                >
                  <Trash2 size={14} /> Factory Reset
                </button>
              </div>

              <div className="flex gap-8 text-[10px] font-bold text-text-muted uppercase tracking-widest">
                <div className="flex flex-col">
                  <span className="opacity-50">Frontend</span>
                  <span className="text-text">v{__APP_VERSION__}</span>
                </div>
                <div className="flex flex-col">
                  <span className="opacity-50">Backend</span>
                  <span className="text-text">v{backendVersion?.version ?? '...'}</span>
                </div>
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  )
}
