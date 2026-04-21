/**
 * Nutritionist hand-off context.
 *
 * `Nutrition.tsx` and friends call `openNutritionist(context, sessionId)` to
 * pop the Coach panel open on the Nutritionist tab with optional pre-filled
 * context. The Layout subscribes and forwards into `<CoachPanel />`.
 *
 * This was lifted out of `App.tsx` during the router migration so the layout
 * no longer needs prop-drilled callbacks.
 */
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

interface NutritionistHandoffValue {
  context?: string
  sessionId?: string
  open: (context?: string, sessionId?: string) => void
  clear: () => void
}

const NutritionistHandoffContext = createContext<NutritionistHandoffValue | undefined>(undefined)

export function NutritionistHandoffProvider({ children }: { children: ReactNode }) {
  const [context, setContext] = useState<string | undefined>()
  const [sessionId, setSessionId] = useState<string | undefined>()

  const open = useCallback((ctx?: string, sid?: string) => {
    setContext(ctx)
    setSessionId(sid)
  }, [])

  const clear = useCallback(() => {
    setContext(undefined)
    setSessionId(undefined)
  }, [])

  return (
    <NutritionistHandoffContext.Provider value={{ context, sessionId, open, clear }}>
      {children}
    </NutritionistHandoffContext.Provider>
  )
}

export function useNutritionistHandoff(): NutritionistHandoffValue {
  const ctx = useContext(NutritionistHandoffContext)
  if (!ctx) throw new Error('useNutritionistHandoff must be used within NutritionistHandoffProvider')
  return ctx
}
