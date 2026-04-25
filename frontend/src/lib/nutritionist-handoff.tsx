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
  // Increments on every `open()` call so consumers can react to repeated
  // opens even when the same context string is passed twice. React's
  // `setState` dedupes by value, so without this an effect watching
  // `context` alone would not re-fire for an identical follow-up click.
  requestNonce: number
  open: (context?: string, sessionId?: string) => void
  clear: () => void
}

const NutritionistHandoffContext = createContext<NutritionistHandoffValue | undefined>(undefined)

export function NutritionistHandoffProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ context?: string; sessionId?: string; requestNonce: number }>({
    requestNonce: 0,
  })

  const open = useCallback((ctx?: string, sid?: string) => {
    setState(prev => ({ context: ctx, sessionId: sid, requestNonce: prev.requestNonce + 1 }))
  }, [])

  const clear = useCallback(() => {
    setState(prev => ({ context: undefined, sessionId: undefined, requestNonce: prev.requestNonce }))
  }, [])

  return (
    <NutritionistHandoffContext.Provider value={{ ...state, open, clear }}>
      {children}
    </NutritionistHandoffContext.Provider>
  )
}

export function useNutritionistHandoff(): NutritionistHandoffValue {
  const ctx = useContext(NutritionistHandoffContext)
  if (!ctx) throw new Error('useNutritionistHandoff must be used within NutritionistHandoffProvider')
  return ctx
}
