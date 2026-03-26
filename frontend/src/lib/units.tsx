import { createContext, useContext, type ReactNode } from 'react'
import { useSettings } from '../hooks/useApi'

export type UnitSystem = 'metric' | 'imperial'

const UnitsContext = createContext<UnitSystem>('imperial')

export function UnitsProvider({ children }: { children: ReactNode }) {
  const { data: settings } = useSettings()
  const units: UnitSystem = settings?.units === 'metric' ? 'metric' : 'imperial'
  return <UnitsContext.Provider value={units}>{children}</UnitsContext.Provider>
}

export function useUnits(): UnitSystem {
  return useContext(UnitsContext)
}
