import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useSettings, useUpdateSetting } from '../hooks/useApi'

type Theme = 'dark' | 'light'

interface ThemeCtx {
  theme: Theme
  toggle: () => void
}

const ThemeContext = createContext<ThemeCtx>({ theme: 'dark', toggle: () => {} })

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { data: settings } = useSettings()
  const updateSetting = useUpdateSetting()
  const [theme, setTheme] = useState<Theme>('dark')

  // Sync from server settings when they load
  useEffect(() => {
    if (settings?.theme === 'light' || settings?.theme === 'dark') {
      setTheme(settings.theme)
    }
  }, [settings?.theme])

  // Apply theme class to document
  useEffect(() => {
    document.documentElement.classList.remove('dark', 'light')
    document.documentElement.classList.add(theme)
  }, [theme])

  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    updateSetting.mutate({ key: 'theme', value: next })
  }

  return (
    <ThemeContext.Provider value={{ theme, toggle }}>
      {children}
    </ThemeContext.Provider>
  )
}

export const useTheme = () => useContext(ThemeContext)

export function useChartColors() {
  const { theme } = useTheme()
  const dark = theme === 'dark'
  return {
    gridColor: dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
    tickColor: dark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.6)',
    legendColor: dark ? '#a1a1aa' : '#52525b',
    tooltipBg: dark ? '#27272a' : '#ffffff',
    tooltipTitle: dark ? '#e4e4e7' : '#1a1a2e',
    tooltipBody: dark ? '#e4e4e7' : '#333333',
    tooltipBorder: dark ? '#3f3f46' : '#d1d5db',
  }
}
