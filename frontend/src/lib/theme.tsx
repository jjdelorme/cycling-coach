import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

type Theme = 'dark' | 'light'

interface ThemeCtx {
  theme: Theme
  toggle: () => void
}

const ThemeContext = createContext<ThemeCtx>({ theme: 'dark', toggle: () => {} })

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem('theme') as Theme | null
    return saved || 'dark'
  })

  useEffect(() => {
    document.documentElement.classList.remove('dark', 'light')
    document.documentElement.classList.add(theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggle = () => setTheme(t => (t === 'dark' ? 'light' : 'dark'))

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
